"""QA sanitize rule (thiet ke muc 13, story 2.6 FR13) — strip rac truyen web,
khong dung model, kem source offsets + reason code.

Rac truyen web TQ chen vao SOURCE: watermark chu tron (ⓣⓣⓚ.ⓣⓦ), dong
'bookmark', anti-leech inline (百萬\\小!說), clause quang cao (天天看小說解書荒),
va ngoac rong (「」). Chay tren node.content (TIENG TRUNG) TRUOC khi VP dich —
vi sau dich rac bien thanh tieng Viet lộn xộn khong the bat bang mau Trung.

Moi rule deterministic. Span offsets theo node.content GOC (chua strip) de
trace lai chinh xac (AD-18); parser van lossless tren source goc — day chi la
VIEW dua vao VP. Block bi strip het -> final_text rong, export giu
prefix/suffix (newline) nen so dong khong doi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Chu tron (ⓐ-ⓩ Ⓐ-Ⓩ) — dac trung watermark ten mien site (ⓣⓣⓚ.ⓣⓦ).
# KHONG gom so tron ①② — heading that co the dung loai nay.
CIRCLED_RE = re.compile(r"[Ⓐ-ⓩ]")
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


@dataclass(frozen=True)
class JunkSpan:
    """Mot span bi xoa khoi view — offset theo source GOC (story 2.6, AD-18)."""

    start: int
    end: int
    reason: str  # SITE_WATERMARK | BOOKMARK_LINE | EMPTY_QUOTES | INLINE_JUNK


def sanitize_source(text: str) -> tuple[str, list[JunkSpan]]:
    """Tra (clean_text, junk_spans) cho node.content tieng Trung truoc khi dich.

    Offsets trong spans chi vao vi tri tren text GOC; clean_text la view sau
    khi xoa het spans (+ collapse khoang trang du).
    """
    if not text.strip():
        return text, []
    # Block thuan watermark/quang cao: co chu tron hoac chi la 'bookmark' -> bo het.
    if CIRCLED_RE.search(text):
        return "", [JunkSpan(0, len(text), "SITE_WATERMARK")]
    if BOOKMARK_RE.match(text):
        return "", [JunkSpan(0, len(text), "BOOKMARK_LINE")]

    spans: list[JunkSpan] = [
        JunkSpan(m.start(), m.end(), "EMPTY_QUOTES") for m in EMPTY_QUOTES_RE.finditer(text)
    ]
    for rx in INLINE_JUNK_RES:
        spans.extend(JunkSpan(m.start(), m.end(), "INLINE_JUNK") for m in rx.finditer(text))
    if not spans:
        return text, []
    # [Note] Xoa reverse theo start chi dung khi cac span KHONG chong lan —
    # invariant nay dam bao boi cac regex hien tai (rơi nhau); them rule chong
    # lan phai enforce/split span truoc khi xoa.
    out = text
    for span in sorted(spans, key=lambda s: s.start, reverse=True):
        out = out[: span.start] + out[span.end :]
    out = re.sub(r"[ \t]{2,}", " ", out).strip()
    return out, spans
