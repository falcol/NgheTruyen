"""Tests cho QA sanitize rules (thiet ke muc 13)."""
from __future__ import annotations

from zhvi.qa import sanitize_source


def test_watermark_line_dropped():
    text = "天天看小說解書荒，ⓣⓣⓚ.ⓣⓦ超實用"
    out, spans = sanitize_source(text)
    assert out == ""
    assert [s.reason for s in spans] == ["SITE_WATERMARK"]


def test_bookmark_line_dropped():
    out, spans = sanitize_source("bookmark")
    assert out == ""
    assert [s.reason for s in spans] == ["BOOKMARK_LINE"]


def test_inline_antileech_removed_sentence_kept():
    text = "「懦夫！」小胖看到凌天坐在凳子上百萬\\小!說的動作，以為他是怕了。"
    out, spans = sanitize_source(text)
    assert "百萬" not in out and "小!說" not in out
    assert "懦夫" in out and "以為他是怕了" in out
    assert [s.reason for s in spans] == ["INLINE_JUNK"]


def test_empty_quotes_removed():
    text = "面容猥瑣，一看就不是什麼好人！「」"
    out, spans = sanitize_source(text)
    assert out.endswith("好人！")
    assert "「」" not in out
    assert [s.reason for s in spans] == ["EMPTY_QUOTES"]


def test_clean_text_untouched():
    text = "「小天，來，我準備好了，我要和你決一死戰！」"
    out, spans = sanitize_source(text)
    assert out == text
    assert spans == []


def test_circled_digits_not_stripped():
    """So tron ①② co the xuat hien trong heading that -> KHONG bi rule watermark ban."""
    text = "第①章 開始"
    out, spans = sanitize_source(text)
    assert out == text
    assert spans == []
