"""Discovery toan truyen — sinh observation tho cho pha LEARN (story 3.1).

AD-4: discovery la pha LEARN, CHI DOC dictionary active — khong nap
observation vao engine, khong mutate trie/dictionary state.
AD-8: observation la state trong book SQLite, khong phai projection.
AD-18: counting tren text gian the + NFC (cung khong gian index voi trie);
``ngram_original`` giu dang goc first-seen lam provenance.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from zhvi.document import CJK_RE, parse_document
from zhvi.snapshot import decode_strict
from zhvi.state import ObservationRow, SourceRevisionRow, State
from zhvi.vietphrase.loader import Dictionary, normalize_nfc, to_simplified
from zhvi.vietphrase.lattice import vp_plan

NGRAM_MIN = 2
NGRAM_MAX = 8

# Seed heuristic ten rieng — CHI la tin hieu observation, khong sinh target
# (AD-6: target sources thuoc candidate builder story 3.2).
_PERSON_SURNAMES = frozenset(
    "王李张刘陈杨黄赵周吴徐孙马朱胡郭何林罗郑梁谢宋唐许韩冯邓曹彭曾肖田董潘袁蔡蒋余于杜叶程魏苏吕丁任卢姚沈钟姜崔谭陆范汪廖石金韦贾夏傅方白邹熊孟秦邱江尹薛闫段雷龙黎史陶贺毛郝顾龚邵万钱严覃武戴莫孔向汤"
)
_PLACE_SUFFIXES = frozenset("山城峰谷岛洲海江湖河潭洞穴宫殿楼阁台坊郡州县国家族")
_SECT_SUFFIXES = frozenset("派宗门教盟阁楼谷庄堂寺观庵")
_TECHNIQUE_SUFFIXES = frozenset("功法诀经术拳剑刀掌指腿步阵图录典章谱")
_REALM_PREFIXES = (
    "炼气", "筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫",
)
_REALM_SUFFIXES = frozenset("境期层重")
_PATTERN_ORDER = ("person", "place", "sect", "technique", "realm")

# Reuse CJK_RE range tu document.py — khong dinh nghia range moi.
_RUN_RE = re.compile(f"(?:{CJK_RE.pattern})+")


@dataclass(frozen=True)
class DiscoverySummary:
    source_revision_id: str
    dictionary_revision_id: str
    observations: int
    single_char_run: int
    unknown: int
    alt_segmentation: int
    repetition_unstable: int
    pattern_rows: int

    def to_json(self) -> dict:
        return {
            "source_revision": self.source_revision_id,
            "dictionary_revision": self.dictionary_revision_id,
            "observations": self.observations,
            "flags": {
                "single_char_run": self.single_char_run,
                "unknown": self.unknown,
                "alt_segmentation": self.alt_segmentation,
                "repetition_unstable": self.repetition_unstable,
            },
            "patterns": self.pattern_rows,
        }


@dataclass
class _Accum:
    """Bo dem mutable cho mot ngram tren toan van ban."""

    total: int = 0
    chapters: dict[int, int] = field(default_factory=dict)
    left: dict[str, int] = field(default_factory=dict)
    right: dict[str, int] = field(default_factory=dict)
    original: str = ""
    single_char_run: bool = False
    unknown: bool = False
    alt_segmentation: bool = False
    repetition_unstable: bool = False


def _merge_adjacent(spans: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Gop cac span don-ky tu lien ke thanh run fragmentation >= 2 ky tu."""
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and merged[-1][1] == start:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def _shannon(counts: dict[str, int]) -> float:
    """Entropy Shannon co so 2 tren phan phoi context (rong -> 0)."""
    total = sum(counts.values())
    if total == 0:
        return 0.0
    return -sum((c / total) * math.log2(c / total) for c in counts.values())


def _pattern_hits(gram: str) -> list[str]:
    hits: set[str] = set()
    if gram[0] in _PERSON_SURNAMES:
        hits.add("person")
    if gram[-1] in _PLACE_SUFFIXES:
        hits.add("place")
    if gram[-1] in _SECT_SUFFIXES:
        hits.add("sect")
    if gram[-1] in _TECHNIQUE_SUFFIXES:
        hits.add("technique")
    if gram.startswith(_REALM_PREFIXES) or gram[-1] in _REALM_SUFFIXES:
        hits.add("realm")
    return [p for p in _PATTERN_ORDER if p in hits]


def _obs_id(source_revision_id: str, gram: str) -> str:
    return hashlib.sha256(
        (source_revision_id + "\x00" + gram).encode("utf-8")
    ).hexdigest()


def run_discovery(
    state: State,
    *,
    source_revision: SourceRevisionRow,
    dictionary: Dictionary,
    dictionary_revision_id: str,
) -> DiscoverySummary:
    """Chay discovery 6 buoc tren mot source revision, ghi observations.

    Deterministic (AC 3.1.2): counting theo thu tu duyet node ordinal tang dan,
    JSON dump sort_keys, replace-not-append trong mot transaction.
    """
    text = decode_strict(
        Path(source_revision.snapshot_path).read_bytes(), source_revision.encoding
    )
    doc = parse_document(text)

    uni: dict[str, int] = {}
    bi: dict[tuple[str, str], int] = {}
    accs: dict[str, _Accum] = {}

    for node in doc.translatable_nodes():
        content = node.content  # property: raw_text da strip
        if not content:
            continue
        orig_nfc = normalize_nfc(content)
        simple = normalize_nfc(to_simplified(content, dictionary.trad_simp))
        # AD-9: to_simplified thay tung ky tu nen offset simplified == offset goc.
        draft = vp_plan(dictionary, content)
        # Ca unknown lan single-char edge deu can gop lien ke: mot ngram chi
        # nam "trong unknown/fragmented run" khi phu toan bo run da gop.
        unknown_iv = _merge_adjacent(
            [(s.source_start, s.source_end) for s in draft.unknown_spans]
        )
        single_iv = _merge_adjacent(
            [
                (s.source_start, s.source_end)
                for s in draft.spans
                if s.source_end - s.source_start == 1
            ]
        )
        collapsed_iv = list(draft.collapsed_spans)
        # Node-level signal: instability flag cho ca paragraph (tho nhung deterministic).
        alt_node = "SEGMENTATION_INSTABILITY" in draft.warnings

        for m in _RUN_RE.finditer(simple):
            run = m.group()
            base = m.start()
            for ch in run:
                uni[ch] = uni.get(ch, 0) + 1
            for i in range(len(run) - 1):
                key = (run[i], run[i + 1])
                bi[key] = bi.get(key, 0) + 1
            for n in range(NGRAM_MIN, NGRAM_MAX + 1):
                for i in range(len(run) - n + 1):
                    gram = run[i : i + n]
                    acc = accs.setdefault(gram, _Accum())
                    acc.total += 1
                    acc.chapters[node.chapter_id] = (
                        acc.chapters.get(node.chapter_id, 0) + 1
                    )
                    if i > 0:
                        acc.left[run[i - 1]] = acc.left.get(run[i - 1], 0) + 1
                    if i + n < len(run):
                        acc.right[run[i + n]] = acc.right.get(run[i + n], 0) + 1
                    if not acc.original:
                        acc.original = orig_nfc[base + i : base + i + n]
                    gs, ge = base + i, base + i + n
                    # Spec buoc 4: is_unknown = ngram CHUA ky tu thuoc unknown
                    # span (overlap) — khong yeu cau phu tron ca run.
                    if not acc.unknown and any(gs < e and s < ge for s, e in unknown_iv):
                        acc.unknown = True
                    # single_char_run: ngram phu tron mot doan fragmentation
                    # (chuoi >=2 entry mot ky tu lien ke) — containment.
                    if not acc.single_char_run and any(
                        s <= gs and ge <= e for s, e in single_iv
                    ):
                        acc.single_char_run = True
                    if not acc.repetition_unstable and any(
                        s <= gs and ge <= e for s, e in collapsed_iv
                    ):
                        acc.repetition_unstable = True
                    if alt_node:
                        acc.alt_segmentation = True

    n_total = sum(uni.values())
    rows: list[ObservationRow] = []
    for gram, acc in accs.items():
        # PMI(xy) = log2(count(xy) * N / (count(x) * count(y))); min_pmi = min
        # tren cac bigram lien ke ben trong ngram.
        min_pmi = min(
            math.log2(
                bi[(gram[j], gram[j + 1])] * n_total
                / (uni[gram[j]] * uni[gram[j + 1]])
            )
            for j in range(len(gram) - 1)
        )
        rows.append(
            ObservationRow(
                id=_obs_id(source_revision.id, gram),
                source_revision_id=source_revision.id,
                dictionary_revision_id=dictionary_revision_id,
                ngram=gram,
                ngram_original=acc.original,
                length=len(gram),
                total_count=acc.total,
                chapter_count=len(acc.chapters),
                chapters_json=json.dumps(
                    {str(k): v for k, v in sorted(acc.chapters.items())},
                    sort_keys=True,
                ),
                left_contexts_json=json.dumps(acc.left, sort_keys=True),
                right_contexts_json=json.dumps(acc.right, sort_keys=True),
                left_entropy=_shannon(acc.left),
                right_entropy=_shannon(acc.right),
                min_pmi=min_pmi,
                is_single_char_run=int(acc.single_char_run),
                is_unknown=int(acc.unknown),
                alt_segmentation=int(acc.alt_segmentation),
                repetition_unstable=int(acc.repetition_unstable),
                pattern_hits_json=json.dumps(_pattern_hits(gram)),
            )
        )

    state.replace_observations(source_revision.id, rows)
    return DiscoverySummary(
        source_revision_id=source_revision.id,
        dictionary_revision_id=dictionary_revision_id,
        observations=len(rows),
        single_char_run=sum(r.is_single_char_run for r in rows),
        unknown=sum(r.is_unknown for r in rows),
        alt_segmentation=sum(r.alt_segmentation for r in rows),
        repetition_unstable=sum(r.repetition_unstable for r in rows),
        pattern_rows=sum(1 for r in rows if r.pattern_hits_json != "[]"),
    )
