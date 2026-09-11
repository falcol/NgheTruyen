"""LuatNhan pattern rules ({s}=so, {n}=ten, {p}=cum CJK, {v}=dong tu).

{p}/{v}: convert inversion + khung (桌上的{p}, 一把{v}). {0} van skip.

Key chua {s}/{n} duoc compile thanh regex anchor tai vi tri match trong van
ban da simplify. Capture duoc dich quy nguoc qua trie (tat pattern — chong
de quy) roi thay vao template target: {s}/{n} = slot dau tien loai do,
{1}..{k} = slot thu k theo thu tu xuat hien.

Key {0} VAN SKIP: 24.8k rule qua de over-match va engine cu cung bo qua.
Metachar regex co y trong key — ( ) [ ] | ? * — duoc giu nguyen; con lai
duoc escape. Rule regex hong bi lo.

Bucket theo ky tu dau (DIGIT/CJK/letter cu the) de greedy_path khong phai
th thu toan bo rule tai moi vi tri.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

CJK_CLASS = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
NUM_CHARS = "0-9０-９零一二三四五六七八九十百千万亿兩两壹贰叁肆伍陆柒捌玖拾佰仟"
NUM_RE = f"[{NUM_CHARS}]+(?:[.,．][{NUM_CHARS}]+)*"
SLOT_RE = re.compile(r"\{(s|n|p|v)\}")
TARGET_REF_RE = re.compile(r"\{(s|n|p|v|\d+)\}")
# {v}: dong tu sau 一把 — alternation, dai truoc ngan. Khong dung {p} (nuot danh tu).
VERBS = frozenset({
    "拽住", "抓住", "拉住", "揪住", "扯住", "拖住", "按住", "捂住", "抱住",
    "拿住", "握住", "掐住", "扭住", "拎住", "逮住", "捉住", "勒住", "夹住",
    "捧住", "推开", "拉开", "扯开", "扔掉", "丢掉", "塞进", "塞入", "搂住",
    "抓起", "提起", "拎起", "抢过", "夺过", "拔下", "捏紧", "抓紧", "扶住",
    "拽", "揪", "抓", "拉", "拿", "握", "扭", "打", "推", "按", "拖", "扯",
    "扔", "丢", "塞", "搂", "拍", "抢", "夺", "拔", "捏", "扶", "掀", "摔",
    "砸", "踢", "摘", "揽",
})
# {p} dung truoc hat/vi tu: 桌上的地图就看, 桌上的书籍看完
# khong nuot '地图就看' / '书籍看完' / '凌天上的' / '动作后'.
P_STOP = (
    "就了的着過过吗呢吧啊嘛呀"
    "便则卻却但而并且也又还都才已正"
    "把被给让向从在是有没不"
    "看拿放走来去到说問问听想用做打开吃坐站"
    "上里裡下中前后後"
)
PASS_CHARS = frozenset("()[]|?*+")

# {n} phai la entity that (ten rieng Names.txt trust 20, manual >=25) hoac dai
# tu — khong phai moi cum CJK la danh tu ('無視自己' khong phai ten nguoi).
ENTITY_TRUSTS = frozenset({20.0, 25.0, 100.0, 1000.0})
# Hau to tu tien (Chivi-lite): {n} chap duoc khi chu cuoi thuoc set, khong can Names.
ENTITY_SUFFIXES = frozenset("宗门派殿阁宫师尊帝皇城山峰谷界域洲")
# {n} / sense 想: chu don. Khong dua 老师/同学 vao day — se nuot {n}.
PRONOUNS = frozenset("我你他她它您咱俺儂汝爾")

DIGIT_KEY = "\x00digit"
CJK_KEY = "\x00cjk"

NUM_START_RE = re.compile(f"[{NUM_CHARS}]")


def is_num_start(ch: str) -> bool:
    return bool(NUM_START_RE.match(ch))


def _verb_slot_pattern() -> str:
    """{v} chi dong tu that — 一把剑 khong match. Dai truoc: 扔掉|扔."""
    alts = sorted(VERBS, key=lambda s: (-len(s), s))
    return "(" + "|".join(re.escape(v) for v in alts) + ")"


@dataclass(frozen=True)
class PatternRule:
    key: str  # da simplified — de trace
    regex: re.Pattern
    slots: tuple[str, ...]  # 's'/'n' theo thu tu capture group
    target: str  # template chua {s}/{n}/{1}..
    precedence: tuple  # (layer, trust, load_index) — nhu literal edge
    policy: str
    starts: tuple[str, ...]  # khoa bucket


def compile_rule(zh_simp: str, target: str, precedence: tuple, policy: str) -> PatternRule | None:
    """Compile 1 key template -> PatternRule; None neu khong phai pattern hoac hong."""
    if "{0}" in zh_simp or not SLOT_RE.search(zh_simp):
        return None
    slots: list[str] = []
    parts: list[str] = []
    last = 0
    for m in SLOT_RE.finditer(zh_simp):
        parts.append(_escape_literal(zh_simp[last : m.start()]))
        kind = m.group(1)
        slots.append(kind)
        # Slot cuoi key (khong con literal neo phia sau) -> lazy: '小{n}' chi bat
        # 1 ky tu ten, khong nuot tron '天的事情辦好了'. Slot giua key -> greedy +
        # backtracking regex tu dieu chinh do dai ('{n}山脚下' -> '华山' + '山脚下').
        anchored = m.end() < len(zh_simp)
        if kind == "n":
            # 1-4 CJK: ten nguoi/dia danh thuong 2-3 chu; cap ngan de '{n}自己'
            # khong nuot ca menh gioi ('看到凌天居然無視自己').
            parts.append(f"([{CJK_CLASS}]{{1,4}})" if anchored else f"([{CJK_CLASS}]{{1,4}}?)")
        elif kind == "p":
            # Cum CJK 1-4, khong chua P_STOP. Unanchored van greedy (1-4)
            # de bat '幼儿书籍'; hat/vi tu cat cuoi NP.
            parts.append(rf"((?:(?![{P_STOP}])[{CJK_CLASS}]){{1,4}})")
        elif kind == "v":
            parts.append(_verb_slot_pattern())
        else:
            # lazy phai la {1,8}? — them '?' vao sau NUM_RE ('[..]+') se bien
            # ca nhom thanh optional, match rong -> edge dai 0 -> loop vo han
            parts.append(f"({NUM_RE})" if anchored else f"([{NUM_CHARS}]{{1,8}}?)")
        last = m.end()
    parts.append(_escape_literal(zh_simp[last:]))
    try:
        regex = re.compile("".join(parts))
    except re.error:
        return None
    return PatternRule(zh_simp, regex, tuple(slots), target, precedence, policy, _start_buckets(zh_simp))


def _escape_literal(seg: str) -> str:
    return "".join(ch if ch in PASS_CHARS else re.escape(ch) for ch in seg)


def _start_buckets(key: str) -> tuple[str, ...]:
    """Ky tu dau co the xuat hien khi match — de bucket hoa rule."""
    starts: list[str] = []
    i, n = 0, len(key)
    while i < n:
        m = SLOT_RE.match(key, i)
        if m:
            starts.append(DIGIT_KEY if m.group(1) == "s" else CJK_KEY)
            return tuple(dict.fromkeys(starts))
        ch = key[i]
        if ch == "(":
            j = key.find(")", i)
            if j == -1:
                return (CJK_KEY, DIGIT_KEY)
            for alt in key[i + 1 : j].split("|"):
                if alt:
                    starts.append(alt[0])
            if j + 1 < n and key[j + 1] == "?":
                i = j + 2
                continue
            return tuple(dict.fromkeys(starts))
        if ch == "[":
            j = key.find("]", i)
            if j == -1:
                return (CJK_KEY,)
            if j + 1 < n and key[j + 1] == "?":
                i = j + 2
                continue
            starts.extend(key[i + 1 : j][:4])
            return tuple(dict.fromkeys(starts))
        starts.append(ch)
        return tuple(dict.fromkeys(starts))
    return (CJK_KEY, DIGIT_KEY)


def build_pattern_index(rules: list[PatternRule]) -> dict[str, list[PatternRule]]:
    idx: dict[str, list[PatternRule]] = {}
    for r in rules:
        for s in r.starts:
            idx.setdefault(s, []).append(r)
    return idx


def fill_target(rule: PatternRule, match: re.Match, translate) -> str:
    """Thay {s}/{n}/{k} trong target bang capture da dich (translate: str->str)."""
    translations = [translate(match.group(i + 1) or "") for i in range(len(rule.slots))]

    def sub(m: re.Match) -> str:
        ref = m.group(1)
        if ref.isdigit():
            idx = int(ref) - 1
            return translations[idx] if 0 <= idx < len(translations) else ""
        for j, kind in enumerate(rule.slots):
            if kind == ref:
                return translations[j]
        return ""

    out = TARGET_REF_RE.sub(sub, rule.target)
    return re.sub(r"\s{2,}", " ", out).strip()
