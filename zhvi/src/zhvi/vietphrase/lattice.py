"""VietPhrase lattice + top-K path (thiet ke muc 11.2).

Khac greedy longest-match cu: giu MOI match chong lan thanh edges, tim top-K
duong di toan boang DP/beam, score = trust + length - single-char penalty -
fragmentation penalty. Margin top1/top2 va entropy duong di la risk signal
(M2 dung cho router).

Render (join tokens, punct map, capitalize) nam trong render() de parity
voi ket qua cua engine cu.
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass

from .layers import Layer
from .loader import Dictionary, TrieNode, normalize_nfc, to_simplified
from .patterns import CJK_KEY, DIGIT_KEY, ENTITY_TRUSTS, PRONOUNS, PatternRule, fill_target, is_num_start
from .trace import SourceSpan, VpDraft, VpSpan

CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")

# Render conventions ghe so voi engine cu (QuickTrans).
CN_PUNCT = {
    "，": ",", "。": ".", "？": "?", "！": "!", "；": ";", "：": ":",
    "「": "“", "」": "”", "『": "‘", "』": "’", "《": "«", "》": "»",
    "（": "(", "）": ")", "【": "[", "】": "]", "〈": "<", "〉": ">",
    "、": ",", "～": "~",
}
PUNCT_RE = re.compile("[" + re.escape("".join(CN_PUNCT)) + "]")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?;:”’…)%\]»])")
SPACE_AFTER_OPEN_RE = re.compile(r"([“‘(\[«])\s+")
MULTI_SPACE_RE = re.compile(r"[^\S\n]{2,}")
DROP_PARTICLES = set("的旳了地过過嘛呢吧啊呀啦呐吶呗唄哩哟喲咯喽嘍")
CAP_RE = re.compile(
    r"(^|[.!?]\s*[”’\"']?\s*|\n\s*|[“‘\"']\s*)"
    r"([a-zàáạảãăắằặẳẵâấầậẩẫđèéẹẻẽêếềệểễìíịỉĩòóọỏõôốồộổỗơớờợởỡùúụủũưứừựửữỳýỵỷỹ])"
)

# Trong so khoi diem (user tinh chinh — thiet ke muc 41: khong gan cung).
W_TRUST = 0.01          # trust file scale
W_LEN = 1.0             # bonus moi ky tu thu 2 tro di cua phrase
W_SINGLE = 2.0          # phat single-char fallback
W_FRAG = 1.5            # phat 2 single-char lien ke (phan manh)
W_UNKNOWN = 5.0         # ky tu khong co entry nao
W_DROP = 0.5            # thuong khi boc particle (giu hanh vi QuickTrans)
W_PATTERN = 3.0         # phat luat nhan {s}/{n}: pattern la fallback cua literal


@dataclass(frozen=True)
class Edge:
    start: int
    end: int
    target: str
    precedence: tuple  # (layer, trust, load_index)
    policy: str
    entry_version_id: str | None
    score: float
    alternatives: tuple = ()
    is_pattern: bool = False  # edge tu luat nhan {s}/{n} — thua literal cung do dai


def _find_edges(root: TrieNode, text: str, pos: int) -> list[Edge]:
    """Moi match bat dau tai pos (giu chong lan, khong chi longest)."""
    edges: list[Edge] = []
    node = root
    j = pos
    n = len(text)
    while j < n:
        node = node.children.get(text[j])
        if node is None:
            break
        j += 1
        if not node.entries:
            continue
        for target, prec, policy in node.entries:
            length = j - pos
            score = prec[1] * W_TRUST + (length - 1) * W_LEN
            if length == 1:
                score -= W_SINGLE
                if text[pos] in DROP_PARTICLES:
                    edges.append(Edge(pos, j, "", prec, policy, None, score + W_DROP))
            edges.append(Edge(pos, j, target, prec, policy, f"{prec[0]}:{text[pos:j]}:{target}", score))
    return edges


def _literal_edge(text: str, start: int) -> Edge:
    """Run ky tu khong phai CJK — giu nguyen, khong di qua dictionary."""
    n = len(text)
    j = start
    while j < n and not CJK_RE.match(text[j]):
        j += 1
    return Edge(start, j, text[start:j], (int(Layer.BASE_SINGLE), 0.0, -1), "CONTEXTUAL", None, 0.0)


def _translate_capture(dic: Dictionary, seg: str) -> str:
    """Dich mot capture {s}/{n} qua trie (tat pattern — chong de quy). Khong hoa
    dau cau vi no nam giua chuoi target."""
    if not seg:
        return ""
    edges = greedy_path(dic, seg, patterns=False)
    return " ".join(e.target for e in edges if e.target != "").strip()


def _entity_ok(dic: Dictionary, seg: str) -> bool:
    """{n} chi hop le khi chinh no la mot entry entity (Names/overrides/manual)
    hoac dai tu co trong tu dien — khong phai dong tu/dai tu chi thi."""
    if not seg or seg[0] in PRONOUNS:
        return False
    node = dic.root
    for ch in seg:
        node = node.children.get(ch)
        if node is None:
            return False
    return any(p[1] in ENTITY_TRUSTS for _t, p, _pol in node.entries)


def _candidate_rules(dic: Dictionary, ch: str) -> list[PatternRule]:
    """Rules co the match tai ky tu `ch` (bucket ky tu cu the + DIGIT/CJK)."""
    if not dic.patterns:
        return []
    out: list[PatternRule] = list(dic.patterns.get(ch, ()))
    if is_num_start(ch):
        out += dic.patterns.get(DIGIT_KEY, ())
    if CJK_RE.match(ch):
        out += dic.patterns.get(CJK_KEY, ())
    return out


def _pattern_edges(dic: Dictionary, text: str, pos: int) -> list[Edge]:
    """Edges tu luat nhan {s}/{n} match neo tai pos."""
    edges: list[Edge] = []
    for rule in _candidate_rules(dic, text[pos]):
        m = rule.regex.match(text, pos)
        if not m:
            continue
        if any(
            kind == "n" and not _entity_ok(dic, m.group(i + 1) or "")
            for i, kind in enumerate(rule.slots)
        ):
            continue  # {n} phai la entity that (ten/keyword), khong phai cum dong tu
        filled = fill_target(rule, m, lambda s: _translate_capture(dic, s))
        if not filled:
            continue
        length = m.end() - pos
        score = rule.precedence[1] * W_TRUST + (length - 1) * W_LEN - W_PATTERN
        edges.append(
            Edge(pos, m.end(), filled, rule.precedence, rule.policy,
                 f"{rule.precedence[0]}:{rule.key}:{rule.target}", score, is_pattern=True)
        )
    return edges


@dataclass
class _Path:
    edges: list[Edge]
    score: float
    prev_single: bool


@dataclass
class _State:
    """Mot trang thai DP: duong di ket thuc tai vi tri `pos` (parent-pointer,
    khong copy danh sach edge — tranh O(n^2) tren doan dai)."""

    pos: int
    score: float
    prev_single: bool
    parent: int  # index trong state list, -1 = origin
    edge: Edge | None


def _path_tiebreak_key(p: "_Path") -> tuple:
    """Score bang nhau -> uu tien match dai som nhat (hanh vi greedy cua engine cu).
    Lattice van giu alternatives de tinh margin/entropy."""
    return (-p.score, tuple(-(e.end - e.start) for e in p.edges))


def best_paths(dic: Dictionary, text: str, k: int = 4, *, patterns: bool = True) -> list[_Path]:
    """Top-K duong di qua toan bo text bang beam DP (parent pointers)."""
    n = len(text)
    states: list[_State] = [_State(0, 0.0, False, -1, None)]
    frontier: list[list[int]] = [[] for _ in range(n + 1)]
    frontier[0] = [0]
    for pos in range(n):
        ids = frontier[pos]
        if not ids:
            continue
        ids.sort(key=lambda i: states[i].score, reverse=True)
        ids = ids[:k]
        frontier[pos] = ids
        # sinh edges tu pos
        pat_edges = _pattern_edges(dic, text, pos) if patterns else []
        if CJK_RE.match(text[pos]) or pat_edges:
            candidates = _find_edges(dic.root, text, pos) + pat_edges
            if not candidates:
                candidates = [
                    Edge(pos, pos + 1, text[pos], (int(Layer.BASE_SINGLE), 0.0, -2), "CONTEXTUAL", None, -W_UNKNOWN)
                ]
        else:
            candidates = [_literal_edge(text, pos)]
        for edge in candidates:
            bucket = frontier[edge.end]
            for sid in ids:
                st = states[sid]
                score = st.score + edge.score
                single = edge.end - edge.start == 1 and edge.entry_version_id is not None
                if single and st.prev_single:
                    score -= W_FRAG
                bucket.append(len(states))
                states.append(_State(edge.end, score, single, sid, edge))
    finals = frontier[n]
    materialized: list[_Path] = []
    for sid in finals:
        edges: list[Edge] = []
        cur: int | None = sid
        while cur is not None and cur >= 0:
            st = states[cur]
            if st.edge is not None:
                edges.append(st.edge)
            cur = st.parent if st.parent >= 0 else None
        edges.reverse()
        materialized.append(_Path(edges, states[sid].score, False))
    materialized.sort(key=_path_tiebreak_key)
    return materialized[:k]


def greedy_path(dic: Dictionary, text: str, *, patterns: bool = True) -> list[Edge]:
    """Duong di longest-match tai moi vi tri — baseline QuickTrans (engine cu).

    M1 dung path nay de render (parity voi chat luong da kiem chung); lattice
    top-K o tren dung de tinh margin/entropy/alternatives cho risk (M2 router).
    patterns=False dung khi dich capture cua rule — tranh de quy vo han.
    """
    edges: list[Edge] = []
    n = len(text)
    pos = 0
    while pos < n:
        pat: list[Edge] = []
        if patterns and (CJK_RE.match(text[pos]) or is_num_start(text[pos])):
            pat = _pattern_edges(dic, text, pos)
        if CJK_RE.match(text[pos]) or pat:
            cands = _find_edges(dic.root, text, pos) + pat
            if not cands:
                edges.append(
                    Edge(pos, pos + 1, text[pos], (int(Layer.BASE_SINGLE), 0.0, -2), "CONTEXTUAL", None, -W_UNKNOWN)
                )
                pos += 1
                continue
            longest = max(e.end for e in cands)
            # AD-9 (story 1.4): trong cac match dai nhat — layer precedence
            # (layer, trust) truoc, roi literal thang pattern, roi tie-break
            # theo entry_version_id (lexical). entry_version_id la derived id
            # on dinh (layer:span:target) — KHONG dung load_index: output
            # khong phu thuoc thu tu nap tu dien. Epic 2 thay bang id that
            # cua entry_versions.
            best = min(
                (e for e in cands if e.end == longest),
                key=lambda e: (
                    -e.precedence[0],
                    -e.precedence[1],
                    e.is_pattern,
                    e.entry_version_id or "",
                ),
            )
            if longest == pos + 1 and text[pos] in DROP_PARTICLES:
                best = Edge(pos, longest, "", best.precedence, best.policy, best.entry_version_id, best.score + W_DROP)
            edges.append(best)
            pos = longest
        else:
            e = _literal_edge(text, pos)
            edges.append(e)
            pos = e.end
    return edges


def _entropy(paths: list[_Path]) -> float:
    if len(paths) < 2:
        return 0.0
    scores = [p.score for p in paths]
    mx = max(scores)
    exps = [math.exp(s - mx) for s in scores]
    total = sum(exps)
    return -sum((e / total) * math.log(e / total + 1e-12) for e in exps)


def _source_has_reduplication(text: str, start: int, end: int) -> bool:
    """Nguon co lap lai lien ke that (VD 有些有些, 磨炼磨炼) trong vung [start,end).

    Lap lai co chu dich cua tac gia -> giu; khong phai lap lai nguon -> artifact
    cua hai span khac nhau cung map ve mot target.
    """
    region = text[start:end]
    for unit in (1, 2, 3):
        for i in range(len(region) - 2 * unit + 1):
            a = region[i : i + unit]
            b = region[i + unit : i + 2 * unit]
            if a == b and CJK_RE.match(a[0]):
                return True
    return False


def collapse_repetitions(edges: list[Edge], text: str) -> tuple[list[Edge], int, list[tuple[int, int]]]:
    """Chong lap tu phia target (artifact cua greedy/luat Han-Viet).

    Edge ke tiep co target trung nhau hoac target sau bat dau bang target truoc
    (VD 'đã' + 'đã bị') va nguon KHONG lap lai that -> loai edge dau, giu edge
    sau (chua noi dung day du). Lap lai nguon (磨炼磨炼 → ma luyện ma luyện)
    duoc giu nguyen — dung SYSTEM_PROMPT 'giu nhip lap'.

    Tra (edges con lai, so lan collapse, offsets (start, end) tung span bi bo —
    AD-18: transformation kem source-offset trace).
    """
    out: list[Edge] = []
    collapsed = 0
    dropped: list[tuple[int, int]] = []
    i = 0
    n = len(edges)
    while i < n:
        e = edges[i]
        j = i + 1
        while j < n and edges[j].target == "":
            j += 1
        if (
            j < n
            and e.target
            and e.entry_version_id is not None
            and edges[j].entry_version_id is not None
        ):
            t1, t2 = e.target, edges[j].target
            if (t1 == t2 or t2.startswith(t1 + " ")) and not _source_has_reduplication(
                text, e.start, edges[j].end
            ):
                collapsed += 1
                dropped.append((e.start, e.end))
                i += 1  # bo e dau, giu e sau
                continue
        out.append(e)
        i += 1
    return out, collapsed, dropped


def render(edges: list[Edge]) -> str:
    """Ghep target theo QuickTrans conventions ( nhu engine cu)."""
    parts = [e.target for e in edges if e.target != ""]
    text = " ".join(parts)
    text = text.replace("……", "...").replace("…", "...").replace("——", "—")
    text = PUNCT_RE.sub(lambda m: CN_PUNCT.get(m.group(0), m.group(0)), text)
    text = SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = SPACE_AFTER_OPEN_RE.sub(r"\1", text)
    text = MULTI_SPACE_RE.sub(" ", text)
    text = text.strip()
    text = CAP_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    return normalize_nfc(text)


def vp_plan(
    dic: Dictionary,
    text: str,
    *,
    beam: int = 4,
    occurrence_prefix: str = "",
    collapse_reps: bool = True,
) -> VpDraft:
    """ Dich mot doan van: lattice -> top-1 path -> VpDraft co trace + risk.

    Offset trong trace theo text da simplified (NFC) — nguon goi luu ca hai.
    """
    if not text.strip():
        return VpDraft(text=text, spans=(), unknown_spans=(), single_char_ratio=0.0,
                       lattice_margin=1.0, lattice_entropy=0.0)
    # AD-9 trace (story 1.4): giu ban goc (phồn thể) de span.source luu nguon
    # that; to_simplified thay tung ky tu nen offset simplified == offset goc.
    orig = normalize_nfc(text)
    text = normalize_nfc(to_simplified(text, dic.trad_simp))
    paths = best_paths(dic, text, k=max(2, beam))
    if not paths:
        return VpDraft(text=text, spans=(), unknown_spans=(), single_char_ratio=0.0,
                       lattice_margin=0.0, lattice_entropy=0.0, warnings=("NO_PATH",))
    # M1: render theo greedy (parity QuickTrans cu); lattice lo duong di
    # khac de do margin/entropy — router M2 quyet dinh dung cai nao.
    greedy_edges = greedy_path(dic, text)
    # Rule chong lap: loai artifact trung target giua hai edge ke nhau khi
    # nguon khong lap lai that (VD 'có chút'+'có chút lo lắng' -> giu cai sau).
    collapsed_count = 0
    collapsed_spans: list[tuple[int, int]] = []
    if collapse_reps:
        greedy_edges, collapsed_count, collapsed_spans = collapse_repetitions(greedy_edges, text)
    greedy_score = sum(e.score for e in greedy_edges)
    best = _Path(greedy_edges, greedy_score, False)
    margin = (paths[0].score - paths[1].score) if len(paths) > 1 else float("inf")
    entropy = _entropy(paths)
    # bat dong greedy vs lattice best = segmentation instability (risk feature muc 12)
    disagreement = max(0.0, paths[0].score - greedy_score)

    spans: list[VpSpan] = []
    unknowns: list[SourceSpan] = []
    single_count = 0
    cjk_count = 0
    warnings: list[str] = []
    for idx, edge in enumerate(best.edges):
        src = orig[edge.start : edge.end]  # source GOC (phồn thể) — key match la giản thể
        if not CJK_RE.search(src):
            continue
        cjk_count += sum(1 for ch in src if CJK_RE.match(ch))
        if edge.entry_version_id is None and edge.precedence[2] == -2:
            unknowns.append(SourceSpan(edge.start, edge.end, src))
            continue
        if edge.target == "":  # particle boc
            continue
        if edge.end - edge.start == 1:
            single_count += 1
        spans.append(
            VpSpan(
                occurrence_id=f"{occurrence_prefix}#{idx}",
                source_start=edge.start,
                source_end=edge.end,
                source=src,
                target=edge.target,
                alternatives=edge.alternatives,
                entry_version_id=edge.entry_version_id,
                policy=edge.policy,
                path_score=edge.score,
            )
        )
    if unknowns:
        warnings.append("UNKNOWN_SPAN")
    if margin != float("inf") and margin < 1.0:
        warnings.append("LOW_LATTICE_MARGIN")
    if disagreement > 0.5:
        warnings.append("SEGMENTATION_INSTABILITY")
    if collapsed_count:
        warnings.append(f"REPETITION_COLLAPSED:{collapsed_count}")
    return VpDraft(
        text=render(best.edges),
        spans=tuple(spans),
        unknown_spans=tuple(unknowns),
        single_char_ratio=single_count / cjk_count if cjk_count else 0.0,
        lattice_margin=0.0 if margin == float("inf") else margin,
        lattice_entropy=entropy,
        warnings=tuple(warnings),
        collapsed_spans=tuple(collapsed_spans),
    )
