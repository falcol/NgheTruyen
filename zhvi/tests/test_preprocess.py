"""Tests cho versioned preprocessing view (story 2.6, SPEC FR13/AD-18).

Junk stripping xoa span kem SOURCE OFFSETS + reason code (offset theo
node.content goc, khong phai text da strip); transformation version hoa
(PREPROCESS_VERSION) tham gia run fingerprint + block cache key; source
snapshot khong bao gio bi doi.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from zhvi.config import Config
from zhvi.pipeline import TranslateRequest, block_cache_key, translate_project
from zhvi.project import create_project
from zhvi.qa import sanitize_source


def test_junk_spans_offsets_in_original_source():
    """Span offsets theo text GOC (chua strip) + reason code tung loai."""
    text = "「」他百萬\\小!說笑了天天看小說解書荒，很大。"
    clean, spans = sanitize_source(text)
    assert clean == "他笑了很大。"  # rule quang cao an luon dau phay sau 荒
    by_reason = {}
    for s in spans:
        by_reason.setdefault(s.reason, []).append(s)
        # offset theo goc: text[start:end] la dung phan bi strip
        assert text[s.start : s.end] != ""
    assert any(text[s.start : s.end] == "「」" for s in by_reason["EMPTY_QUOTES"])
    assert any("百萬" in text[s.start : s.end] for s in by_reason["INLINE_JUNK"])
    assert any("天天看小說解書荒" in text[s.start : s.end] for s in by_reason["INLINE_JUNK"])


def test_watermark_full_block_span():
    """Block toan watermark: span phu ca block, reason SITE_WATERMARK."""
    text = "ⓣⓣⓚ.ⓣⓦ 无弹窗"
    clean, spans = sanitize_source(text)
    assert clean == ""
    assert len(spans) == 1
    assert spans[0].reason == "SITE_WATERMARK"
    assert spans[0].start == 0 and spans[0].end == len(text)


def test_clean_text_no_spans():
    """Text sach: khong span."""
    clean, spans = sanitize_source("凌天看着前方。")
    assert clean == "凌天看着前方。"
    assert spans == []


def test_preprocess_version_in_cache_key_and_fingerprint(tmp_path, monkeypatch):
    """AD-18: PREPROCESS_VERSION tham gia fingerprint + cache key — bump lam
    mat cache/run cu."""
    from zhvi.fingerprint import build_run_fingerprint

    cfg = Config()
    fp1 = build_run_fingerprint(
        source_revision_hash="a", encoding="utf-8", dictionary_fingerprint="r", cfg=cfg
    )
    k1 = block_cache_key("src", "rev", cfg)
    monkeypatch.setattr("zhvi.pipeline.PREPROCESS_VERSION", "zhvi-preprocess-2")
    monkeypatch.setattr("zhvi.fingerprint.PREPROCESS_VERSION", "zhvi-preprocess-2")
    fp2 = build_run_fingerprint(
        source_revision_hash="a", encoding="utf-8", dictionary_fingerprint="r", cfg=cfg
    )
    k2 = block_cache_key("src", "rev", cfg)
    assert fp1 != fp2
    assert k1 != k2


def test_qa_trace_records_junk_spans(tmp_path):
    """qa cua block chua junk co junk_spans (offset + reason) — trace AD-18."""
    from zhvi.state import State

    dicts = tmp_path / "d"
    dicts.mkdir()
    (dicts / "QualityOverrides.txt").write_text(
        "笑了=được lắm\n很大=rất lớn\n", encoding="utf-8"
    )
    project = create_project(tmp_path / "proj")
    src = tmp_path / "s.txt"
    src.write_text("第一章\n\n「」他百萬\\小!說笑了。\n", encoding="utf-8")
    res = translate_project(
        project, TranslateRequest(source=src, output=tmp_path / "o.txt", dict_dir=str(dicts))
    )
    assert res.exit_code == 0
    st = State(project.db_path)
    try:
        blk = st.conn.execute(
            "SELECT qa_json FROM blocks WHERE run_id=?", (res.run_id,)
        ).fetchall()
    finally:
        st.close()
    qa = json.loads(blk[1][0])  # block doan van (index 1 sau heading)
    assert any(s["reason"] == "EMPTY_QUOTES" for s in qa.get("junk_spans", []))
    assert any(s["reason"] == "INLINE_JUNK" for s in qa.get("junk_spans", []))


def test_collapse_trace_has_source_offsets(tmp_path):
    """AD-18: repetition collapse xuat trace kem offset (start, end) cua span
    bi bo — khong chi count."""
    from zhvi.state import State
    from zhvi.vietphrase.lattice import vp_plan
    from zhvi.vietphrase.layers import Layer
    from zhvi.vietphrase.loader import Dictionary, TrieNode, _insert

    root = TrieNode()
    _insert(root, "稍微", "có chút", (int(Layer.BASE_MULTI), 10.0, 0), "CONTEXTUAL")
    _insert(root, "有点", "có chút", (int(Layer.BASE_MULTI), 10.0, 1), "CONTEXTUAL")
    dic = Dictionary(root=root, trad_simp={}, entry_count=2, fingerprint="t")
    draft = vp_plan(dic, "稍微有点", collapse_reps=True)
    assert draft.text == "Có chút"  # artifact 'có chút có chút' bi collapse (hoa dau cau)
    assert draft.collapsed_spans  # co offset
    for s in draft.collapsed_spans:
        assert 0 <= s[0] < s[1] <= len("稍微有点")
        assert "稍微" in "稍微有点"[s[0] : s[1]]  # span bi bo la edge dau
    # qua pipeline: qa ghi collapsed_spans
    dicts = tmp_path / "d"
    dicts.mkdir()
    (dicts / "QualityOverrides.txt").write_text(
        "稍微=có chút\n有点=có chút\n", encoding="utf-8"
    )
    project = create_project(tmp_path / "proj")
    src = tmp_path / "s.txt"
    src.write_text("第一章\n\n稍微有点\n", encoding="utf-8")
    res = translate_project(
        project, TranslateRequest(source=src, output=tmp_path / "o.txt", dict_dir=str(dicts))
    )
    assert res.exit_code == 0
    st = State(project.db_path)
    try:
        rows = st.conn.execute(
            "SELECT qa_json FROM blocks WHERE run_id=?", (res.run_id,)
        ).fetchall()
    finally:
        st.close()
    qa = json.loads(rows[1][0])
    assert qa.get("collapsed_spans")


def test_junk_only_block_export_keeps_lines(tmp_path):
    """Block chi co rac (watermark) -> final_text rong nhung export giu nguyen
    so dong (prefix/suffix newline) — byte-equivalent phan khong dich duoc."""
    dicts = tmp_path / "d"
    dicts.mkdir()
    (dicts / "QualityOverrides.txt").write_text("笑了=được lắm\n", encoding="utf-8")
    project = create_project(tmp_path / "proj")
    src = tmp_path / "s.txt"
    src.write_text("第一章\n\nⓣⓣⓚ.ⓣⓦ 无弹窗\n他笑了。\n", encoding="utf-8")
    res = translate_project(
        project, TranslateRequest(source=src, output=tmp_path / "o.txt", dict_dir=str(dicts))
    )
    assert res.exit_code == 0
    src_lines = src.read_text(encoding="utf-8").splitlines()
    out_lines = (tmp_path / "o.txt").read_text(encoding="utf-8").splitlines()
    assert len(out_lines) == len(src_lines)  # khong mat dong vi strip rac


def test_source_snapshot_untouched(tmp_path):
    """Source snapshot bytes khong doi sau khi dich (view only — FR13)."""
    dicts = tmp_path / "d"
    dicts.mkdir()
    (dicts / "QualityOverrides.txt").write_text("笑了=được lắm\n", encoding="utf-8")
    project = create_project(tmp_path / "proj")
    src = tmp_path / "s.txt"
    src.write_text("第一章\n\n「」他百萬\\小!說笑了。\n", encoding="utf-8")
    before = hashlib.sha256(src.read_bytes()).hexdigest()
    res = translate_project(
        project, TranslateRequest(source=src, output=tmp_path / "o.txt", dict_dir=str(dicts))
    )
    assert res.exit_code == 0
    from zhvi.state import State

    st = State(project.db_path)
    try:
        snap = st.latest_source_revision().snapshot_path
    finally:
        st.close()
    assert hashlib.sha256(Path(snap).read_bytes()).hexdigest() == hashlib.sha256(
        src.read_bytes()
    ).hexdigest()
    assert before == hashlib.sha256(src.read_bytes()).hexdigest()
