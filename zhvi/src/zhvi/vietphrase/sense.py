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
# 了 sau gioi tu noi cho (在了/于了): particle, khong aspect "đã".
_LOCATIVE_BEFORE_LE = frozenset("在于於")
# Dong tu menh de (rong hon VERBS {v} nam/nem).
_CLAUSE_VERBS = VERBS | frozenset(
    "来去到说問问听想用做打开吃坐站被让讓逼叫走看"
)
# 的话: sau dong tu nghe/nho (听到/记得...) la "loi noi" (possessive).
_DEHUA_SPEECH = ("听到", "听着", "相信", "打断", "听", "回味", "回忆", "想起", "记得", "记载", "说起", "谈起", "讲起")
_DEHUA_COND_LEFT = ("要是", "如果", "假如", "倘若", "要不", "若是", "若要", "若不")
_DEHUA_TOPIC_VERB = ("让", "使", "令", "说", "引起", "导致")
_DEHUA_BOUNDARY = frozenset("，；。！？,\n」』")
# 一跃 + 跳X (nhay vot + huong): 一跃 -> "nhay vot", 跳 giu bo huong.
_TIAO_AFTER_YIYUE = {
    "跳上": "lên", "跳下": "xuống", "跳起": "dậy", "跳出": "ra",
    "跳进": "vào", "跳入": "vào", "跳过": "qua",
    "跃上": "lên", "躍上": "lên", "跃下": "xuống", "躍下": "xuống",
}
# 第X + ton hieu/danh vi (thuy to, Than Ton...) -> de + so Han-Viet
# (de nhat..de thap bat...). Con lai (dot/lan/nguoi/vi/dai...) giu thu N.
_ORD_TITLE2 = (
    "始祖", "老祖", "神尊", "神皇", "神帝", "帝君", "大帝", "美人", "美女",
    "强者", "天才", "天骄", "高手", "宗主", "宗门", "掌门", "门主",
    "家主", "城主", "宫主", "圣主", "圣女", "圣子", "长老", "盟主", "族长",
)
_SINO_DIGIT = ("", "nhất", "nhị", "tam", "tứ", "ngũ", "lục", "thất", "bát", "cửu")
_CN_DIGIT = {
    "零": 0, "一": 1, "二": 2, "两": 2, "兩": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_CN_UNIT = {"十": 10, "百": 100, "千": 1000}


def _cn_numeral(seg: str) -> int | None:
    """So Han 1..9999 trong edge 第X; None neu khong phai so thuan."""
    if not seg:
        return None
    for w in ("万", "萬"):
        if w in seg:
            hi, _, lo = seg.partition(w)
            h = _cn_numeral(hi) if hi else 1
            l = _cn_numeral(lo) if lo else 0
            if h is None or l is None:
                return None
            return h * 10000 + l
    total, num = 0, 0
    for ch in seg:
        if ch in _CN_DIGIT:
            num = _CN_DIGIT[ch]
        elif ch == "零":
            continue
        elif ch in _CN_UNIT:
            total += (num or 1) * _CN_UNIT[ch]
            num = 0
        else:
            return None
    return total + num if (total or num) else None


# Thanh ngu 4 chu de vo (dau bi dinh vao edge truoc, VD 人望 + 望其项背).
# Chi thanh ngu curated — khong phai moi tu dai trong trie (VD 就忍不住,
# 果然如此, 个人观点 chia doi duoc, khong bao ve). Tu 不... do _stolen_bu.
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
    }
)


def ordinal_tail(seg: str) -> str | None:
    """Edge 第X<C> (VD 第一掌): tra C neu X la so Han thuan, else None."""
    if len(seg) >= 3 and seg[0] == "第" and _cn_numeral(seg[1:-1]) is not None:
        return seg[-1:]
    return None


def dehua_conditional(text: str, start: int, end: int) -> bool:
    """的话 tai [start,end): True neu doc conditional (split literal),
    False neu possessive/topic (giu pattern X的{p} dao ngu).

    - Trai co dong tu nghe/tin (听到...) -> loi noi (possessive).
    - Trai co 要是/如果/... -> conditional.
    - Sau la bien menh de: neu mo menh de tiep lay 话 lam chu ngu
      (让/使/令/说...) -> possessive; con lai (dai tu, 只要, het cau)
      -> conditional. Khong bien -> possessive.
    """
    left = _left_cjk(text, start, n=8)
    if any(w in left for w in _DEHUA_SPEECH):
        return False
    if any(w in left for w in _DEHUA_COND_LEFT):
        return True
    after = text[end:]
    if not after or after[0] in _DEHUA_BOUNDARY:
        nxt = after[1:] if after else ""
        if nxt.startswith(_DEHUA_TOPIC_VERB):
            return False
        return True
    return False


def _sino_ordinal(n: int | None) -> str | None:
    """1..9999 -> nhat..de thap bat...; None khi ngoai mien (giu dich cu)."""
    if n is None or n < 1 or n > 9999:
        return None
    if n == 10:
        return "thập"
    if n < 10:
        return _SINO_DIGIT[n]
    if n < 20:
        return "thập " + _SINO_DIGIT[n - 10]
    if n < 100:
        hi, lo = divmod(n, 10)
        s = _SINO_DIGIT[hi] + " thập"
        return s if lo == 0 else s + " " + _SINO_DIGIT[lo]
    if n < 1000:
        hi, lo = divmod(n, 100)
        s = _SINO_DIGIT[hi] + " bách"
        if lo == 0:
            return s
        if lo < 10:
            return s + " linh " + _SINO_DIGIT[lo]
        return s + " " + _sino_ordinal(lo)
    hi, lo = divmod(n, 1000)
    s = _SINO_DIGIT[hi] + " thiên"
    if lo == 0:
        return s
    if lo < 10:
        return s + " linh " + _SINO_DIGIT[lo]
    return s + " " + _sino_ordinal(lo)
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
    if src == "一跃" and nxt in ("跳", "跃", "躍"):
        return "nhảy vọt"
    # 一跃 + 跳X: bo nhay trung, giu huong (一跃跳上 -> nhay vot len).
    if src in _TIAO_AFTER_YIYUE and left.endswith("一跃"):
        return _TIAO_AFTER_YIYUE[src]
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
    if src.startswith("第") and len(src) > 1:
        sino = _sino_ordinal(_cn_numeral(src[1:]))
        if sino is not None:
            if rest[:2] in _ORD_TITLE2:
                return "đệ " + sino
            # 第一人 = de nhat nhan (danh hieu); 第N人 con lai la thu tu.
            if sino == "nhất" and rest[:1] == "人" and (
                len(rest) == 1 or rest[1] in _STOP_AFTER or not _is_cjk(rest[1])
            ):
                return "đệ " + sino
    if src in _ASPECT:
        if src == "了" and left[-1:] in _LOCATIVE_BEFORE_LE:
            return ""
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
