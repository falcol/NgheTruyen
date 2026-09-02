"""QA sanitize rule (thiet ke muc 13) — strip rac truyen web, khong dung model.

Rac truyen web TQ chen vao SOURCE: watermark chu tron (ⓣⓣⓚ.ⓣⓦ), dong
'bookmark', anti-leech inline (百萬\\小!說), clause quang cao (天天看小說解書荒),
va ngoac rong (「」). Chay tren node.content (TIENG TRUNG) TRUOC khi VP dich —
vi sau dich rac bien thanh tieng Viet lộn xộn khong the bat bang mau Trung.

Moi rule deterministic, co ten de trace trong QA warnings. Parser van lossless
tren source goc; chi text dua vao VP bi strip. Block bi strip het -> final_text
rong, export giu prefix/suffix (newline) nen so dong khong doi.
"""
from __future__ import annotations

import re

# Chu tron (ⓐ-ⓩ Ⓐ-Ⓩ) — dac trung watermark ten mien site (ⓣⓣⓚ.ⓣⓦ).
# KHONG gom so tron ①② — heading that co the dung loai nay.
CIRCLED_RE = re.compile(r"[\u24B6-\u24E9]")
# Dong 'bookmark' doc lap (nut bo site export thanh text).
BOOKMARK_RE = re.compile(r"^\s*book\s?mark\s*$", re.IGNORECASE)
# Ngoac/quote rong lien ke (leech chu thieu doi thuong).
EMPTY_QUOTES_RE = re.compile(r"(?:「」|『』|“”|‘’|\"\"|'')+|〔〕|〖〗")
# Anti-leech / quang cao chen inline trong cau.
INLINE_JUNK_RES = (
    re.compile(r"百萬\\?小!說"),
    re.compile(r"百万\\?小说"),
    re.compile(r"[每天]天看(?:小說|小说)解(?:書|书)荒[，,、]?"),
)


def sanitize_source(text: str) -> tuple[str, list[str]]:
    """Tra (clean_text, rules_applied) cho node.content tieng Trung truoc khi dich."""
    if not text.strip():
        return text, []
    # Block thuan watermark/quang cao: co chu tron hoac chi la 'bookmark' -> bo het.
    if CIRCLED_RE.search(text):
        return "", ["SITE_WATERMARK"]
    if BOOKMARK_RE.match(text):
        return "", ["BOOKMARK_LINE"]

    out = text
    applied: list[str] = []
    if EMPTY_QUOTES_RE.search(out):
        out = EMPTY_QUOTES_RE.sub("", out)
        applied.append("EMPTY_QUOTES")
    for rx in INLINE_JUNK_RES:
        out, n = rx.subn("", out)
        if n and "INLINE_JUNK" not in applied:
            applied.append("INLINE_JUNK")
    if applied:
        out = re.sub(r"[ \t]{2,}", " ", out).strip()
    return out, applied
