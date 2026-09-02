"""Tests cho document.py — round-trip lossless la bat buoc (thiet ke muc 7/39)."""
from __future__ import annotations

from pathlib import Path

import pytest

from zhvi.document import inspect_document, parse_document

RAW_CHINA = Path(__file__).resolve().parents[2] / "raw_china"


def test_rebuild_byte_for_byte_chap1():
    text = (RAW_CHINA / "chap1_raw.txt").read_text(encoding="utf-8")
    doc = parse_document(text)
    assert doc.rebuild() == text


def test_nodes_cover_document_exactly():
    text = (RAW_CHINA / "chap1_raw.txt").read_text(encoding="utf-8")
    doc = parse_document(text)
    assert doc.nodes[0].char_start == 0
    assert doc.nodes[-1].char_end == len(text)
    for prev, nxt in zip(doc.nodes, doc.nodes[1:]):
        assert prev.char_end == nxt.char_start


def test_content_prefix_suffix_partition():
    text = (RAW_CHINA / "chap1_raw.txt").read_text(encoding="utf-8")
    doc = parse_document(text)
    for node in doc.nodes:
        if node.is_translatable:
            assert node.prefix + node.content + node.suffix == node.raw_text
            assert node.content != ""
        else:
            assert node.prefix == node.raw_text


def test_chapter_detection_presets():
    text = "第一章 开始\n\n正文一。\n\n第十章\n\n正文二。\n"
    doc = parse_document(text)
    headings = [n for n in doc.nodes if n.node_type == "heading"]
    assert len(headings) == 2
    assert doc.chapter_count == 2
    assert headings[0].chapter_id == 0
    assert headings[1].chapter_id == 1
    paras = [n for n in doc.nodes if n.node_type == "paragraph"]
    assert paras[0].chapter_id == 0
    assert paras[1].chapter_id == 1


def test_preface_before_first_heading():
    text = "引子\n\n第1章 chuong mot\n\nnoi dung\n"
    doc = parse_document(text)
    first_para = next(n for n in doc.nodes if n.node_type == "paragraph")
    assert first_para.chapter_id == -1


def test_no_heading_fallback_single_chapter():
    text = "chi la van thuong\nkhong co heading\n"
    doc = parse_document(text)
    rep = inspect_document(doc)
    assert rep.ambiguous_chapters
    assert any("heading" in w for w in rep.warnings)


def test_crlf_round_trip():
    text = "第一章\r\n\r\nDoan mot.\r\n\r\nDoan hai.\r\n"
    doc = parse_document(text)
    assert doc.newline_style == "\r\n"
    assert doc.rebuild() == text
    assert doc.chapter_count == 1


def test_blank_lines_and_tabs_round_trip():
    text = "  a\n\n\t\n\n\n  b  \n"
    doc = parse_document(text)
    assert doc.rebuild() == text


def test_ideographic_space_preserved():
    text = "\u3000\u3000凌天看着前方。\n"
    doc = parse_document(text)
    para = next(n for n in doc.nodes if n.node_type == "paragraph")
    assert para.prefix == "\u3000\u3000"
    assert para.content == "凌天看着前方。"
    assert doc.rebuild() == text


def test_long_paragraph_flagged():
    text = "字" * 7000 + "\n"
    doc = parse_document(text)
    rep = inspect_document(doc, block_max_chars=2000)
    assert rep.long_paragraphs == 1


def test_unbalanced_quotes_flagged():
    text = "“mở mà không đóng\n"
    doc = parse_document(text)
    rep = inspect_document(doc)
    assert rep.unbalanced_quotes == 1


def test_cjk_ratio():
    text = "中文中文\n"
    doc = parse_document(text)
    rep = inspect_document(doc)
    assert rep.cjk_ratio == 1.0


def test_custom_chapter_regex():
    text = "Chapter 5: hello\n\nbody\n"
    doc = parse_document(text, chapter_regex=r"Chapter \d+")
    assert doc.chapter_count == 1


def test_chapter_detection_none():
    text = "第一章\n\nbody\n"
    doc = parse_document(text, chapter_detection="none")
    assert doc.chapter_count == 1
    assert all(n.node_type != "heading" for n in doc.nodes)


def test_byte_offsets_utf8():
    text = "中文\nabc\n"
    doc = parse_document(text)
    offsets = doc.byte_offsets("utf-8")
    assert offsets[0] == (0, 7)  # 中文\n = 3+3+1
    assert offsets[1] == (7, 11)


@pytest.mark.parametrize("name", ["chap1_raw.txt"])
def test_real_file_inspect_sane(name: str):
    text = (RAW_CHINA / name).read_text(encoding="utf-8")
    doc = parse_document(text)
    rep = inspect_document(doc)
    assert rep.total_chars == len(text)
    assert rep.node_counts.get("paragraph", 0) > 10
