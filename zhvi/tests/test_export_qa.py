"""Tests structural QA truoc export (story 5.1)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import zhvi.pipeline as pl
from zhvi.document import parse_document
from zhvi.export import build_output, node_block_id
from zhvi.pipeline import TranslateRequest, translate_project
from zhvi.project import create_project
from zhvi.quality.export_qa import run_export_qa
from zhvi.state import State
from zhvi.vietphrase import lattice as lattice_mod

SRC = "第一章\n\n凌天看着前方。\n"


def _mini_dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mini-dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "凌天=Lăng Thiên\n看着=nhìn về phía\n前方=phía trước\n第一章=Chương 1\n",
        encoding="utf-8",
    )
    return d


def _blocks_for(doc, texts: dict[str, str]) -> dict[str, dict]:
    out = {}
    for node in doc.translatable_nodes():
        bid = node_block_id(node)
        out[bid] = {"final_text": texts.get(bid, "ok")}
    return out


def test_placeholder_fails_qa():
    doc = parse_document("第一章\n\nhello.\n")
    blocks = _blocks_for(doc, {})
    assembled = build_output(doc, blocks)
    bad = assembled.replace("ok", "ok__ZHVI")
    r = run_export_qa(doc, bad, blocks)
    assert r.ok is False
    assert "placeholder" in r.errors
    assert bad.endswith("ok__ZHVI") or "__ZHVI" in bad


def test_leftover_cjk_fails_qa():
    doc = parse_document("第一章\n\nhello.\n")
    blocks = _blocks_for(doc, {})
    assembled = build_output(doc, blocks)
    bad = assembled + "天"
    r = run_export_qa(doc, bad, blocks)
    assert r.ok is False
    assert "leftover_cjk" in r.errors


def test_missing_block_fails_qa():
    doc = parse_document("第一章\n\nhello.\n")
    blocks = {}
    r = run_export_qa(doc, "x\n\ny\n", blocks)
    assert r.ok is False
    assert "missing_blocks" in r.errors


def test_newline_mismatch_fails_qa():
    doc = parse_document("第一章\n\nhello.\n")
    blocks = _blocks_for(doc, {})
    assembled = build_output(doc, blocks)
    r = run_export_qa(doc, assembled.replace("\n", " "), blocks)
    assert r.ok is False
    assert "newline_mismatch" in r.errors


def test_repeated_artifact_fails_qa():
    doc = parse_document("第一章\n\nhello.\n")
    blocks = _blocks_for(doc, {})
    assembled = build_output(doc, blocks)
    # Chen cap lap khong them newline.
    bad = assembled.replace("ok", "ababab", 1)
    r = run_export_qa(doc, bad, blocks)
    assert r.ok is False
    assert "repeated_artifact" in r.errors


def test_header_equals_and_ellipsis_not_repeated_artifact():
    doc = parse_document("Hi.\n")
    blocks = _blocks_for(doc, {})
    assembled = build_output(doc, blocks)
    decorated = "===== chương 204 =====\n" + assembled + "Cọt kẹt..T..Tttt, chỗ....\n"
    r = run_export_qa(doc, decorated, blocks)
    assert "repeated_artifact" not in r.errors


def test_clean_output_passes_and_does_not_mutate():
    doc = parse_document("Hi.\n")
    blocks = _blocks_for(doc, {})
    assembled = build_output(doc, blocks)
    r = run_export_qa(doc, assembled, blocks)
    assert r.ok is True
    assert r.errors == []
    # AC 1.3: ket qua QA khong mang ban van da "sua".
    assert not hasattr(r, "output_text")
    assert "repaired" not in r.metrics


def test_pipeline_placeholder_blocks_export(tmp_path, monkeypatch):
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    out = tmp_path / "out.vi.txt"
    real = lattice_mod.vp_plan

    def _inject(*args, **kwargs):
        draft = real(*args, **kwargs)
        return replace(draft, text=draft.text + "__ZHVI")

    monkeypatch.setattr(lattice_mod, "vp_plan", _inject)
    monkeypatch.setattr(pl, "vp_plan", _inject)
    result = translate_project(
        project,
        TranslateRequest(source=src, output=out, dict_dir=str(dict_dir)),
    )
    assert result.exit_code == 9
    assert not out.exists()
    st = State(project.db_path)
    try:
        run = st.latest_run()
        assert run is not None and run.status == "needs_dictionary_fix"
    finally:
        st.close()
    assert result.report.get("output") is None
    assert "placeholder" in result.report["qa"]["errors"]
    assert "quality_score" not in result.report


def test_pipeline_report_has_metric_keys(tmp_path):
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    out = tmp_path / "out.vi.txt"
    result = translate_project(
        project,
        TranslateRequest(source=src, output=out, dict_dir=str(dict_dir)),
    )
    assert result.exit_code == 0, result.report
    report = result.report
    for key in (
        "dictionary_revision_id",
        "coverage_chars",
        "coverage_spans",
        "unknown_spans",
        "single_char_ratio",
        "fragmentation",
        "candidates",
        "auto_entries",
        "affected_blocks",
        "regression",
        "sha256",
        "elapsed_s",
        "chars_per_s",
    ):
        assert key in report, key
    assert "quality_score" not in report
    assert "score" not in report
    assert out.is_file()
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    assert report["sha256"] == digest
    manifest = json.loads(
        (project.runs_dir / result.run_id / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["output"]["sha256"] == digest
    vi = out.read_text(encoding="utf-8")
    assert report["coverage_chars"] == round(len(vi) / len(SRC), 4)
