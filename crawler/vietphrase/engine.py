"""Greedy longest-match VietPhrase convert (QuickTrans-style)."""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import requests

from .sync_dicts import phienam_needs_refresh

DICT_DIR = Path(__file__).resolve().parent / "dicts"
DICT_BASE = "https://vietphrase.app/dicts"

# Manifest priority: higher wins on the same key. Custom overlay is above all.
DICT_FILES: list[tuple[str, int]] = [
    ("ChinesePhienAmWords.txt", 5),
    ("ChinesePhienAmWords_2.txt", 5),
    ("VietPhrase_1.txt", 10),
    ("VietPhrase_2.txt", 10),
    ("VietPhrase_3.txt", 10),
    ("VietPhrase_4.txt", 10),
    ("LuatNhan.txt", 15),
    ("Names.txt", 20),
    ("Names_2.txt", 20),
    ("QualityOverrides.txt", 25),
    ("ContextPatterns.txt", 25),
    ("trad-simp.txt", 0),  # mapping file, not a phrase dict
]
CUSTOM_FILE = "Custom.txt"
CUSTOM_PRI = 100

CN_PUNCT = {
    "，": ",",
    "。": ".",
    "？": "?",
    "！": "!",
    "；": ";",
    "：": ":",
    "「": "“",
    "」": "”",
    "『": "‘",
    "』": "’",
    "《": "«",
    "》": "»",
    "（": "(",
    "）": ")",
    "【": "[",
    "】": "]",
    "〈": "<",
    "〉": ">",
    "、": ",",
    "～": "~",
}
PUNCT_RE = re.compile("[" + re.escape("".join(CN_PUNCT)) + "]")
SPACE_BEFORE_PUNCT_RE = re.compile(r"\s+([,.!?;:”’…)%\]»])")
SPACE_AFTER_OPEN_RE = re.compile(r"([“‘(\[«])\s+")
MULTI_SPACE_RE = re.compile(r"[^\S\n]{2,}")
CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
TRAILING_PRI_RE = re.compile(r"\t\d+\s*$")
# Drop 1-char particles after longest match (QT). Keep 着/著/得 — expect uses lấy/đến.
DROP_PARTICLES = set("的旳了地过過嘛呢吧啊呀啦呐吶呗唄哩哟喲咯喽嘍")
CAP_RE = re.compile(
    r"(^|[.!?]\s*[”’\"']?\s*|\n\s*|[“‘\"']\s*)"
    r"([a-zàáạảãăắằặẳẵâấầậẩẫđèéẹẻẽêếềệểễìíịỉĩòóọỏõôốồộổỗơớờợởỡùúụủũưứừựửữỳýỵỷỹ])"
)


class _Node:
    __slots__ = ("c", "v", "p")

    def __init__(self) -> None:
        self.c: dict[str, _Node] = {}
        self.v: str | None = None
        self.p: int = -1


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def _load_trad_simp(path: Path) -> dict[str, str]:
    raw = "".join(_read_text(path).split())
    chars = list(raw)
    if len(chars) % 2:
        chars = chars[:-1]
    return {chars[i]: chars[i + 1] for i in range(0, len(chars), 2)}


def _first_meaning(raw: str) -> str:
    raw = TRAILING_PRI_RE.sub("", raw).strip()
    raw = raw.rstrip("*").strip()
    cut = raw.find("//")
    if cut != -1:
        raw = raw[:cut].strip()
    for sep in ("/", "|"):
        i = raw.find(sep)
        if i != -1:
            raw = raw[:i].strip()
            break
    return raw


def _upsert(root: _Node, zh: str, vi: str, pri: int) -> None:
    if not zh or not vi:
        return
    node = root
    for ch in zh:
        nxt = node.c.get(ch)
        if nxt is None:
            nxt = _Node()
            node.c[ch] = nxt
        node = nxt
    if node.v is None or pri >= node.p:
        node.v = vi
        node.p = pri


def _match(root: _Node, text: str, pos: int) -> tuple[int, str] | None:
    node = root
    last_end = -1
    last_val: str | None = None
    j = pos
    n = len(text)
    while j < n:
        nxt = node.c.get(text[j])
        if nxt is None:
            break
        node = nxt
        j += 1
        if node.v is not None:
            last_end = j
            last_val = node.v
    if last_val is not None and last_end > pos:
        return last_end, last_val
    return None


def _join_tokens(parts: list[str]) -> str:
    text = " ".join(p for p in parts if p != "")
    text = text.replace("……", "...").replace("…", "...").replace("——", "—")
    text = PUNCT_RE.sub(lambda m: CN_PUNCT.get(m.group(0), m.group(0)), text)
    text = SPACE_BEFORE_PUNCT_RE.sub(r"\1", text)
    text = SPACE_AFTER_OPEN_RE.sub(r"\1", text)
    text = MULTI_SPACE_RE.sub(" ", text)
    return text.strip()


POST_PROCESS_RULES: list[tuple[re.Pattern, str]] = []








def _post_process_vietnamese(text: str) -> str:
    for rx, repl in POST_PROCESS_RULES:
        text = rx.sub(repl, text)
    return text



class Engine:
    def __init__(self) -> None:
        self.root = _Node()
        self.trad_simp: dict[str, str] = {}
        self.ready = False

    def load(self, overlay: dict[str, str] | None = None) -> None:
        ensure_dicts()
        self.root = _Node()
        self.trad_simp = _load_trad_simp(DICT_DIR / "trad-simp.txt")
        for name, pri in DICT_FILES:
            if name == "trad-simp.txt":
                continue
            path = DICT_DIR / name
            self._load_phrase_file(path, pri)
        custom = DICT_DIR / CUSTOM_FILE
        if custom.is_file():
            self._load_phrase_file(custom, CUSTOM_PRI, simp_keys=True)
        if overlay:
            for zh, vi in overlay.items():
                simp = self.to_simplified(zh)
                _upsert(self.root, simp, vi, 100)
                if simp != zh:
                    _upsert(self.root, zh, vi, 100)
        self.ready = True

    def _load_phrase_file(self, path: Path, pri: int, simp_keys: bool = False) -> None:
        for line in _read_text(path).splitlines():
            line = line.strip()
            if not line or line[0] in "#;":
                continue
            if line.startswith("//"):
                continue
            eq = line.find("=")
            if eq < 1:
                continue
            zh = line[:eq].strip()
            if "{" in zh:
                continue  # luat nhan {s}/{n}/{p}/{v} — engine cu khong nap pattern
            vi = _first_meaning(line[eq + 1 :])
            if pri == 20 and len(zh) == 1:
                continue
            if simp_keys:
                simp = self.to_simplified(zh)
                _upsert(self.root, simp, vi, pri)
                if simp != zh:
                    _upsert(self.root, zh, vi, pri)
            else:
                _upsert(self.root, zh, vi, pri)

    def to_simplified(self, text: str) -> str:
        mp = self.trad_simp
        if not mp:
            return text
        return "".join(ch if ch == "么" else mp.get(ch, ch) for ch in text)

    def convert(self, text: str) -> str:
        if not self.ready:
            self.load()
        text = self.to_simplified(text)
        parts: list[str] = []
        i = 0
        n = len(text)
        while i < n:
            if text[i] == "\n":
                parts.append("\n")
                i += 1
                continue
            if not CJK_RE.match(text[i]):
                j = i + 1
                while j < n and text[j] != "\n" and not CJK_RE.match(text[j]):
                    j += 1
                parts.append(text[i:j])
                i = j
                continue
            hit = _match(self.root, text, i)
            if hit is None:
                parts.append(text[i])
                i += 1
                continue
            end, val = hit
            src = text[i:end]
            if len(src) == 1 and src in DROP_PARTICLES:
                i = end
                continue
            parts.append(val)
            i = end
        return unicodedata.normalize("NFC", _capitalize(_post_process_vietnamese(_join_tokens(parts))))


_ENGINE: Engine | None = None
_OVERLAY_ID: int | None = None


def _capitalize(text: str) -> str:
    return CAP_RE.sub(lambda m: m.group(1) + m.group(2).upper(), text)


def ensure_dicts() -> None:
    DICT_DIR.mkdir(parents=True, exist_ok=True)
    missing = [
        name
        for name, _ in DICT_FILES
        if name != CUSTOM_FILE and not (DICT_DIR / name).is_file()
    ]
    if phienam_needs_refresh(DICT_DIR) and "ChinesePhienAmWords.txt" not in missing:
        missing.append("ChinesePhienAmWords.txt")
    if not missing:
        return
    for name in missing:
        url = f"{DICT_BASE}/{name}"
        print(f"[vietphrase] download {name}", flush=True)
        resp = requests.get(url, timeout=300)
        resp.raise_for_status()
        (DICT_DIR / name).write_bytes(resp.content)


def get_engine(overlay: dict[str, str] | None = None) -> Engine:
    global _ENGINE, _OVERLAY_ID
    oid = hash(tuple(sorted((overlay or {}).items())))
    if _ENGINE is None or not _ENGINE.ready or oid != _OVERLAY_ID:
        eng = Engine()
        eng.load(overlay)
        _ENGINE = eng
        _OVERLAY_ID = oid
    return _ENGINE


def convert(text: str, overlay: dict[str, str] | None = None) -> str:
    return get_engine(overlay).convert(text)
