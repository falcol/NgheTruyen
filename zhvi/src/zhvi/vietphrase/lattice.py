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
from dataclasses import dataclass, replace

from .layers import Layer
from .loader import TRUST_BY_FILE, Dictionary, TrieNode, normalize_nfc, to_simplified
from .patterns import (
    CJK_KEY,
    DIGIT_KEY,
    ENTITY_SUFFIXES,
    PRONOUNS,
    VERBS,
    PatternRule,
    fill_target,
    is_num_start,
)
from .sense import (
    _IDIOMS,
    _ORD_TITLE2,
    _PROTECTED_OVERFLOWS,
    _SPEECH_AFTER_DAO,
    apply_sense,
    dehua_conditional,
    ordinal_tail,
)
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
# Convert artifact: 已经+了 / 被+被. Khong nuot "phòng bị bị đánh" (phòng bị + bị).
DA_DA_RE = re.compile(r"\bđã đã\b", re.IGNORECASE)
BI_BI_RE = re.compile(r"(?<![Pp]hòng )\bbị bị\b")
DA_BI_DOAT_DA_RE = re.compile(r"đã bị đoạt đã")
# QT boc hat 1 chu sau longest-match. 了/着/过 giu — sense map đã/đang/rồi.
DROP_PARTICLES = set("的旳地嘛呢吧啊呀啦呐吶呗唄哩哟喲咯喽嘍")
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
# Names.txt / Names_2.txt — QT prioritizedName. Khong dung ENTITY_TRUSTS
# (QO/Custom 25/100 la phrase override, khong phai ten).
_NAME_FILE_TRUST = TRUST_BY_FILE["Names.txt"]


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


def _is_name_prec(prec: tuple) -> bool:
    """Ten duoc bao ve: Names.txt (trust 20) hoac glossary (SERIES/BOOK_MANUAL)."""
    layer, trust, _idx = prec
    if layer >= int(Layer.SERIES_MANUAL):
        return True
    return layer == int(Layer.BASE_MULTI) and trust == _NAME_FILE_TRUST


# Custom.txt tron ten rieng (Tieu My...) + cum tu (cau truc, fix).
# Chi muc TEN duoc quyen name (chon nuot edge glue): target viet hoa +
# source khong chua hat chuc nang. Cum (桌上的, 足以让人...) khong duoc
# nuot nguoc edge khac.
_NAME_PARTICLES = frozenset("的得地了着过吗呢吧啊")


def _is_custom_name(layer: int, trust: float, target: str, source: str) -> bool:
    """True neu entry la ten rieng khai tay trong Custom.txt."""
    return (
        layer == int(Layer.GLOBAL_MANUAL)
        and trust >= TRUST_BY_FILE["Custom.txt"]
        and bool(target)
        and target[0].isupper()
        and not _NAME_PARTICLES.intersection(source)
    )


def _span_is_protected(dic: Dictionary, text: str, start: int, end: int) -> bool:
    """Edge hien tai la ten/glossary/Custom/QO — dung de junk Names cat ngang."""
    node = dic.root
    for ch in text[start:end]:
        node = node.children.get(ch)
        if node is None:
            return False
    return any(
        _is_name_prec(p) or p[0] >= int(Layer.GLOBAL_MANUAL)
        for _t, p, _pol in node.entries
    )


def _inner_name(dic: Dictionary, text: str, pos: int) -> tuple[int, int, str] | None:
    """Ten dai >= 2 bat dau tai pos. Tra (end, layer, target) cua match
    name-prec dai nhat (entry manh nhat trong node thang).

    is_manual cu (SERIES/BOOK_MANUAL) duoc thay bang layer + target cu the
    de caller phan biet ten that voi glue word viet thuong (了一=mot,
    在了=o) — xem _swallows_name.
    """
    node = dic.root
    j = pos
    n = len(text)
    last: tuple[int, int, str] | None = None
    while j < n:
        node = node.children.get(text[j])
        if node is None:
            break
        j += 1
        if j - pos < 2:
            continue
        name_entries = [(t, p) for t, p, _pol in node.entries if _is_name_prec(p)]
        if not name_entries:
            continue
        target, prec = max(name_entries, key=lambda te: te[1])
        last = (j, prec[0], target)
    return last


def _custom_name_collision(dic: Dictionary, text: str, edge: Edge) -> bool:
    """Ten Custom (Tieu My...) bi edge glue ngan (是小) nuot mat chu dau.
    Drop de ten thang.

    Hep co chu dich: chi edge len<=3 (glue) — cum dai co nghia nhu
    数学老师 giu nguyen; ten phai keo dai qua edge.end; entry phai la
    TEN Custom (target viet hoa, source khong hat), khong phai cum
    (桌上的, 足以让人...).
    """
    if edge.is_pattern or edge.end - edge.start > 3:
        return False
    if _span_is_protected(dic, text, edge.start, edge.end):
        return False
    for i in range(edge.start + 1, edge.end):
        node = dic.root
        j = i
        n = len(text)
        while j < n:
            node = node.children.get(text[j])
            if node is None:
                break
            j += 1
            if j - i < 2 or j <= edge.end:
                continue
            for _t, p, _pol in node.entries:
                if _is_custom_name(p[0], p[1], _t, text[i:j]):
                    return True
    return False


def _ordinal_title_collision(dic: Dictionary, text: str, edge: Edge) -> bool:
    """Ordinal 第X<C> (VD 第一掌=chuong phap) nuot chu dau cua title
    (VD 掌门). Drop de 第X + title thang (sense de N + trace sach).

    Chi khi title (C + chu ke) thuoc bank ton hieu VA co that trong trie —
    tranh che sai khi cum khong ton tai (VD 第一掌 don le van giu).
    """
    if edge.is_pattern:
        return False
    if ordinal_tail(text[edge.start : edge.end]) is None:
        return False
    if edge.end >= len(text):
        return False
    title = text[edge.end - 1 : edge.end + 1]
    if title not in _ORD_TITLE2:
        return False
    node = dic.root
    for ch in title:
        node = node.children.get(ch)
        if node is None:
            return False
    return bool(node.entries)


def _longest_word_len(dic: Dictionary, text: str, pos: int) -> int:
    """Do dai match dai nhat trong trie bat dau tai pos (0 neu khong co)."""
    node = dic.root
    best = 0
    j = pos
    n = len(text)
    while j < n:
        node = node.children.get(text[j])
        if node is None:
            break
        j += 1
        if node.entries:
            best = j - pos
    return best


# Duoi tu ghep 2-4 chu: leftover 1 chu nay hiem khi dung le (脉/力/云/乎/意),
# khac 人/子/的 (一个+人, 个人). Dung de drop edge cuop chu dau 血脉/之力/在乎.
# [Note] 魂 bi loai: 魂力 (hon luc) qua pho bien tien hiep; overflow 大魂
# hiem khi la tu that — giu lai gay false positive chet 强大魂力 (parity chap1).
_BOUND_COMPOUND_TAILS = frozenset("脉力气云术丹阵魄灵光界门乎意")
# Locative 2 chu (心中/桌上): khong drop khi 中气/上X tran — khac 他在|乎.
_LOCATIVE_EDGE_ENDS = frozenset("中上下内外前后里间")
_NAME_GLUE_REST = frozenset({"已经", "已經"})
# 没有/所有 (2) vs 有敌意 (duoi 意): khong drop 2 chu chuc nang.
_CLOSED_YOU = frozenset({"没有", "所有", "只有", "还有"})


_PRONOUN_SKIP_TAIL = frozenset("们們的")


def _stolen_pronoun_np(dic: Dictionary, text: str, edge: Edge) -> bool:
    """Pronoun+X NP (她信, 它坚持) cuop chu dau cua tu 3+ chu tran khoi
    (信不过, 坚持下来了). Drop de dai tu don + compound thang.

    Khong them 过 vao bound-tail (qua/rồi pho bien). Chi prefix dai tu,
    overflow dai >= 3 (tranh 他看|来 2 chu); 不 thi >= 2 (我不|算).
    们/的 khong drop (他们/她的).
    Name-prec giu nhu _stolen_compound; Custom van drop.
    """
    if edge.is_pattern or edge.end - edge.start < 2:
        return False
    if text[edge.start] not in PRONOUNS:
        return False
    if text[edge.start + 1] in _PRONOUN_SKIP_TAIL:
        return False
    if _is_name_prec(edge.precedence):
        return False
    i = edge.start + 1
    # 我不|算: 不算 chi 2 chu; 他看|来 van min 3.
    min_wlen = 2 if text[i] == "不" else 3
    node = dic.root
    n = len(text)
    for j in range(i, min(i + 8, n)):
        node = node.children.get(text[j])
        if node is None:
            break
        wlen = j - i + 1
        word_end = j + 1
        if not node.entries or wlen < min_wlen or word_end <= edge.end:
            continue
        return True
    return False


def _stolen_compound(dic: Dictionary, text: str, edge: Edge) -> bool:
    """Edge generic cuop chu dau cua tu ghep tran khoi (这么多血|脉, 多少血|脉).

    Giong _stolen_bu nhung hinh hoc nguoc: tu tran (血脉 2) NGAN hon edge
    (这么多血 4). Chi khi tu tran ket thuc bang bound tail — tranh 一个+人.
    Ten rieng (name-prec) khong drop; phrase Custom (多少血) van drop.

    Xet MOI word 2-4 chu tran khoi, khong chi longest: 在乎的 (3, duoi 的)
    che 在乎 (2, duoi 乎) neu chi nhin longest.
    """
    if edge.is_pattern or edge.end - edge.start < 2:
        return False
    if _is_name_prec(edge.precedence):
        return False
    n = len(text)
    for i in range(edge.start + 1, edge.end):
        node = dic.root
        for j in range(i, min(i + 4, n)):
            node = node.children.get(text[j])
            if node is None:
                break
            wlen = j - i + 1
            word_end = j + 1
            if not node.entries or wlen < 2 or word_end <= edge.end:
                continue
            if text[word_end - 1] not in _BOUND_COMPOUND_TAILS:
                continue
            # Glue last-char 2 chu (人丹) khi tu 2+ bat dau dung edge.end
            # (丹田): NP 3+ chu (蒙面人) la that, khong phai ke cuop.
            # 这么多血|脉 (edge.end = 1 chu) va 他在|乎 van drop.
            if (
                i == edge.end - 1
                and wlen == 2
                and edge.end - edge.start >= 3
                and _longest_word_len(dic, text, edge.end) >= 2
            ):
                continue
            # 心中 vs 中气: locative 2 chu that, 气 bound-tail khong duoc cat.
            if (
                edge.end - edge.start == 2
                and text[edge.end - 1] in _LOCATIVE_EDGE_ENDS
                and i == edge.end - 1
                and wlen == 2
            ):
                continue
            if (
                i == edge.end - 1
                and edge.end - edge.start == 2
                and text[edge.start : edge.end] in _CLOSED_YOU
            ):
                continue
            return True
    return False


def _stolen_bu(dic: Dictionary, text: str, edge: Edge) -> bool:
    """Edge generic ket thuc bang 不 (VD 到不) cuop 不 cua tu dai hon
    bat dau tai do (VD 不可思议). Drop de longest-match thang.

    Chi khi tu 不 dai hon edge (不可思议 4 > 到不 2); 不了 (2) vs
    到不 (2) giu nguyen — bao ve 到不了 that. Tu X不 da thanh lap
    (要不/这不/那不/毫不/莫不/并不) khong bao gio drop.
    """
    if edge.is_pattern or edge.end - edge.start < 2:
        return False
    if text[edge.end - 1] != "不":
        return False
    if text[edge.start : edge.end] in ("要不", "这不", "那不", "毫不", "莫不", "并不"):
        return False
    if _span_is_protected(dic, text, edge.start, edge.end):
        return False
    return _longest_word_len(dic, text, edge.end - 1) > edge.end - edge.start


def _idiom_overflow(dic: Dictionary, text: str, edge: Edge) -> bool:
    """Edge 2 chu (VD 人望) che chu dau cua thanh ngu curated (VD 望其项背)
    bat dau tai cuoi edge va tran khoi. Drop de thanh ngu thang.

    Hep co chu dich: chi thanh ngu trong _IDIOMS (khong phai moi tu dai
    trong trie — VD 就忍不住/果然如此/个人观点 chia doi duoc nen khong
    bao ve, 早就/如果 an toan); thanh ngu phai co that trong trie; tu
    不... do _stolen_bu phu trach.
    """
    if edge.is_pattern:
        return False
    if edge.end - edge.start != 2:
        return False
    if _span_is_protected(dic, text, edge.start, edge.end):
        return False
    tail = edge.end - 1
    if text[tail : tail + 4] not in _IDIOMS:
        return False
    return _longest_word_len(dic, text, tail) >= 4


def _has_entry(dic: Dictionary, zh: str) -> bool:
    node = dic.root
    for ch in zh:
        node = node.children.get(ch)
        if node is None:
            return False
    return bool(node.entries)


def _de_tail_vp(dic: Dictionary, text: str, edge: Edge) -> bool:
    """兴师问罪的 (5+): 的 hat, drop de idiom | 的."""
    if edge.is_pattern or edge.end - edge.start < 5:
        return False
    if text[edge.end - 1] != "的":
        return False
    return _has_entry(dic, text[edge.start : edge.end - 1])


def _protected_overflow(dic: Dictionary, text: str, edge: Edge) -> bool:
    """Edge ngan cuop chu dau cum bao ve (是知|知情人, 你要|要么, 人解|解决)."""
    if edge.is_pattern or edge.end - edge.start < 2:
        return False
    if _is_name_prec(edge.precedence):
        return False
    n = len(text)
    for i in range(edge.start + 1, edge.end):
        for length in (2, 3, 4):
            end = i + length
            if end > n:
                break
            if end <= edge.end:
                continue
            if text[i:end] in _PROTECTED_OVERFLOWS:
                return True
    return False


_DAO_TRAVEL = frozenset({"就道", "便道"})


def _travel_dao_before_speech(dic: Dictionary, text: str, edge: Edge) -> bool:
    """就道/便道 truoc ngoac thoai: drop de 就|道, 道 -> nói."""
    if edge.is_pattern:
        return False
    if text[edge.start : edge.end] not in _DAO_TRAVEL:
        return False
    rest = text[edge.end :]
    return bool(rest) and rest[0] in _SPEECH_AFTER_DAO


_QI_PRONOUN_LAI = frozenset({"我来", "你来", "他来", "她来", "它来"})
_KIN_TITLES = ("姐姐", "哥哥", "妹妹", "弟弟")
_PRONOUN_DE_TAILS = tuple(p + "的" for p in sorted(PRONOUNS)) + ("自己的",)


def _kin_before_de_zhuren(dic: Dictionary, text: str, edge: Edge) -> bool:
    """是她 / 是她姐姐 + 姐姐的主人: drop de 她姐姐的主人 thang, khong 'nàng chủ nhân'."""
    if edge.is_pattern:
        return False
    src = text[edge.start : edge.end]
    rest = text[edge.end :]
    if rest.startswith("的主人") and any(src.endswith(k) for k in _KIN_TITLES):
        return True
    return any(rest.startswith(k + "的主人") for k in _KIN_TITLES)


def _pronoun_de_before_noun(dic: Dictionary, text: str, edge: Edge) -> bool:
    """给她的|主人, 自己的|半边脸: drop de {p}的主人 / 自己 | 的 | NP dao."""
    if edge.is_pattern or edge.end - edge.start < 2:
        return False
    src = text[edge.start : edge.end]
    if not any(src.endswith(t) for t in _PRONOUN_DE_TAILS):
        return False
    rest = text[edge.end :]
    if not rest or not CJK_RE.match(rest[0]):
        return False
    return _longest_word_len(dic, text, edge.end) >= 2


def _jiu_da_before_guolai(dic: Dictionary, text: str, edge: Edge) -> bool:
    """电话就打|过来了: 就打 cuop 打 của 打过来. Drop de 就 | 打过来."""
    if edge.is_pattern:
        return False
    if text[edge.start : edge.end] != "就打":
        return False
    return text[edge.end :].startswith("过来")


def _pronoun_lai_after_qi(dic: Dictionary, text: str, edge: Edge) -> bool:
    """威胁起我来了: 我来 cuop 来 của 来了. Drop de 我 | 来了 (sense empty)."""
    if edge.is_pattern:
        return False
    if text[edge.start : edge.end] not in _QI_PRONOUN_LAI:
        return False
    return "起" in text[max(0, edge.start - 4) : edge.start]


def _shi_dui_before_name(dic: Dictionary, text: str, edge: Edge) -> bool:
    """是对 + ten: drop de 是 | 对{n}的{p}."""
    if edge.is_pattern or text[edge.start : edge.end] != "是对":
        return False
    for length in (2, 3, 4):
        seg = text[edge.end : edge.end + length]
        if len(seg) == length and _entity_ok(dic, seg):
            return True
    return False


def _name_function_glue(dic: Dictionary, text: str, edge: Edge) -> bool:
    """VP glue 凌天已经: ten o dau + 已经. Drop de ten | 已经."""
    if edge.is_pattern or _is_name_prec(edge.precedence):
        return False
    hit = _inner_name(dic, text, edge.start)
    if hit is None:
        return False
    name_end, _layer, target = hit
    if not target or not target[0].isupper():
        return False
    if name_end <= edge.start or name_end >= edge.end:
        return False
    return text[name_end:edge.end] in _NAME_GLUE_REST


def _swallows_name(dic: Dictionary, text: str, edge: Edge) -> bool:
    """Bo generic neu ten bat dau lech ben trong va (tran khoi span | glossary).

    Phrase chinh no la ten -> giu (QT containsName early-return). Pattern
    {n}/{p} dung ten lam capture, khong nuot. Dai < 2 khong bao gio nuot.
    Names.txt nam gon trong collocation (天地 trong 得天地厚爱) khong chan —
    file ten rat nhieu 2-chu common word.
    """
    if edge.is_pattern or edge.end - edge.start < 2:
        return False
    if _span_is_protected(dic, text, edge.start, edge.end):
        return False
    if _ordinal_title_collision(dic, text, edge):
        return True
    if _custom_name_collision(dic, text, edge):
        return True
    for i in range(edge.start + 1, edge.end):
        hit = _inner_name(dic, text, i)
        if hit is None:
            continue
        name_end, layer, target = hit
        if layer >= int(Layer.BOOK_MANUAL):
            return True  # book/user lock: van bao ve ke ca khi nam gon
        if layer >= int(Layer.SERIES_MANUAL):
            # Gloss series/global: chi bao ve khi la ten that (viet hoa).
            # Glue word viet thuong (了一=mot, 在了=o) nam gon trong cum
            # dai hon khong duoc cat cum (VD 贴在了=dinh vao).
            if target and target[0].isupper():
                return True
            continue
        # Names.txt: chi khi ten dai >= 3 VA tran khoi span. 2-chu (汉语, 天神)
        # overlapping 1 ky tu la common-word rac, khong phai ten that.
        if name_end > edge.end and name_end - i >= 3:
            return True
    return False


def _candidates_at(dic: Dictionary, text: str, pos: int, *, patterns: bool) -> list[Edge]:
    """Edges tai pos sau khi loai generic nuot ten (QT prioritizedName)."""
    pat_edges = _pattern_edges(dic, text, pos) if patterns else []
    if CJK_RE.match(text[pos]) or pat_edges:
        candidates = _find_edges(dic.root, text, pos) + pat_edges
        candidates = [e for e in candidates if not _swallows_name(dic, text, e)]
        candidates = [e for e in candidates if not _idiom_overflow(dic, text, e)]
        candidates = [e for e in candidates if not _stolen_bu(dic, text, e)]
        candidates = [e for e in candidates if not _stolen_compound(dic, text, e)]
        candidates = [e for e in candidates if not _stolen_pronoun_np(dic, text, e)]
        candidates = [e for e in candidates if not _protected_overflow(dic, text, e)]
        candidates = [e for e in candidates if not _name_function_glue(dic, text, e)]
        candidates = [e for e in candidates if not _travel_dao_before_speech(dic, text, e)]
        candidates = [e for e in candidates if not _shi_dui_before_name(dic, text, e)]
        candidates = [e for e in candidates if not _de_tail_vp(dic, text, e)]
        candidates = [e for e in candidates if not _pronoun_lai_after_qi(dic, text, e)]
        candidates = [e for e in candidates if not _kin_before_de_zhuren(dic, text, e)]
        candidates = [e for e in candidates if not _pronoun_de_before_noun(dic, text, e)]
        candidates = [e for e in candidates if not _jiu_da_before_guolai(dic, text, e)]
        if not candidates:
            candidates = [
                Edge(pos, pos + 1, text[pos], (int(Layer.BASE_SINGLE), 0.0, -2), "CONTEXTUAL", None, -W_UNKNOWN)
            ]
        return candidates
    return [_literal_edge(text, pos)]


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
    """{n} hop le: entry entity (Names/manual) hoac hau to tong/dat (宗门…).
    Khong nuot dai tu/dong tu ('無視自己')."""
    if not seg or seg[0] in PRONOUNS:
        return False
    if seg[-1] in ENTITY_SUFFIXES and all(CJK_RE.match(ch) for ch in seg):
        return True
    node = dic.root
    for ch in seg:
        node = node.children.get(ch)
        if node is None:
            return False
    for target, prec, _pol in node.entries:
        trust = prec[1]
        if trust in (20.0, 25.0, 1000.0):
            return True
        # Custom 100: chi ten (viet hoa). 让=để khong phai {n}.
        if trust >= 100.0 and target and target[0].isupper():
            return True
    return False


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


def _pattern_capture_swallows_word(dic: Dictionary, text: str, cap_start: int, cap_end: int) -> bool:
    """Capture {p} tham nuot chu dau cua tu dai tran ra ngoai capture
    (VD 六岁的{p} bat 小胖子幸, nuot 幸 cua 幸灾乐祸道). Skip de literal
    dai thang — doi xung cua _swallows_name (literal nuot ten).

    Chi tinh word dai >= 3 trong trie: overlap 2 chu thuong la common-word
    rac (cung triet ly _swallows_name). {n} da co _entity_ok rieng; {s}/{v}
    (so/dong tu) khong the chua word CJK tran.
    """
    if cap_end - cap_start < 2:
        return False
    n = len(text)
    for i in range(cap_start + 1, cap_end):
        node = dic.root
        for j in range(i, min(i + 8, n)):
            node = node.children.get(text[j])
            if node is None:
                break
            wlen = j - i + 1
            word_end = j + 1
            if not node.entries or wlen < 3 or word_end <= cap_end:
                continue
            return True
    return False


def _pattern_edges(dic: Dictionary, text: str, pos: int) -> list[Edge]:
    """Edges tu luat nhan {s}/{n} match neo tai pos."""
    edges: list[Edge] = []
    for rule in _candidate_rules(dic, text[pos]):
        m = rule.regex.match(text, pos)
        if not m:
            continue
        skip = False
        for i, kind in enumerate(rule.slots):
            cap = m.group(i + 1) or ""
            if kind == "n" and not _entity_ok(dic, cap):
                skip = True  # {n} entity/ten, khong nuot dong tu
                break
            if kind == "v" and cap not in VERBS:
                skip = True
                break
            if kind == "p":
                cs, ce = m.start(i + 1), m.end(i + 1)
                if ce > cs and _pattern_capture_swallows_word(dic, text, cs, ce):
                    skip = True  # {p} nuot chu dau tu dai tran ra ngoai
                    break
        if skip:
            continue
        # So huu X的{p} nuot hat dieu kien 的话 (VD 要是杀掉凌天的话 ->
        # "loi noi cua Lang Thien"). Chi skip khi dehua_conditional xac
        # nhan conditional; topic X的话 + dong tu (VD 凌天的话让...) va
        # ngu canh nghe/tin (VD 听到凌天的话) giu "loi noi cua X".
        if rule.key.endswith("的{p}") and rule.slots[-1:] == ("p",):
            cap = m.group(len(rule.slots))
            if cap in ("时候", "時候"):
                continue
            if cap in ("话", "話"):
                if dehua_conditional(text, m.end() - 2, m.end()):
                    continue
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
        candidates = _candidates_at(dic, text, pos, patterns=patterns)
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


_CLAN_PLURAL = frozenset(("我们", "你们", "他们", "她们", "它们", "咱们"))


def _is_clan_name_edge(edge: Edge, src: str) -> bool:
    """Ten ho X家 (Names/Custom), khong VP 回家/国家/全家."""
    if not (2 <= len(src) <= 3 and src.endswith("家")):
        return False
    if _is_name_prec(edge.precedence):
        return True
    layer, trust, _idx = edge.precedence
    return _is_custom_name(layer, trust, edge.target, src)


def _possessive_clan(edges: list[Edge], text: str) -> list[Edge]:
    """Pronoun + ten ho X家 -> 'X gia của ta' (灭我赵家, khong 'diệt ta Triệu Gia')."""
    out: list[Edge] = []
    i = 0
    n = len(edges)
    while i < n:
        e = edges[i]
        src = text[e.start : e.end]
        if (src in PRONOUNS or src in _CLAN_PLURAL) and i + 1 < n and e.target:
            nxt = edges[i + 1]
            nsrc = text[nxt.start : nxt.end]
            if nxt.start == e.end and _is_clan_name_edge(nxt, nsrc) and nxt.target:
                out.append(
                    replace(
                        nxt,
                        start=e.start,
                        target=f"{nxt.target} của {e.target}",
                        score=e.score + nxt.score,
                    )
                )
                i += 2
                continue
        out.append(e)
        i += 1
    return out


def _is_possessive_head(edge: Edge, src: str) -> bool:
    """Ve trai 的 so huu: dai tu hoac ten (target viet hoa)."""
    if not edge.target:
        return False
    if src in PRONOUNS or src in _CLAN_PLURAL or src == "自己":
        return True
    if any(src.endswith(k) for k in _KIN_TITLES):
        return True
    return bool(edge.target[0].isupper())


_TIME_AFTER_DE = frozenset(
    {"晚上", "夜晚", "早上", "中午", "下午", "白天", "夜里", "夜裏", "清晨", "傍晚", "凌晨"}
)


def _possessive_de(edges: list[Edge], text: str) -> list[Edge]:
    """Ten/dai tu + 的 (boc) + NP -> 'NP của ten' (花少的耻辱).

    Thoi diem (晚上): 'buổi tối ở Đồng Thành', khong 'của'.
    Khong dao 新的老师 / 打不晕的凌天 (ve trai khong phai ten).
    """
    out: list[Edge] = []
    i = 0
    n = len(edges)
    while i < n:
        e = edges[i]
        src = text[e.start : e.end]
        if src in ("的", "旳") and not e.target and out and i + 1 < n:
            left = out[-1]
            right = edges[i + 1]
            lsrc = text[left.start : left.end]
            rsrc = text[right.start : right.end]
            if (
                left.end == e.start
                and e.end == right.start
                and right.target
                and _is_possessive_head(left, lsrc)
                and CJK_RE.match(text[right.start])
            ):
                if rsrc in _TIME_AFTER_DE:
                    joined = f"{right.target} ở {left.target}"
                else:
                    joined = f"{right.target} của {left.target}"
                out[-1] = replace(
                    right,
                    start=left.start,
                    target=joined,
                    score=left.score + right.score,
                )
                i += 2
                continue
        out.append(e)
        i += 1
    return out


def _dui_before_name(edges: list[Edge], text: str) -> list[Edge]:
    """对 + ten (viet hoa) -> 'với' (对凌天各种客气), khong 'đối'."""
    out = list(edges)
    for i, e in enumerate(out):
        if text[e.start : e.end] != "对" or not e.target:
            continue
        if i + 1 >= len(out):
            continue
        nxt = out[i + 1]
        if nxt.start != e.end or not nxt.target:
            continue
        if nxt.target[0].isupper():
            out[i] = replace(e, target="với")
    return out


def greedy_path(dic: Dictionary, text: str, *, patterns: bool = True) -> list[Edge]:
    """Duong di longest-match tai moi vi tri — baseline QuickTrans (engine cu).

    M1 dung path nay de render (parity voi chat luong da kiem chung); lattice
    top-K o tren dung de tinh margin/entropy/alternatives cho risk (M2 router).
    patterns=False dung khi dich capture cua rule — tranh de quy vo han.
    Sau AD-9: apply_sense (chu ben phai + loai cau) chi doi *target* cung span.
    Generic dai hon khong duoc nuot Names/glossary bat dau lech ben trong
    (QT prioritizedName).
    """
    edges: list[Edge] = []
    n = len(text)
    pos = 0
    in_quote = False
    while pos < n:
        cands = _candidates_at(dic, text, pos, patterns=patterns)
        if CJK_RE.match(text[pos]) or any(e.is_pattern for e in cands):
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
            else:
                best = apply_sense(best, text, in_quote=in_quote)
            edges.append(best)
            pos = longest
        else:
            e = _literal_edge(text, pos)
            for ch in text[pos:e.end]:
                if ch in "「『":
                    in_quote = True
                elif ch in "」』":
                    in_quote = False
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
        if j < n and e.target:
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
    text = DA_DA_RE.sub("đã", text)
    text = BI_BI_RE.sub("bị", text)
    text = DA_BI_DOAT_DA_RE.sub("đã bị đoạt", text)
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
    # M1: render theo greedy (parity QuickTrans). beam<=1 bo DP top-K —
    # margin/entropy chi can cho router M2 / explain.
    greedy_edges = greedy_path(dic, text)
    greedy_edges = _possessive_clan(greedy_edges, text)
    greedy_edges = _possessive_de(greedy_edges, text)
    greedy_edges = _dui_before_name(greedy_edges, text)
    # Rule chong lap: loai artifact trung target giua hai edge ke nhau khi
    # nguon khong lap lai that (VD 'có chút'+'có chút lo lắng' -> giu cai sau).
    collapsed_count = 0
    collapsed_spans: list[tuple[int, int]] = []
    if collapse_reps:
        greedy_edges, collapsed_count, collapsed_spans = collapse_repetitions(greedy_edges, text)
    greedy_score = sum(e.score for e in greedy_edges)
    best = _Path(greedy_edges, greedy_score, False)
    if beam <= 1:
        margin, entropy, disagreement = 1.0, 0.0, 0.0
    else:
        paths = best_paths(dic, text, k=max(2, beam))
        if not paths:
            return VpDraft(text=text, spans=(), unknown_spans=(), single_char_ratio=0.0,
                           lattice_margin=0.0, lattice_entropy=0.0, warnings=("NO_PATH",))
        margin = (paths[0].score - paths[1].score) if len(paths) > 1 else float("inf")
        entropy = _entropy(paths)
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
