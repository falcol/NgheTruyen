"""Punctuation, Han-Viet casing, and source-file decoding."""

from __future__ import annotations

import re

CN_PUNCT = {
    "，": ",",
    "。": ".",
    "？": "?",
    "！": "!",
    "；": ";",
    "：": ":",
    "「": "\u201c",
    "」": "\u201d",
    "『": "\u2018",
    "』": "\u2019",
    "《": "\u00ab",
    "》": "\u00bb",
    "（": "(",
    "）": ")",
    "【": "[",
    "】": "]",
    "〈": "<",
    "〉": ">",
    "、": ",",
    "～": "~",
}
_CN_PUNCT_RE = re.compile("[" + "".join(CN_PUNCT) + "]")
_VI_LOWER = "a-zàáạảãăắằặẳẵâấầậẩẫđèéẹẻẽêếềệểễìíịỉĩòóọỏõôốồộổỗơớờợởỡùúụủũưứừựửữỳýỵỷỹ"
_CAP_SENTENCE_RE = re.compile(rf"(^|[.!?\n]\s*)([{_VI_LOWER}])")
_CAP_DIALOG_RE = re.compile(rf"([:：]\s*[\"'“‘「『]\s*)([{_VI_LOWER}])")
_CAP_CHAPTER_RE = re.compile(rf"(\bChương\s+\d+\s*:\s*)([{_VI_LOWER}])")
_DIALOG_SPACE_RE = re.compile(r"([:：])(?=[\"'“‘「『])")
_SPACE_BEFORE_CLOSE_RE = re.compile(r" ([.,!?;:)\]\u00bb\u201d\u2019>])")
_SPACE_AFTER_OPEN_RE = re.compile(r"([\(\[\u00ab\u201c\u2018<]) ")
_SPACE_BEFORE_NARROW_RE = re.compile(r" ([.,!?;:])")
_MULTI_SPACE_RE = re.compile(r" {2,}")
_NL_TRIM_RE = re.compile(r"[ \t]*\n[ \t]*")
_NL_COLLAPSE_RE = re.compile(r"\n{3,}")

HANVIET_PATCH = {
    "的": "đích",
    "了": "liễu",
    "旳": "đích",
    "宁": "ninh",
    "寧": "ninh",
    "㝉": "ninh",
    "靦": "điến",
    "䩄": "điến",
    "撝": "huy",
    "㧑": "huy",
    "灬": "quang",
}

# Longest kinship suffix first. Used only when the whole Han-Viet input is a title alias.
KINSHIP_ALIAS_SUFFIXES = (
    ("师叔祖", "sư thúc tổ"),
    ("師叔祖", "sư thúc tổ"),
    ("师叔母", "sư thúc mẫu"),
    ("師叔母", "sư thúc mẫu"),
    ("师叔", "sư thúc"),
    ("師叔", "sư thúc"),
    ("师兄", "sư huynh"),
    ("師兄", "sư huynh"),
    ("师姐", "sư tỷ"),
    ("師姐", "sư tỷ"),
    ("师弟", "sư đệ"),
    ("師弟", "sư đệ"),
    ("师妹", "sư muội"),
    ("師妹", "sư muội"),
    ("表哥", "biểu ca"),
    ("表姐", "biểu tỷ"),
    ("表弟", "biểu đệ"),
    ("表妹", "biểu muội"),
    ("堂哥", "đường ca"),
    ("堂姐", "đường tỷ"),
    ("堂弟", "đường đệ"),
    ("堂妹", "đường muội"),
    ("哥哥", "ca ca"),
    ("姐姐", "tỷ tỷ"),
    ("弟弟", "đệ đệ"),
    ("妹妹", "muội muội"),
    ("小姐", "tiểu thư"),
    ("公子", "công tử"),
    ("姑娘", "cô nương"),
    ("先生", "tiên sinh"),
    ("夫人", "phu nhân"),
    ("老头", "lão đầu"),
    ("老頭", "lão đầu"),
    ("某", "mỗ"),
    ("叔", "thúc"),
    ("哥", "ca"),
    ("姐", "tỷ"),
    ("爷", "gia"),
    ("爺", "gia"),
    ("娘", "nương"),
    ("伯", "bá"),
    ("嫂", "tẩu"),
)


def is_cjk(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    return (
        0x4E00 <= code <= 0x9FFF
        or 0x3400 <= code <= 0x4DBF
        or 0xF900 <= code <= 0xFAFF
        or 0x20000 <= code <= 0x2EE5F
        or 0x2F800 <= code <= 0x2FA1F
        or 0x30000 <= code <= 0x323AF
    )


def has_cjk(text: str) -> bool:
    return any(is_cjk(ch) for ch in text)


def load_trad_simp(raw: str) -> dict[str, str]:
    cleaned = raw.lstrip("\ufeff")
    cleaned = re.sub(r"[\r\n\s]", "", cleaned)
    chars = list(cleaned)
    if len(chars) % 2:
        chars.pop()
    mapping: dict[str, str] = {}
    for i in range(0, len(chars), 2):
        mapping[chars[i]] = chars[i + 1]
    return mapping


def convert_to_simplified(text: str, mapping: dict[str, str] | None, enabled: bool) -> str:
    if not mapping or not enabled or not text:
        return text
    out = []
    for ch in text:
        if ch == "么":
            out.append(ch)
        else:
            out.append(mapping.get(ch, ch))
    return "".join(out)


def normalize_punctuation(text: str) -> str:
    text = text.replace("……", "...").replace("——", "\u2014").replace("…", "...")
    return _CN_PUNCT_RE.sub(lambda m: CN_PUNCT[m.group(0)], text)


def clean_line_breaks(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = _NL_TRIM_RE.sub("\n", text)
    return _NL_COLLAPSE_RE.sub("\n\n", text)


def capitalize_sentences(text: str) -> str:
    text = _DIALOG_SPACE_RE.sub(r"\1 ", text)
    text = _CAP_SENTENCE_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    text = _CAP_DIALOG_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    text = _CAP_CHAPTER_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)
    return text


def title_case_vietnamese(raw: str) -> str:
    return re.sub(r"(^|\s)(\S)", lambda m: m.group(1) + m.group(2).upper(), raw or "")


def finish_legacy(text: str) -> str:
    text = normalize_punctuation(text)
    text = _SPACE_BEFORE_CLOSE_RE.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN_RE.sub(r"\1", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _SPACE_BEFORE_NARROW_RE.sub(r"\1", text)
    text = clean_line_breaks(text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()
    return capitalize_sentences(text)


def finish_hanviet(text: str) -> str:
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = normalize_punctuation(text)
    text = _SPACE_BEFORE_CLOSE_RE.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN_RE.sub(r"\1", text)
    text = clean_line_breaks(text)
    text = _MULTI_SPACE_RE.sub(" ", text).strip()
    return capitalize_sentences(text)


def cjk_score(text: str) -> int:
    score = 0
    for ch in text:
        if ch == "\ufffd":
            score -= 5
        elif 0x4E00 <= ord(ch) <= 0x9FFF:
            score += 1
    return score


def decode_source(data: bytes, encoding: str = "auto") -> str:
    if encoding == "utf-8":
        return data.decode("utf-8-sig")
    if encoding == "gbk":
        return data.decode("gb18030")
    if encoding == "big5":
        return data.decode("big5hkscs")
    if encoding != "auto":
        raise ValueError(f"encoding không hỗ trợ: {encoding}")
    if data.startswith(b"\xef\xbb\xbf"):
        return data.decode("utf-8-sig")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    gb = data.decode("gb18030", errors="replace")
    big5 = data.decode("big5hkscs", errors="replace")
    if cjk_score(big5) > cjk_score(gb):
        return big5
    return gb
