"""Legacy VietPhrase trie used by vietphrase.app file translation.

Longest span wins. At the same key, higher priority wins, then the later entry.
Standalone particles are dropped. LuatNhan ``{0}`` patterns run only when the
capture is a pronoun, a number, or a dictionary hit allowed by the level.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from vp.textutil import (
    HANVIET_PATCH,
    KINSHIP_ALIAS_SUFFIXES,
    convert_to_simplified,
    finish_hanviet,
    finish_legacy,
    has_cjk,
    is_cjk,
    title_case_vietnamese,
)

PRONOUNS = frozenset(
    "你自己\t大家伙儿\t同学们\t大伙儿\t老师们\t自个儿\t他人\t他们\t你们\t别人\t同学\t咱们\t她们\t它们\t您们\t我们\t旁人\t老师\t自己\t诸位\t他\t你\t咱\t她\t它\t您\t我\t朕".split(
        "\t"
    )
)

_PARTICLES = frozenset("的旳了着著地得过過嘛呢吧啊呀啦呐吶呗唄哩哟喲咯喽嘍罢罷")
_NUMERIC_CAPTURE_RE = re.compile(
    r"^[零〇一二两兩三四五六七八九十百千万萬亿億半几幾多\d点點刻分秒时時小时小時天日月年岁歲余餘來来上下左右前后後余餘]+$"
)
_NUMERIC_VALUE_RE = re.compile(r"[零〇一二两兩三四五六七八九十百千万萬亿億半几幾多\d]")
_VIETPHRASE_SOURCE_RE = re.compile(r"^VietPhrase_[1-4]\.txt$", re.IGNORECASE)
# Whole-gloss English leaks in the phrase corpora, e.g. 杀了我=Kill Me.
# A gloss is dropped only when every word is in this set, so undiacritic
# Vietnamese ("ra", "mang theo") and Hán Việt names ("Dung Linh") stay.
_ENGLISH_GLOSS_WORDS = frozenset(
    {
        "attack",
        "boss",
        "cooldown",
        "damage",
        "hit",
        "kill",
        "killer",
        "me",
        "one",
        "penta",
        "quadra",
        "quest",
        "skill",
        "skills",
    }
)
# Dictionary glosses of function phrases. A novel-scan name must not replace these.
_GRAMMAR_GLOSS_RE = re.compile(
    r"^(?:thời điểm|thời gian|lúc|khi|tuyệt đối|hoàn toàn|vô duyên vô cớ|trong thời gian|thông cảm)\b",
    re.IGNORECASE,
)
_PAREN_RE = re.compile(r"\s*\(.*?\)\s*")
_CLAUSE_BOUNDARY_RE = re.compile(r"[，。？！；：,.!?;:…—)\]\u00bb\u201d\u2019>」』】〉]")
_LATIN_NUM_RE = re.compile(r"[A-Za-z0-9]")
_NEXT_STATION_PARTICLE_RE = re.compile(r"^(?:呗|唄|吧|啊|呀|嘛|呢|啦)$")

# Tails and exception lists copied from zhvi longest-match guards.
_BOUND_COMPOUND_TAILS = frozenset("脉力气云术丹阵魄灵光界门乎意")
_LOCATIVE_EDGE_ENDS = frozenset("中上下内外前后里间")
_CLOSED_YOU = frozenset({"没有", "所有", "只有", "还有"})
# Bare 独子 before a verb is the homophone of 独自. 他的独子 is a longer
# dictionary key and stays "only son". Clause-final 独子 stays a noun.
_DUZI_ADVERB_NEXT = frozenset(
    "一站走坐去来回行立留在闯进入出跑飞躲藏看望听等往向离返归居住"
    "战守待练修开说笑哭赶追逃停靠躺跪跳爬骑奔至到喝沉摆活饮呆"
    "占乱为作面玩斩缠扔前弹"
)
_CLOSED_BU = frozenset({"要不", "这不", "那不", "毫不", "莫不", "并不"})
_PRONOUN_SKIP_TAIL = frozenset("们們的")
_NAME_GLUE_REST = frozenset({"已经", "已經"})
_NAME_PARTICLES = frozenset("的得地了着过")
_KIN_TITLES = ("姐姐", "哥哥", "妹妹", "弟弟")
_CLAN_SKIP = frozenset({"回家", "国家", "全家"})
_DE_SKIP_RIGHT = frozenset({"话", "話", "时候", "時候"})
# Adjective + 的 + 地方 stays Chinese order ("mùi ngon chỗ"). These two
# are modifiers, not owners: 味道好的地方, 太差的地方.
_PLACE_MODIFIER = frozenset({"味道好", "太差"})
_TIME_AFTER_DE = frozenset(
    {"晚上", "夜晚", "早上", "中午", "下午", "白天", "夜里", "夜裏", "清晨", "傍晚", "凌晨"}
)
_IDIOMS = frozenset(
    {
        "望其项背",
        "望尘莫及",
        "莫名其妙",
        "出乎意料",
        "理所当然",
        "心服口服",
        "触目惊心",
        "铺天盖地",
        "震耳欲聋",
        "目瞪口呆",
        "哑口无言",
        "手足无措",
        "筋疲力尽",
        "全力以赴",
        "千钧一发",
        "任人鱼肉",
    }
)
_PROTECTED_OVERFLOWS = frozenset(
    {
        "知情人",
        "要么",
        "解决",
        "口中",
        "任人鱼肉",
        "烟雾弹",
        "跟着",
        "有点",
        "印记",
        "圆润",
        "女朋友",
        "停了下来",
        "题目",
    }
)


class _Node:
    __slots__ = ("c", "v", "p", "o", "has")

    def __init__(self) -> None:
        self.c: dict[str, _Node] = {}
        self.v = ""
        self.p = 0
        self.o = -1
        self.has = False


class _PatNode:
    __slots__ = ("c", "patterns", "templates")

    def __init__(self) -> None:
        self.c: dict[str, _PatNode] = {}
        self.patterns: list[tuple[str, str]] | None = None
        self.templates: list[str] | None = None


@dataclass(slots=True)
class _Step:
    kind: str
    start: int
    end: int
    value: str
    pri: int
    cap_start: int = 0
    cap_end: int = 0
    template: str = ""

    @property
    def length(self) -> int:
        return self.end - self.start


@dataclass(slots=True)
class _Tok:
    start: int
    end: int
    zh: str
    value: str
    pri: int
    drop: bool
    kind: str


def _normalize_variant(value: str) -> str:
    return re.sub(r"\s+", " ", _PAREN_RE.sub(" ", value or "")).strip()


def extract_meaning(raw: str) -> str:
    if "\u271a[" in raw or "+[" in raw:
        t1 = raw.find("\\t1.")
        if t1 != -1:
            meat = raw[t1 + 4 :].strip()
            end = re.search(r"\\n|//", meat)
            if end:
                meat = meat[: end.start()]
            semi = meat.find(";")
            if semi != -1:
                meat = meat[:semi]
            meat = _PAREN_RE.sub(" ", meat).strip()
            if meat:
                return meat
        hv = raw.find("Hán Việt:")
        if hv != -1:
            hv_val = raw[hv + 9 :].strip()
            hv_end = re.search(r"\\[nt]|//", hv_val)
            if hv_end:
                hv_val = hv_val[: hv_end.start()]
            hv_val = re.split(r"[;；]", hv_val)[0].strip()
            if hv_val:
                return hv_val
        stripped = re.sub(r"[\u271a+]\s*\[[^\]]*\]\s*", "", raw)
        stripped = re.sub(r"Hán Việt:\s*\S+\s*", "", stripped).strip()
        stripped = re.sub(r"\\[nt]", " ", stripped).strip()
        if stripped:
            semi2 = stripped.find(";")
            if semi2 != -1:
                stripped = stripped[:semi2].strip()
            stripped = _PAREN_RE.sub(" ", stripped).strip()
            if stripped:
                return stripped
    dslash = raw.find("//")
    first = raw[:dslash].strip() if dslash != -1 else raw
    alt = re.search(r"[/|]", first)
    return first[: alt.start()].strip() if alt else first


def _english_gloss(value: str) -> bool:
    if not value or any(ord(ch) > 127 for ch in value):
        return False
    words = re.findall(r"[A-Za-z]+", value)
    return bool(words) and all(word.lower() in _ENGLISH_GLOSS_WORDS for word in words)


def _grammar_gloss(value: str) -> bool:
    return bool(value) and bool(_GRAMMAR_GLOSS_RE.match(value.strip()))


def _overlay_hides_peak(key: str, value: str) -> bool:
    """内劲巅峰=Nội Kình Điên Phong must not replace 巅峰=đỉnh phong."""
    return key.endswith("巅峰") and "đỉnh phong" not in value.casefold()


def _overlay_replaces_grammar(engine: Engine, key: str, value: str) -> bool:
    """A name overlay must not replace a function-phrase dictionary gloss."""
    hit = engine.exact_entry(key)
    if hit is None:
        return False
    gloss, pri = hit
    if pri >= 20 or not gloss or gloss[:1].isupper():
        return False
    if value.casefold() == gloss.casefold():
        return False
    return _grammar_gloss(gloss)


def first_meaning(raw: str, key_len: int, source: str) -> str:
    if "\u271a[" in raw or "+[" in raw:
        return extract_meaning(raw)
    dslash = raw.find("//")
    first = raw[:dslash].strip() if dslash != -1 else raw.strip()
    if not first:
        return ""
    vietphrase = bool(_VIETPHRASE_SOURCE_RE.match(source or "")) and key_len >= 2
    if not vietphrase:
        return _normalize_variant(extract_meaning(first))
    for part in re.split(r"[/|]", first):
        norm = _normalize_variant(part)
        if norm and not _english_gloss(norm):
            return norm
    return ""


def parse_dict_lines(text: str, priority: int, source: str) -> list[tuple[str, str, int, str]]:
    rows: list[tuple[str, str, int, str]] = []
    for line in text.split("\n"):
        line = line.strip().lstrip("\ufeff")
        if not line or line[0] == "#" or line.startswith("//"):
            continue
        eq = line.find("=")
        if eq < 1:
            continue
        zh = line[:eq].strip()
        vi_raw = line[eq + 1 :].strip()
        if "{0}" in zh:
            rows.append((zh, re.sub(r"\s*\*$", "", vi_raw), priority, source))
            continue
        meaning = first_meaning(vi_raw, len(zh), source)
        if meaning:
            rows.append((zh, meaning, priority, source))
    return rows


def parse_quality_overrides(text: str) -> list[tuple[str, str, int, str]]:
    rows: list[tuple[str, str, int, str]] = []
    for line in text.split("\n"):
        line = line.strip().lstrip("\ufeff")
        if not line or line[0] == "#" or line.startswith("//"):
            continue
        eq = line.find("=")
        if eq < 1:
            continue
        pri = 10
        rest = line[eq + 1 :].strip()
        tab = rest.rfind("\t")
        if tab != -1 and rest[tab + 1 :].strip().isdigit():
            pri = int(rest[tab + 1 :].strip())
            rest = rest[:tab].strip()
        rows.extend(parse_dict_lines(line[:eq].strip() + "=" + rest + "\n", pri, "QualityOverrides.txt"))
    return rows


def _is_numeric_capture(text: str) -> bool:
    normalized = re.sub(r"\s+", "", text or "")
    return bool(normalized) and bool(_NUMERIC_CAPTURE_RE.match(normalized)) and bool(
        _NUMERIC_VALUE_RE.search(normalized)
    )


def _clause_boundary(ch: str) -> bool:
    return not ch or bool(_CLAUSE_BOUNDARY_RE.match(ch))


def _neighbor_char(text: str, index: int, step: int) -> str:
    i = index
    while 0 <= i < len(text):
        if text[i] not in " \n\t":
            return text[i]
        i += step
    return ""


class Engine:
    def __init__(
        self,
        root: _Node,
        phienam: dict[str, str],
        pat_prefix: _PatNode | None,
        pat_suffix: _PatNode | None,
        trad_map: dict[str, str],
        *,
        simplified: bool,
        luat_nhan: int,
    ) -> None:
        self.root = root
        self.phienam = phienam
        self.pat_prefix = pat_prefix
        self.pat_suffix = pat_suffix
        self.trad_map = trad_map
        self.simplified = simplified
        self.luat_nhan = max(0, min(3, luat_nhan))

    @classmethod
    def build(
        cls,
        records: list[tuple[str, str, int, str]],
        trad_map: dict[str, str] | None = None,
        *,
        simplified: bool = True,
        luat_nhan: int = 2,
        custom: list[tuple[str, str]] | None = None,
    ) -> Engine:
        mapping = trad_map or {}
        converted: list[tuple[str, str, int, str]] = []
        original: list[tuple[str, str, int, str]] = []
        patterns: list[tuple[str, str, str]] = []
        for key, value, pri, source in records:
            orig = key
            simp = convert_to_simplified(orig, mapping, simplified)
            if "{0}" in simp:
                idx = simp.find("{0}")
                patterns.append((simp[:idx], simp[idx + 3 :], value))
            elif simp != orig:
                converted.append((simp, value, pri, orig))
            else:
                original.append((simp, value, pri, orig))
        ordered = converted + original
        root = _Node()
        for index, (key, value, pri, _orig) in enumerate(ordered):
            _upsert(root, key, value, pri, index)
        if custom:
            for key, value in custom:
                simp = convert_to_simplified(key.strip(), mapping, simplified)
                if simp and value.strip():
                    _force(root, simp, value.strip(), 999)
        phienam: dict[str, str] = {}
        for key, value, pri, orig in ordered:
            if len(key) == 1 and key == orig and pri <= 1 and value:
                phienam[key] = value
        for ch, hv in HANVIET_PATCH.items():
            current = phienam.get(ch)
            if not current or has_cjk(current):
                phienam[ch] = hv
        pat_prefix, pat_suffix = _build_patterns(patterns)
        return cls(
            root,
            phienam,
            pat_prefix,
            pat_suffix,
            mapping,
            simplified=simplified,
            luat_nhan=luat_nhan,
        )

    def convert(self, text: str) -> str:
        return convert_to_simplified(text, self.trad_map, self.simplified)

    def exact_entry(self, key: str) -> tuple[str, int] | None:
        node = self.root
        for ch in key:
            nxt = node.c.get(ch)
            if nxt is None:
                return None
            node = nxt
        if node.has:
            return node.v, node.p
        return None

    def exact_priority(self, key: str) -> int | None:
        hit = self.exact_entry(key)
        return None if hit is None else hit[1]

    def translate(self, text: str, overlay: list[tuple[str, str, int]] | None = None) -> str:
        if text is None:
            return ""
        if not text:
            return text
        text = self.convert(text)
        index = _overlay_index(overlay or [], self)
        parts: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            if is_cjk(text[i]):
                start = i
                while i < n and is_cjk(text[i]):
                    i += 1
                lead = text[start - 1] if start else ""
                run = self._translate_run(text[start:i], index, text[i:], lead)
                if run.strip() == "đứng" and _station_noun(text, start):
                    run = "trạm"
                parts.append(run)
            else:
                mixed = self._plain_step(text, i, n, index)
                if mixed.kind == "trie" and mixed.end > i and has_cjk(text[i : mixed.end]):
                    parts.append(mixed.value)
                    i = mixed.end
                    continue
                start = i
                while i < n and not is_cjk(text[i]):
                    i += 1
                parts.append(text[start:i])
        return finish_legacy(" ".join(parts))

    def hanviet(self, text: str) -> str:
        text = self.convert(text or "")
        alias = _hanviet_title(text, self.phienam)
        if alias:
            return alias
        parts: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            if is_cjk(text[i]):
                parts.append(self.phienam.get(text[i], text[i]))
                i += 1
            else:
                start = i
                while i < n and not is_cjk(text[i]):
                    i += 1
                parts.append(text[start:i])
        return finish_hanviet(" ".join(parts))

    def _capture_allowed(self, cap: str, pri: int) -> bool:
        if self.luat_nhan == 0:
            return False
        if cap in PRONOUNS:
            return True
        if self.luat_nhan >= 2 and pri >= 20:
            return True
        if self.luat_nhan >= 3 and pri >= 10:
            return True
        return False

    def _plain_step(
        self,
        text: str,
        pos: int,
        end_limit: int,
        overlay: dict[str, list[tuple[str, str, int]]] | None,
    ) -> _Step:
        trie = _trie_match(self.root, text, pos, end_limit)
        over = _overlay_match(text, pos, end_limit, overlay)
        best = _better(over, trie)
        if best and best.kind == "trie" and best.length >= 2 and best.pri < 20 and overlay:
            strong = _overlay_strong_start(text, pos + 1, best.end, end_limit, overlay)
            if strong > pos:
                trie = _trie_match(self.root, text, pos, strong)
                over = _overlay_match(text, pos, strong, overlay)
                best = _better(over, trie)
        if best:
            return best
        ch = text[pos]
        return _Step("phienam", pos, pos + 1, self.phienam.get(ch, ch), 0)

    def _translate_run(
        self,
        text: str,
        overlay: dict[str, list[tuple[str, str, int]]] | None,
        follow: str = "",
        lead: str = "",
    ) -> str:
        toks: list[_Tok] = []
        i = 0
        n = len(text)
        while i < n:
            step = self._step_at(text, i, n, overlay)
            if step.length <= 0:
                toks.append(_Tok(i, i + 1, text[i], text[i], 0, False, "literal"))
                i += 1
                continue
            zh = text[step.start : step.end]
            if step.kind == "pattern":
                cap = text[step.cap_start : step.cap_end]
                rendered = step.template.replace("{0}", self._translate_run(cap, overlay), 1)
                toks.append(_Tok(step.start, step.end, zh, rendered, step.pri, False, "pattern"))
            else:
                particle = len(zh) == 1 and zh in _PARTICLES
                value = "" if particle else (step.value if step.value is not None else zh)
                if not toks and zh in _QUOTE_SENSE and lead in _QUOTE_LEAD:
                    value = _QUOTE_SENSE[zh]
                    particle = False
                if zh == "独子" and _duzi_adverb(text, step.end):
                    alone = self.exact_entry("独自")
                    value = alone[0] if alone and alone[0] else "một mình"
                elif zh == "原因" and _yuanyin_willing(self, text, step.start, step.end, follow):
                    willing = self.exact_entry("愿意")
                    value = willing[0] if willing and willing[0] else "đồng ý"
                elif zh == "一般" and _simile_yiban(text, step.start, step.end):
                    value = "vậy"
                elif zh in _WORDS_OF and value in _BARE_PRONOUN and _speech_words(text, step.start):
                    value = _WORDS_OF[zh]
                elif zh == "会" and text[step.end : step.end + 2] == "水月":
                    value = "về"
                elif zh == "开了" and _dismissed_person(text, step.end):
                    value = "đuổi"
                elif zh == "拷" and _capital_name_follows(self, text, step.end):
                    value = "còng"
                elif (
                    zh == "的话"
                    and value.casefold() == "nếu"
                    and toks
                    and toks[-1].end == step.start
                ):
                    prev = toks[-1]
                    if not _dehua_conditional(toks) and (
                        _is_possessive_head(prev) or _dehua_say(prev.zh)
                    ):
                        if _is_possessive_head(prev):
                            toks[-1] = _Tok(
                                prev.start,
                                step.end,
                                prev.zh + zh,
                                f"lời của {prev.value}",
                                step.pri,
                                False,
                                "trie",
                            )
                            i += step.length
                            continue
                        value = "lời"
                    elif _dehua_conditional(toks):
                        value = ""
                elif (
                    zh == "在意"
                    and toks
                    and toks[-1].zh == "再"
                    and toks[-1].end == step.start
                    and step.end == len(text)
                    and _follow_still(follow)
                ):
                    prev = toks[-1]
                    toks[-1] = _Tok(
                        prev.start,
                        step.end,
                        "再在意",
                        "dù để ý đến mấy",
                        step.pri,
                        False,
                        "trie",
                    )
                    i += step.length
                    continue
                elif (
                    zh == "有效"
                    and toks
                    and toks[-1].zh == "绝对"
                    and toks[-1].end == step.start
                ):
                    prev = toks[-1]
                    toks[-1] = _Tok(
                        prev.start,
                        step.end,
                        "绝对有效",
                        "tuyệt đối có hiệu lực",
                        step.pri,
                        False,
                        "trie",
                    )
                    i += step.length
                    continue
                toks.append(_Tok(step.start, step.end, zh, value, step.pri, particle, step.kind))
            i += step.length
        toks = _merge_clan(toks)
        toks = _merge_possessive(toks)
        toks = _nest_dantian_locative(toks)
        return " ".join(tok.value for tok in toks if not tok.drop and tok.value)

    def _step_at(
        self,
        text: str,
        pos: int,
        end_limit: int,
        overlay: dict[str, list[tuple[str, str, int]]] | None,
    ) -> _Step:
        base = self._plain_step(text, pos, end_limit, overlay)
        if self.luat_nhan and self.pat_prefix is not None:
            prefix = self._prefix_pattern(text, pos, end_limit, overlay)
            if prefix and (base.kind != "trie" or prefix.length > base.length):
                return prefix
        if self.luat_nhan and self.pat_suffix is not None and self._suffix_capture_ok(text, pos, base):
            suffix = _suffix_pattern(self.pat_suffix, text, pos + base.length, end_limit)
            if suffix:
                suf_len, template = suffix
                # 凌天派过来 is "Lăng Thiên phái", not "phái Lăng Thiên".
                # 把/将{0}派过来 stays on the prefix pattern.
                follows_dispatch = text.startswith(
                    ("过来", "来", "过去", "去", "出去", "出"),
                    pos + base.length + suf_len,
                )
                if not (template == "phái {0}" and follows_dispatch):
                    return _Step(
                        "pattern",
                        pos,
                        pos + base.length + suf_len,
                        "",
                        base.pri,
                        pos,
                        pos + base.length,
                        template,
                    )
        return base

    def _suffix_capture_ok(self, text: str, pos: int, base: _Step) -> bool:
        if self.luat_nhan == 0 or base.length <= 0:
            return False
        cap = text[pos : pos + base.length]
        if _is_numeric_capture(cap):
            return True
        return self._capture_allowed(cap, base.pri)

    def _pattern_capture(
        self,
        text: str,
        start: int,
        end: int,
        end_limit: int,
        overlay: dict[str, list[tuple[str, str, int]]] | None,
    ) -> _Step | None:
        if self.luat_nhan == 0 or start >= end:
            return None
        cap = text[start:end]
        if _is_numeric_capture(cap):
            return _Step("numeric", start, end, "", 0)
        step = self._plain_step(text, start, end_limit, overlay)
        if step.kind == "trie" and step.end == end and self._capture_allowed(cap, step.pri):
            return step
        return None

    def _splits_longer_tail(
        self,
        text: str,
        suffix_start: int,
        suffix_len: int,
        end_limit: int,
        overlay: dict[str, list[tuple[str, str, int]]] | None,
    ) -> bool:
        step = self._plain_step(text, suffix_start, end_limit, overlay)
        return step.kind == "trie" and step.end > suffix_start + suffix_len

    def _prefix_pattern(
        self,
        text: str,
        pos: int,
        end_limit: int,
        overlay: dict[str, list[tuple[str, str, int]]] | None,
    ) -> _Step | None:
        node = self.pat_prefix
        if node is None:
            return None
        i = pos
        best: _Step | None = None
        while i < end_limit and text[i] in node.c:
            node = node.c[text[i]]
            i += 1
            if not node.patterns:
                continue
            for suffix, template in node.patterns:
                if not suffix:
                    continue
                search_from = i
                while True:
                    suf_idx = text.find(suffix, search_from, end_limit)
                    if suf_idx < 0 or suf_idx + len(suffix) > end_limit:
                        break
                    cap_len = suf_idx - i
                    allowed = (
                        self._pattern_capture(text, i, suf_idx, end_limit, overlay)
                        if 0 < cap_len <= 8
                        else None
                    )
                    if allowed:
                        if self._splits_longer_tail(text, suf_idx, len(suffix), end_limit, overlay):
                            search_from = suf_idx + 1
                            continue
                        total = (i - pos) + cap_len + len(suffix)
                        if best is None or total > best.length:
                            best = _Step(
                                "pattern",
                                pos,
                                pos + total,
                                "",
                                0,
                                i,
                                suf_idx,
                                template,
                            )
                        break
                    search_from = suf_idx + 1
        return best


def _upsert(root: _Node, key: str, value: str, pri: int, order: int) -> None:
    node = root
    for ch in key:
        nxt = node.c.get(ch)
        if nxt is None:
            nxt = _Node()
            node.c[ch] = nxt
        node = nxt
    if not node.has or pri > node.p or (pri == node.p and order >= node.o):
        node.v = value
        node.p = pri
        node.o = order
        node.has = True


def _force(root: _Node, key: str, value: str, pri: int) -> None:
    node = root
    for ch in key:
        nxt = node.c.get(ch)
        if nxt is None:
            nxt = _Node()
            node.c[ch] = nxt
        node = nxt
    node.v = value
    node.p = pri
    node.has = True


def _build_patterns(patterns: list[tuple[str, str, str]]) -> tuple[_PatNode | None, _PatNode | None]:
    if not patterns:
        return None, None
    prefix = _PatNode()
    suffix = _PatNode()
    prefix_count = 0
    suffix_count = 0
    for pre, suf, template in patterns:
        if pre:
            node = prefix
            for ch in pre:
                nxt = node.c.get(ch)
                if nxt is None:
                    nxt = _PatNode()
                    node.c[ch] = nxt
                node = nxt
            if node.patterns is None:
                node.patterns = []
            node.patterns.append((suf, template))
            prefix_count += 1
        else:
            node = suffix
            for ch in suf:
                nxt = node.c.get(ch)
                if nxt is None:
                    nxt = _PatNode()
                    node.c[ch] = nxt
                node = nxt
            if node.templates is None:
                node.templates = []
            node.templates.append(template)
            suffix_count += 1
    return (prefix if prefix_count else None, suffix if suffix_count else None)


def _protected_name_end(root: _Node, text: str, pos: int) -> int | None:
    """Longest Names-style hit at pos: priority >= 20 and a capitalised reading."""
    node = root
    last: int | None = None
    j = pos
    while j < len(text):
        nxt = node.c.get(text[j])
        if nxt is None:
            break
        node = nxt
        j += 1
        if j - pos >= 2 and node.has and node.p >= 20 and node.v[:1].isupper():
            last = j
    return last


def _swallows_protected_name(root: _Node, text: str, start: int, end: int, pri: int, value: str) -> bool:
    """A generic phrase must not cover the head of a name that continues past it.

    七彩琉璃=lưu ly bảy màu would otherwise eat 琉璃 of 琉璃宫=Lưu Ly Cung.
    The name is kept and the phrase falls back to the shorter 七彩=thất thải.
    """
    if end - start < 2:
        return False
    if pri >= 20 and value[:1].isupper():
        return False
    for i in range(start + 1, end):
        name_end = _protected_name_end(root, text, i)
        if name_end is None or name_end <= end:
            continue
        # 琉璃宫 is 3+ and may start mid-span. A 2-char name is only
        # 水月: 回水/会水 must not eat 水 (nước đọng, biết bơi).
        if name_end - i >= 3 or (i == end - 1 and text[i:name_end] == "水月"):
            return True
    return False


def _is_protected_name(pri: int, value: str) -> bool:
    return pri >= 20 and bool(value) and value[:1].isupper()


def _longest_word_len(root: _Node, text: str, pos: int) -> int:
    node = root
    best = 0
    j = pos
    n = len(text)
    while j < n:
        nxt = node.c.get(text[j])
        if nxt is None:
            break
        node = nxt
        j += 1
        if node.has:
            best = j - pos
    return best


def _stolen_compound(root: _Node, text: str, start: int, end: int) -> bool:
    """Generic span steals the head of a shorter compound that runs past it."""
    if end - start < 2:
        return False
    n = len(text)
    for i in range(start + 1, end):
        node = root
        for j in range(i, min(i + 4, n)):
            nxt = node.c.get(text[j])
            if nxt is None:
                break
            node = nxt
            wlen = j - i + 1
            word_end = j + 1
            if not node.has or wlen < 2 or word_end <= end:
                continue
            if text[word_end - 1] not in _BOUND_COMPOUND_TAILS:
                continue
            # 着气=xả giận is a noisy bigram. It must not veto 看着/跟着
            # the way 力气/灵气 veto a real stolen head.
            if text[i:word_end] == "着气":
                continue
            if (
                i == end - 1
                and wlen == 2
                and end - start >= 3
                and _longest_word_len(root, text, end) >= 2
            ):
                continue
            if (
                end - start == 2
                and text[end - 1] in _LOCATIVE_EDGE_ENDS
                and i == end - 1
                and wlen == 2
            ):
                continue
            if i == end - 1 and end - start == 2 and text[start:end] in _CLOSED_YOU:
                continue
            return True
    return False


def _protected_overflow(text: str, start: int, end: int) -> bool:
    """Short span steals the head of a curated compound."""
    if end - start < 2:
        return False
    n = len(text)
    for i in range(start + 1, end):
        for length in (2, 3, 4):
            stop = i + length
            if stop > n:
                break
            if stop <= end:
                continue
            if text[i:stop] in _PROTECTED_OVERFLOWS:
                return True
    return False


def _stolen_bu(root: _Node, text: str, start: int, end: int) -> bool:
    """Span ending in 不 steals 不 from a longer word that starts there."""
    if end - start < 2 or text[end - 1] != "不":
        return False
    if text[start:end] in _CLOSED_BU:
        return False
    return _longest_word_len(root, text, end - 1) > end - start


def _stolen_pronoun_np(root: _Node, text: str, start: int, end: int) -> bool:
    """Pronoun+X steals the head of a compound that runs past the span."""
    if end - start < 2 or text[start] not in PRONOUNS:
        return False
    if text[start + 1] in _PRONOUN_SKIP_TAIL:
        return False
    i = start + 1
    min_wlen = 2 if text[i] == "不" else 3
    node = root
    n = len(text)
    for j in range(i, min(i + 8, n)):
        nxt = node.c.get(text[j])
        if nxt is None:
            break
        node = nxt
        wlen = j - i + 1
        word_end = j + 1
        if not node.has or wlen < min_wlen or word_end <= end:
            continue
        return True
    return False


def _idiom_overflow(root: _Node, text: str, start: int, end: int) -> bool:
    """Two-character span covers the first character of a curated idiom."""
    if end - start != 2 or end >= len(text):
        return False
    tail = end - 1
    if text[tail : tail + 4] not in _IDIOMS:
        return False
    return _longest_word_len(root, text, tail) >= 4


def _name_function_glue(root: _Node, text: str, start: int, end: int) -> bool:
    """Name glued to 已经. Split so the name and 已经 match apart."""
    name_end = _protected_name_end(root, text, start)
    if name_end is None or name_end <= start or name_end >= end:
        return False
    return text[name_end:end] in _NAME_GLUE_REST


def _is_custom_name_node(node: _Node, source: str) -> bool:
    return (
        node.has
        and node.p >= 999
        and bool(node.v)
        and node.v[:1].isupper()
        and not _NAME_PARTICLES.intersection(source)
    )


def _custom_name_collision(root: _Node, text: str, start: int, end: int) -> bool:
    """Glue of at most 3 characters steals the head of a Custom name."""
    if end - start > 3:
        return False
    n = len(text)
    for i in range(start + 1, end):
        node = root
        j = i
        while j < n:
            nxt = node.c.get(text[j])
            if nxt is None:
                break
            node = nxt
            j += 1
            if j - i < 2 or j <= end:
                continue
            if _is_custom_name_node(node, text[i:j]):
                return True
    return False


def _bad_de_glue(text: str, start: int, end: int) -> bool:
    """的实力 and 巅峰的 hide the noun and the stage word."""
    return text[start:end] in {"的实力", "巅峰的"}


def _de_steals_dantian(text: str, start: int, end: int) -> bool:
    """心脏的=tim must not swallow 的 before 丹田."""
    return end - start >= 2 and text[end - 1] == "的" and text.startswith("丹田", end)


def _bad_vi_gloss(value: str) -> bool:
    """Corrupt corpora glosses. A shorter entry then applies."""
    return "ngững" in (value or "").casefold()


def _zheqi_steals_qi(root: _Node, text: str, start: int, end: int) -> bool:
    """着气=xả giận steals 气 from 气势/气息/气旋/气派/气泡."""
    if text[start:end] != "着气":
        return False
    return _longest_word_len(root, text, start + 1) >= 2


def _taidang_steals(text: str, start: int, end: int) -> bool:
    """太当=quá sảng khoái steals 当 from 当回事."""
    return text[start:end] == "太当" and text.startswith("回事", end)


def _count_sheng_steals_office(text: str, start: int, end: int) -> bool:
    """几个省 must not eat 省 of 省厅/省内/省份/省里/省长."""
    return text[start:end] in {"几个省", "好几个省"} and end < len(text) and text[end] in "厅内份里长"


def _kid_zi_split(text: str, start: int, end: int) -> bool:
    """个小孩 steals 孩 from 孩子, leaving 子=tử."""
    return (
        end - start >= 3
        and text[start:end].endswith("小孩")
        and end < len(text)
        and text[end] == "子"
    )


def _reject_trie_span(root: _Node, text: str, step: _Step) -> bool:
    if _swallows_protected_name(root, text, step.start, step.end, step.pri, step.value):
        return True
    if _is_protected_name(step.pri, step.value):
        return False
    start, end = step.start, step.end
    return (
        _stolen_compound(root, text, start, end)
        or _protected_overflow(text, start, end)
        or _stolen_bu(root, text, start, end)
        or _stolen_pronoun_np(root, text, start, end)
        or _idiom_overflow(root, text, start, end)
        or _name_function_glue(root, text, start, end)
        or _custom_name_collision(root, text, start, end)
        or _bad_de_glue(text, start, end)
        or _de_steals_dantian(text, start, end)
        or _splits_standing(text, start, end)
        or _splits_plural_pronoun(text, start, end)
        or _bad_vi_gloss(step.value)
        or _taidang_steals(text, start, end)
        or _zheqi_steals_qi(root, text, start, end)
        or _count_sheng_steals_office(text, start, end)
        or _kid_zi_split(text, start, end)
    )


def _trie_match(root: _Node, text: str, pos: int, end_limit: int) -> _Step | None:
    node = root
    found: list[_Step] = []
    j = pos
    while j < end_limit:
        nxt = node.c.get(text[j])
        if nxt is None:
            break
        node = nxt
        j += 1
        if node.has:
            found.append(_Step("trie", pos, j, node.v, node.p))
    for step in reversed(found):
        if not _reject_trie_span(root, text, step):
            return step
    return None


_STAGE_HEAD_RE = re.compile(
    r"(?:^|\s)(?:sơ|trung|hậu|tiền|đỉnh)\s+(?:kỳ|phong)\b",
    re.IGNORECASE,
)


def _is_possessive_head(tok: _Tok) -> bool:
    if not tok.value or tok.kind == "pattern":
        return False
    if tok.zh in PRONOUNS or tok.zh == "自己":
        return True
    if any(tok.zh.endswith(k) for k in _KIN_TITLES):
        return True
    # 先天中期 / 内劲巅峰 / 先天境界 are realms, not owners.
    if tok.zh.endswith("期") or tok.zh.endswith("巅峰") or _STAGE_HEAD_RE.search(tok.value):
        return False
    if "cảnh giới" in tok.value.casefold():
        return False
    return tok.value[:1].isupper()


def _is_clan_name(tok: _Tok) -> bool:
    zh = tok.zh
    if tok.kind == "pattern" or not (2 <= len(zh) <= 3 and zh.endswith("家")):
        return False
    if zh in _CLAN_SKIP:
        return False
    if not tok.value or not tok.value[:1].isupper():
        return False
    if tok.pri >= 999 and not _NAME_PARTICLES.intersection(zh):
        return True
    return tok.pri >= 20


def _merge_clan(toks: list[_Tok]) -> list[_Tok]:
    """Pronoun + surname X家 -> 'X gia của pronoun'."""
    out: list[_Tok] = []
    i = 0
    n = len(toks)
    while i < n:
        tok = toks[i]
        if tok.zh in PRONOUNS and tok.value and i + 1 < n:
            nxt = toks[i + 1]
            if nxt.start == tok.end and _is_clan_name(nxt):
                out.append(
                    _Tok(
                        tok.start,
                        nxt.end,
                        tok.zh + nxt.zh,
                        f"{nxt.value} của {tok.value}",
                        nxt.pri,
                        False,
                        "trie",
                    )
                )
                i += 2
                continue
        out.append(tok)
        i += 1
    return out


_DANTIAN_LOC = {
    "丹田内": "đan điền",
    "丹田中": "đan điền",
    "丹田之中": "đan điền",
    "丹田之内": "đan điền",
    "丹田之里": "đan điền",
}
_BODY_SITE = frozenset({"腹部", "胸口", "眉心", "手臂", "头部", "小腹", "心口"})
_COUNT_GE = frozenset("一二两三四五六七八九十百千几数多")
_PLACE_PREFIXES = ("tại chính ", "ở chính ", "tại ", "ở ", "nơi ")


def _strip_place_prefix(value: str) -> str:
    text = value.strip()
    folded = text.casefold()
    for prefix in _PLACE_PREFIXES:
        if folded.startswith(prefix):
            return text[len(prefix) :].strip()
    return text


def _dantian_owner_phrase(left: _Tok, noun: str) -> str | None:
    """丹田内=trong đan điền leaves the owner outside «trong»."""
    val = (left.value or "").strip()
    if not val or left.drop:
        return None
    zh = left.zh
    folded = val.casefold()
    if zh.endswith("处") or folded.startswith("nơi "):
        place = _strip_place_prefix(val)
        if not place:
            return None
        return f"trong {noun} ở {place}"
    if zh.startswith("在") and len(zh) > 1:
        core = _strip_place_prefix(val)
        if core and core.casefold() != folded:
            return f"trong {noun} của {core}"
    if zh == "心脏":
        return f"trong {noun} của {val}"
    if zh in _BODY_SITE:
        return f"trong {noun} ở {val}"
    if zh.startswith("第") or folded.startswith("thứ "):
        return f"trong {noun} {val}"
    if zh.endswith("个") and all(ch in _COUNT_GE for ch in zh[:-1]):
        return f"trong {val} {noun}"
    if _is_possessive_head(left) or zh in {"自己", "自身"}:
        return f"trong {noun} của {val}"
    return None


def _loc_owner_index(out: list[_Tok], dantian_start: int) -> int | None:
    if not out:
        return None
    last = out[-1]
    if last.zh in ("的", "旳") and last.end == dantian_start and len(out) >= 2:
        owner = out[-2]
        if owner.end == last.start and owner.value and not owner.drop:
            return len(out) - 2
        return None
    if last.end == dantian_start and last.value and not last.drop and last.zh not in ("的", "旳"):
        return len(out) - 1
    return None


def _nest_dantian_locative(toks: list[_Tok]) -> list[_Tok]:
    out: list[_Tok] = []
    for tok in toks:
        noun = _DANTIAN_LOC.get(tok.zh)
        if not noun or not tok.value or not tok.value.casefold().startswith("trong"):
            out.append(tok)
            continue
        owner_i = _loc_owner_index(out, tok.start)
        if owner_i is None:
            out.append(tok)
            continue
        phrase = _dantian_owner_phrase(out[owner_i], noun)
        if not phrase:
            out.append(tok)
            continue
        start = out[owner_i].start
        if " của " not in phrase and owner_i > 0:
            name = out[owner_i - 1]
            if name.end == start and name.value and (_is_possessive_head(name) or name.zh in {"自己", "自身"}):
                phrase = f"{phrase} của {name.value}"
                start = name.start
                owner_i -= 1
        del out[owner_i:]
        out.append(_Tok(start, tok.end, tok.zh, phrase, tok.pri, False, "trie"))
    return out


def _merge_possessive(toks: list[_Tok]) -> list[_Tok]:
    """Name or pronoun + 的 + noun -> 'noun của name'. Time nouns use ở."""
    out: list[_Tok] = []
    i = 0
    n = len(toks)
    while i < n:
        tok = toks[i]
        if tok.zh in ("的", "旳") and tok.end - tok.start == 1 and out and i + 1 < n:
            left = out[-1]
            right = toks[i + 1]
            if (
                left.end == tok.start
                and tok.end == right.start
                and right.zh == "地方"
                and left.zh in _PLACE_MODIFIER
                and left.value
            ):
                out[-1] = _Tok(
                    left.start,
                    right.end,
                    left.zh + tok.zh + right.zh,
                    f"{right.value} {left.value}",
                    right.pri,
                    False,
                    "trie",
                )
                i += 2
                continue
            if (
                left.end == tok.start
                and tok.end == right.start
                and right.value
                and right.kind != "pattern"
                and _is_possessive_head(left)
                and right.zh not in _DE_SKIP_RIGHT
            ):
                if right.zh in _TIME_AFTER_DE:
                    joined = f"{right.value} ở {left.value}"
                else:
                    joined = f"{right.value} của {left.value}"
                out[-1] = _Tok(
                    left.start,
                    right.end,
                    left.zh + tok.zh + right.zh,
                    joined,
                    right.pri,
                    False,
                    "trie",
                )
                i += 2
                if (
                    i < n
                    and toks[i].zh == "更强"
                    and toks[i].start == right.end
                    and out[-1].zh.endswith("实力")
                ):
                    toks[i].value = "mạnh hơn"
                continue
        out.append(tok)
        i += 1
    return out


def _better(nxt: _Step | None, best: _Step | None) -> _Step | None:
    if nxt is None:
        return best
    if best is None:
        return nxt
    if nxt.length != best.length:
        return nxt if nxt.length > best.length else best
    if nxt.pri != best.pri:
        return nxt if nxt.pri > best.pri else best
    return best


def _overlay_index(
    entries: list[tuple[str, str, int]],
    engine: Engine,
) -> dict[str, list[tuple[str, str, int]]] | None:
    if not entries:
        return None
    buckets: dict[str, list[tuple[str, str, int]]] = {}
    for zh, vi, pri in entries:
        key = engine.convert(zh.strip())
        value = vi.strip()
        if not key or not value or _overlay_hides_peak(key, value) or _overlay_replaces_grammar(engine, key, value):
            continue
        buckets.setdefault(key[0], []).append((key, value, pri))
    return buckets or None


def _overlay_match(
    text: str,
    pos: int,
    end_limit: int,
    overlay: dict[str, list[tuple[str, str, int]]] | None,
) -> _Step | None:
    if not overlay or pos >= len(text):
        return None
    bucket = overlay.get(text[pos])
    if not bucket:
        return None
    best: _Step | None = None
    for zh, value, pri in bucket:
        end = pos + len(zh)
        if end > end_limit or text[pos:end] != zh:
            continue
        best = _better(_Step("trie", pos, end, value, pri), best)
    return best


def _overlay_strong_start(
    text: str,
    start: int,
    stop: int,
    end_limit: int,
    overlay: dict[str, list[tuple[str, str, int]]],
) -> int:
    for j in range(start, stop):
        bucket = overlay.get(text[j])
        if not bucket:
            continue
        for zh, _value, pri in bucket:
            if len(zh) < 2 or pri < 20:
                continue
            end = j + len(zh)
            if end <= end_limit and text[j:end] == zh:
                return j
    return -1


def _suffix_pattern(root: _PatNode, text: str, pos: int, end_limit: int) -> tuple[int, str] | None:
    node = root
    best: tuple[int, str] | None = None
    i = pos
    while i < end_limit and text[i] in node.c:
        node = node.c[text[i]]
        i += 1
        if not node.templates:
            continue
        length = i - pos
        for template in node.templates:
            if best is None or length > best[0]:
                best = (length, template)
    return best


def _splits_plural_pronoun(text: str, start: int, end: int) -> bool:
    """送我 must not eat 我 of 我们 and leave 们 as 'nhóm'."""
    if end - start < 2 or end >= len(text) or text[end] != "们":
        return False
    return text[end - 1] in "我你他她它"


def _follow_still(follow: str) -> bool:
    nxt = follow.lstrip(" \t")
    return nxt.startswith(("，依然", "，还是"))


def _dismissed_person(text: str, end: int) -> bool:
    """开了他 is 'fire him'. 开了他的手 is a longer word such as 切开了."""
    if end >= len(text) or text[end] not in "他她你我":
        return False
    after = text[end + 1] if end + 1 < len(text) else ""
    return after != "的"


def _splits_standing(text: str, start: int, end: int) -> bool:
    """前站着 is standing in front, not the station 前站.

    A span that ends on 门 and leaves 前站着 has taken 门 away from 门前站着.
    大门前 stays, because that span already includes 前.
    """
    if text[start:end] == "前站" and end < len(text) and text[end] == "着":
        return True
    return end - start >= 2 and text[end - 1] == "门" and text[end : end + 3] == "前站着"


_SIMILE_OPEN = ("好像", "仿佛", "如同", "犹如", "宛如", "宛若", "好似", "活像", "就像", "像是", "像")
_ORDINARY_YIBAN = frozenset("很太挺更最非不")
_BARE_PRONOUN = frozenset({"ta", "ngươi", "hắn", "nàng", "nó", "tôi", "mình"})
_WORDS_OF = {
    "我的话": "lời của ta",
    "你的话": "lời của ngươi",
    "他的话": "lời của hắn",
    "她的话": "lời của nàng",
    "它的话": "lời của nó",
}
_SPEECH_PREV = frozenset("听信把记当但断")
_SPEECH_BIGRAM = frozenset({"记住", "相信", "听到", "要听", "会听", "须听", "别把", "打断"})


def _simile_yiban(text: str, start: int, end: int) -> bool:
    """好像/仿佛/像 …一般 is 'like', not 一般=bình thường. 很一般 stays ordinary."""
    if text[start:end] != "一般":
        return False
    nxt = text[end] if end < len(text) else ""
    if nxt and nxt != "的":
        return False
    if start > 0 and text[start - 1] in _ORDINARY_YIBAN:
        return False
    window = text[:start]
    return any(op in window for op in _SIMILE_OPEN)


def _speech_words(text: str, start: int) -> bool:
    """听/但/clause-initial 我的话 is 'my words'. 要是我的话 stays the pronoun."""
    i = start - 1
    while i >= 0 and text[i] in "了着过的":
        i -= 1
    if i < 0:
        return True
    if text[i] in _SPEECH_PREV:
        return True
    return i >= 1 and text[i - 1 : i + 1] in _SPEECH_BIGRAM


_QUOTE_LEAD = frozenset({"", "\n", "\r", "“", '"', "「", "『"})
_QUOTE_SENSE = {"恩": "ừ", "嗯": "ừ", "喂": "alo"}
_DEHUA_COND = ("如果", "要是", "假如", "倘若", "若是", "万一", "如若", "就算", "即使", "哪怕")
_DEHUA_SAY = frozenset({"说", "讲", "道", "问", "喊", "叫", "言"})


def _dehua_say(zh: str) -> bool:
    return zh in _DEHUA_SAY or zh.endswith("说") or zh.endswith("讲")


def _dehua_conditional(toks: list[_Tok]) -> bool:
    """如果/要是 in the same clause keeps 的话 as 'nếu'."""
    parts: list[str] = []
    for tok in reversed(toks):
        if tok.value and _CLAUSE_BOUNDARY_RE.search(tok.value):
            break
        parts.append(tok.zh)
    blob = "".join(reversed(parts))
    return any(mark in blob for mark in _DEHUA_COND)


def _capital_name_follows(engine: Engine, text: str, end: int) -> bool:
    """拷 before a capitalized name is the handcuff verb, not 拷问."""
    for length in (2, 3, 4):
        if end + length > len(text):
            continue
        hit = engine.exact_entry(text[end : end + length])
        if hit and hit[1] >= 20 and hit[0][:1].isupper():
            return True
    return False


def _duzi_adverb(text: str, end: int) -> bool:
    return end < len(text) and text[end] in _DUZI_ADVERB_NEXT


_YUANYIN_WILLING_END = set("，。！？,.!?;；")


def _yuanyin_willing(engine: Engine, text: str, start: int, end: int, follow: str = "") -> bool:
    """只要 + tên + 原因 trước dấu câu là lỗi gõ 愿意, không phải «nguyên nhân»."""
    if text[start:end] != "原因":
        return False
    nxt = text[end] if end < len(text) else (follow[:1] if follow else "")
    if nxt not in _YUANYIN_WILLING_END:
        return False
    idx = text.rfind("只要", 0, start)
    if idx < 0:
        return False
    if idx > 0 and "\u4e00" <= text[idx - 1] <= "\u9fff":
        return False
    mid = text[idx + 2 : start]
    if not mid or len(mid) > 4 or any(ch in mid for ch in "的得地了着过"):
        return False
    hit = engine.exact_entry(mid)
    return bool(hit and hit[1] >= 20 and hit[0][:1].isupper())


def _station_noun(text: str, start: int) -> bool:
    if text[start : start + 1] != "站":
        return False
    nxt = _neighbor_char(text, start + 1, 1)
    if not _clause_boundary(nxt) and not _NEXT_STATION_PARTICLE_RE.match(nxt):
        return False
    return bool(_LATIN_NUM_RE.match(_neighbor_char(text, start - 1, -1)))


def _kinship_suffix(zh: str) -> tuple[str, str] | None:
    for pair in KINSHIP_ALIAS_SUFFIXES:
        if zh == pair[0] or (len(zh) > len(pair[0]) and zh.endswith(pair[0])):
            return pair
    return None


def _hanviet_chars(zh: str, phienam: dict[str, str]) -> str:
    return " ".join(phienam.get(ch, ch) for ch in zh)


def _hanviet_title(zh: str, phienam: dict[str, str]) -> str:
    pair = _kinship_suffix(zh)
    if not pair:
        return ""
    if zh == pair[0]:
        return finish_hanviet(pair[1])
    prefix = _hanviet_chars(zh[: -len(pair[0])], phienam)
    if not prefix or has_cjk(prefix):
        return ""
    return title_case_vietnamese(prefix) + " " + pair[1]
