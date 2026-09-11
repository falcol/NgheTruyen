"""Chon nghia cung span: chu ben phai/trai + loai cau. Khong doi segmentation (AD-9)."""
from __future__ import annotations

from dataclasses import replace

from .patterns import PRONOUNS, VERBS

# 得 + prefix nay -> "được" (khong phien am "đến"/"đắc").
_DE_DUOC = ("天地", "厚爱", "厚愛")
_CLAUSE_END = frozenset("。！\n」』")
_QUESTION_MARK = frozenset("？吗麼么")
_SPEECH_AFTER_DAO = frozenset("：:「『")
_STOP_AFTER = frozenset("。！？，,、；;：:\n」』")
# Cum 对+dai tu trong corpus = "đối với X" — convert cat "với".
_DUI_PRONOUN = {
    "对自己": "đối mình",
    "对你": "đối ngươi",
    "对我": "đối ta",
    "对他": "đối hắn",
    "对她": "đối nàng",
    "对它": "đối nó",
    "对您": "đối ngài",
}
# 会 + trai: tuong lai / kha nang.
_FUTURE_LEFT = ("明天", "昨天", "今天", "今年", "将", "將", "一定", "可能")
_FUTURE_RIGHT = frozenset("被让讓")
# Hat the (1 chu sau AD-9). 的/地 van DROP_PARTICLES.
_ASPECT = {
    "了": "đã",
    "着": "đang",
    "著": "đang",
    "过": "rồi",
    "過": "rồi",
}
# Dong tu menh de (rong hon VERBS {v} nam/nem).
_CLAUSE_VERBS = VERBS | frozenset(
    "来去到说問问听想用做打开吃坐站被让讓逼叫走看"
)
# 的话: particle thi vs "loi" (nghe/tin/ngat).
_DEHUA_SPEECH = ("听到", "听着", "相信", "打断", "听")
# 吞: VP "nuốt" dung khi dong tu; HV "thôn" khi hop the/ten (吞灵, 吴吞).
_TUN_NUOT_RIGHT = frozenset("下了掉进入咽服着著过過")
_TUN_NUOT_OBJ = ("口水", "唾沫", "丹药", "丹藥", "药丸", "藥丸")
_TUN_NUOT_LEFT = ("一口", "生", "活", "被", "给", "給")


def clause_is_question(text: str, pos: int) -> bool:
    """Tu `pos` den het menh de co dau hoi / 吗/么."""
    i, n = pos, len(text)
    while i < n and text[i] not in _CLAUSE_END:
        if text[i] in _QUESTION_MARK:
            return True
        i += 1
    return False


def _is_cjk(ch: str) -> bool:
    o = ord(ch)
    return 0x3400 <= o <= 0x4DBF or 0x4E00 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF


def _left_cjk(text: str, pos: int, n: int = 4) -> str:
    """N chu CJK ngay truoc `pos`, dung o hat/punct menh de."""
    chars: list[str] = []
    i = pos
    while i > 0 and len(chars) < n:
        i -= 1
        ch = text[i]
        if ch in _STOP_AFTER:
            break
        if _is_cjk(ch):
            chars.append(ch)
        elif chars:
            break
    chars.reverse()
    return "".join(chars)


def _starts_verb(seg: str) -> bool:
    return bool(seg) and (seg[:2] in _CLAUSE_VERBS or seg[:1] in _CLAUSE_VERBS)


def apply_sense(edge, text: str, *, in_quote: bool = False):
    """Doi target neu cung source + ngu canh khop. Pattern edge: bo qua."""
    if edge.is_pattern:
        return edge
    src = text[edge.start : edge.end]
    if not edge.target and src not in _ASPECT:
        return edge
    rest = text[edge.end :]
    left = _left_cjk(text, edge.start)
    new = _sense_target(
        src,
        rest,
        left,
        in_quote=in_quote,
        clause_pos=edge.start,
        text=text,
        cur=edge.target,
    )
    if new is None or new == edge.target:
        return edge
    return replace(edge, target=new)


def _xiang_after_pronoun(rest: str) -> str | None:
    """nhớ neu het menh de; tưởng neu dai tu + dong tu; None neu NP (想他一代)."""
    if rest.startswith("自己"):
        after = rest[2:]
    elif rest[:1] in PRONOUNS:
        after = rest[1:]
    else:
        return None
    if not after or after[0] in _STOP_AFTER:
        return "nhớ"
    if _starts_verb(after):
        return "tưởng"
    return None


def _sense_target(
    src: str,
    rest: str,
    left: str,
    *,
    in_quote: bool,
    clause_pos: int,
    text: str,
    cur: str,
) -> str | None:
    nxt = rest[:1]
    nxt2 = rest[:2]
    if src == "一把" and (nxt2 in VERBS or nxt in VERBS):
        return "một cái"
    if src in _DUI_PRONOUN:
        return _DUI_PRONOUN[src]
    if src == "都对" and (nxt in PRONOUNS or rest.startswith("自己")):
        return "đều đối"
    if src == "对" and (nxt in PRONOUNS or rest.startswith("自己")):
        return "đối"
    if src == "得" and rest.startswith(_DE_DUOC):
        return "được"
    if src == "多少" and clause_is_question(text, clause_pos):
        return "bao nhiêu"
    if src == "道" and nxt in _SPEECH_AFTER_DAO:
        return "nói"
    if src in _ASPECT:
        return _ASPECT[src]
    # 怎么会 / 怎么可能会: giu span AD-9, rhetorical lai (khong se).
    if "怎么" in src and "会" in src:
        if "sẽ" in cur:
            return cur.replace("sẽ", "lại", 1)
        return None
    # 可能会: giu span, 会 trong cum = future se (khong hoi).
    if src == "可能会" or src.endswith("可能会"):
        if "hội" in cur:
            return cur.replace("hội", "sẽ", 1)
        return None
    if src == "会":
        if any(left.endswith(w) for w in _FUTURE_LEFT) or nxt in _FUTURE_RIGHT:
            return "sẽ"
        return None
    if src == "的话":
        ctx = _left_cjk(text, clause_pos, n=8)
        if any(w in ctx for w in _DEHUA_SPEECH):
            return "lời"
        return "thì"
    if src == "想":
        if rest.startswith("要") or rest.startswith("和") or _starts_verb(rest):
            return None
        return _xiang_after_pronoun(rest)
    if src == "是":
        if (left[-1:] in PRONOUNS or left.endswith("自己")) and (
            nxt in _FUTURE_RIGHT or _starts_verb(rest)
        ):
            return "đúng là"
        return None
    if src == "吞" and cur == "nuốt":
        if any(left.endswith(w) for w in _TUN_NUOT_LEFT):
            return None
        if nxt in _TUN_NUOT_RIGHT or rest.startswith(_TUN_NUOT_OBJ):
            return None
        return "thôn"
    # 吞吃 (VP "nuốt ăn") nuốt ten: 吴吞吃着 → Ngô thôn ăn.
    if src == "吞吃" and cur.startswith("nuốt") and left and _is_cjk(left[-1]):
        return "thôn ăn"
    return None
