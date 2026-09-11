"""Tests cho export + pipeline E2E (thiet ke muc 30/39)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from zhvi.export import ExportFailure, IntegrityFailure, atomic_write, build_output, export_run
from zhvi.document import parse_document
from zhvi.pipeline import TranslateRequest, translate_project
from zhvi.project import create_project
from zhvi.state import State

REPO_ROOT = Path(__file__).resolve().parents[2]
DICT_DIR = REPO_ROOT / "crawler" / "vietphrase" / "dicts"
CHAP1 = REPO_ROOT / "raw_china" / "chap1_raw.txt"


@pytest.fixture()
def project(tmp_path):
    return create_project(tmp_path / "book")


def test_atomic_write(tmp_path):
    dest = tmp_path / "out.txt"
    digest = atomic_write(dest, b"xin chao")
    assert dest.read_bytes() == b"xin chao"
    assert digest == hashlib.sha256(b"xin chao").hexdigest()
    assert not (tmp_path / "out.txt.tmp").exists()


def test_build_output_lossless_structure():
    text = "第一章\n\n正文。\n\nkết.\n"
    doc = parse_document(text)
    blocks = {
        "c0b0": {"final_text": "Huong 1"},
        "c0b2": {"final_text": "Noi dung."},
        "c0b4": {"final_text": "kết."},
    }
    out = build_output(doc, blocks)
    assert out == "Huong 1\n\nNoi dung.\n\nkết.\n"


def test_build_output_missing_block_fails():
    text = "第一章\n\n正文。\n"
    doc = parse_document(text)
    with pytest.raises(ExportFailure):
        build_output(doc, {})


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_e2e_translate_chap1(project):
    out = project.root / "dist" / "vi.txt"
    result = translate_project(
        project, TranslateRequest(source=CHAP1, output=out, dict_dir=str(DICT_DIR))
    )
    assert result.exit_code == 0
    assert out.is_file()
    content = out.read_text(encoding="utf-8")
    assert "Lăng Thiên" in content
    # khong con chu Han
    import re

    assert not re.search(r"[\u4e00-\u9fff]", content)
    # so dong khong doi (lossless structure)
    src_lines = CHAP1.read_text(encoding="utf-8").count("\n")
    assert content.count("\n") == src_lines
    # manifest
    manifest = json.loads((project.runs_dir / result.run_id / "manifest.json").read_text())
    assert manifest["output"]["sha256"] == hashlib.sha256(out.read_bytes()).hexdigest()


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_rerun_same_fingerprint_noop(project):
    out = project.root / "dist" / "vi.txt"
    r1 = translate_project(project, TranslateRequest(source=CHAP1, output=out, dict_dir=str(DICT_DIR)))
    mtime1 = out.stat().st_mtime_ns
    r2 = translate_project(project, TranslateRequest(source=CHAP1, output=out, dict_dir=str(DICT_DIR)))
    assert r2.exit_code == 0
    assert r2.report.get("noop") is True
    assert r2.run_id == r1.run_id
    assert out.stat().st_mtime_ns == mtime1  # khong ghi lai


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_resume_skips_committed_blocks(project):
    """Kill giua run -> resume: block da commit khong bi dich lai."""
    out = project.root / "dist" / "vi.txt"
    # chay lan 1
    r1 = translate_project(project, TranslateRequest(source=CHAP1, output=out, dict_dir=str(DICT_DIR)))
    st = State(project.db_path)
    blocks_v1 = st.committed_blocks(r1.run_id)
    # gia lap crash: reset 5 block ve pending, doi status run
    ids = list(blocks_v1)[:5]
    with st.conn:
        st.conn.execute(
            f"UPDATE blocks SET status='pending', final_text=NULL WHERE id IN ({','.join('?' * len(ids))})",
            ids,
        )
        st.conn.execute("UPDATE runs SET status='paused' WHERE id=?", (r1.run_id,))
    # lan 2: phai tai dung 46 block, chi dich lai 5 block
    content_before = out.read_text(encoding="utf-8")
    r2 = translate_project(project, TranslateRequest(source=CHAP1, output=out, dict_dir=str(DICT_DIR)))
    assert r2.exit_code == 0
    st2 = State(project.db_path)
    assert r2.run_id == r1.run_id  # cung fingerprint -> resume run cu
    blocks_v2 = st2.committed_blocks(r2.run_id)
    assert len(blocks_v2) == len(blocks_v1)
    # noi dung sau resume khong doi
    assert out.read_text(encoding="utf-8") == content_before


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_append_chapter_reuses_old_blocks(project):
    out = project.root / "dist" / "vi.txt"
    src = tmp_src = project.root / "src.txt"
    tmp_src.write_text("第一章\n\n凌天看着前方。\n", encoding="utf-8")
    r1 = translate_project(project, TranslateRequest(source=src, output=out, dict_dir=str(DICT_DIR)))
    st = State(project.db_path)
    attempts_1 = st.conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE engine='vietphrase-lattice'"
    ).fetchone()[0]
    # append chuong 2
    tmp_src.write_text("第一章\n\n凌天看着前方。\n\n第二章\n\n白髮老者說道。\n", encoding="utf-8")
    r2 = translate_project(project, TranslateRequest(source=src, output=out, dict_dir=str(DICT_DIR)))
    assert r2.exit_code == 0
    st2 = State(project.db_path)
    attempts_2 = st2.conn.execute(
        "SELECT COUNT(*) FROM attempts WHERE engine='vietphrase-lattice'"
    ).fetchone()[0]
    # block cu tai dung tu cache => so lan dich that chi tang dung so block MOI
    assert attempts_2 - attempts_1 == 2
    content = out.read_text(encoding="utf-8")
    assert "Lăng Thiên" in content
    # Custom.txt: 白髮老者=bạch phát lão giả (thang VP "Lão giả tóc trắng")
    assert "lão giả" in content.lower()


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_export_requires_completed_run(project):
    out = project.root / "dist" / "vi.txt"
    src = project.root / "src.txt"
    src.write_text("第一章\n\n凌天。\n", encoding="utf-8")
    translate_project(project, TranslateRequest(source=src, output=out, dict_dir=str(DICT_DIR)))
    st = State(project.db_path)
    run = st.latest_run()
    st.set_run_status(run.id, "running")  # gia lap run chua xong
    with pytest.raises(ExportFailure):
        export_run(project, output=project.root / "dist" / "other.txt", run_id=run.id)


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_export_write_permission_error_is_export_failure(project, tmp_path):
    """Loi ghi output (vd duong dan toi thu muc goc) -> ExportFailure, khong crash lo."""
    src = project.root / "src.txt"
    src.write_text("第一章\n\n凌天。\n", encoding="utf-8")
    bad_out = Path("/raw_china/out.txt")  # root FS — khong ghi duoc
    with pytest.raises(ExportFailure):
        translate_project(project, TranslateRequest(source=src, output=bad_out, dict_dir=str(DICT_DIR)))


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_output_existing_different_needs_replace(project):
    out = project.root / "dist" / "vi.txt"
    src = project.root / "src.txt"
    src.write_text("第一章\n\n凌天。\n", encoding="utf-8")
    translate_project(project, TranslateRequest(source=src, output=out, dict_dir=str(DICT_DIR)))
    st = State(project.db_path)
    run = st.latest_run()
    out.write_text("noi dung khac gia", encoding="utf-8")
    with pytest.raises(ExportFailure):
        export_run(project, output=out, run_id=run.id, replace_existing=False)
    res = export_run(project, output=out, run_id=run.id, replace_existing=True)
    assert "Lăng Thiên" in out.read_text(encoding="utf-8")
