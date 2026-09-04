"""Test baseline VietPhrase-only (story 1.5, SPEC CAP-11).

Deterministic output (cung fingerprint -> cung SHA-256) + resume parity
(interrupt roi resume == clean run) + status route VIETPHRASE.
Dung dict dir nho de test nhanh — determinism khong phu thuoc kich thuoc dict.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from zhvi.pipeline import PipelineResult, TranslateRequest, translate_project
from zhvi.project import create_project
from zhvi.state import State

SRC = "第一章\n\n凌天看着前方。\n\n青龙从天而降。\n"


def _mini_dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mini-dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "凌天=Lăng Thiên\n青龙=Thanh Long\n看着=nhìn về phía\n前方=phía trước\n"
        "从天而降=rơi từ trời xuống\n第一章=Chương 1\n",
        encoding="utf-8",
    )
    return d


def _translate(project_dir: Path, src_file: Path, out_file: Path, dict_dir: Path) -> PipelineResult:
    p = create_project(project_dir)
    return translate_project(
        p, TranslateRequest(source=src_file, output=out_file, dict_dir=str(dict_dir))
    )


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_deterministic_same_fingerprint_same_sha256(tmp_path):
    """Hai project rieng, cung source + dict + config -> cung output SHA-256."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")

    out_a = tmp_path / "a.vi.txt"
    out_b = tmp_path / "b.vi.txt"
    res_a = _translate(tmp_path / "proj-a", src, out_a, dict_dir)
    res_b = _translate(tmp_path / "proj-b", src, out_b, dict_dir)

    assert res_a.exit_code == 0 and res_b.exit_code == 0
    assert res_a.report["sha256"] == res_b.report["sha256"] == _sha(out_a) == _sha(out_b)
    # fingerprint giong het (source revision + dict + config)
    st_a = State(tmp_path / "proj-a" / ".zhvi" / "state.sqlite3")
    st_b = State(tmp_path / "proj-b" / ".zhvi" / "state.sqlite3")
    try:
        assert st_a.latest_run().fingerprint == st_b.latest_run().fingerprint
    finally:
        st_a.close()
        st_b.close()


def test_resume_parity_interrupted_equals_clean(tmp_path, monkeypatch):
    """Gian doan giua chung (KeyboardInterrupt sau vai block) roi resume -> output
    giong het clean run."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")

    # Clean run (chenh doan)
    out_clean = tmp_path / "clean.vi.txt"
    assert _translate(tmp_path / "proj-clean", src, out_clean, dict_dir).exit_code == 0

    # Run bi gian doan: block dau tien dich OK (da commit), block thu 2 interrupt
    import zhvi.pipeline as pl

    real_vp_plan = pl.vp_plan
    calls = {"n": 0}

    def flaky_vp_plan(dic, text, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyboardInterrupt
        return real_vp_plan(dic, text, **kw)

    monkeypatch.setattr(pl, "vp_plan", flaky_vp_plan)
    proj_i = tmp_path / "proj-interrupted"
    res_i = _translate(proj_i, src, tmp_path / "i.vi.txt", dict_dir)
    assert res_i.exit_code == 130  # paused
    assert res_i.report["paused"] is True
    # block da commit van giu
    assert res_i.report["blocks"] >= 1

    # Resume (khong con interrupt)
    monkeypatch.setattr(pl, "vp_plan", real_vp_plan)
    out_i = tmp_path / "i.vi.txt"
    res_r = _translate(proj_i, src, out_i, dict_dir)
    assert res_r.exit_code == 0

    assert _sha(out_i) == _sha(out_clean)


def test_resume_report_counts_cached_blocks_routes(tmp_path, monkeypatch):
    """Resume run: report vp_ratio/routes phai dem TAT CA block committed cua run
    (ke ca block nap lai tu run truoc / cache-hit), khong phai chi block moi
    dich trong lan nay (CAP-9 metric)."""
    import zhvi.pipeline as pl

    from zhvi.config import ROUTE_VIETPHRASE

    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")

    real_vp_plan = pl.vp_plan
    calls = {"n": 0}

    def flaky_vp_plan(dic, text, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyboardInterrupt
        return real_vp_plan(dic, text, **kw)

    monkeypatch.setattr(pl, "vp_plan", flaky_vp_plan)
    proj = tmp_path / "proj-r"
    res_i = _translate(proj, src, tmp_path / "r.vi.txt", dict_dir)
    assert res_i.exit_code == 130
    assert res_i.report["blocks"] >= 1
    # paused report: vp_ratio = block da commit / tong block (khong hardcode 1.0)
    assert 0 < res_i.report["vp_ratio"] < 1.0
    assert res_i.report["routes"].get(ROUTE_VIETPHRASE) == res_i.report["blocks"]

    # Resume: block dau skip (da commit), block con lai di VP moi
    monkeypatch.setattr(pl, "vp_plan", real_vp_plan)
    res_r = _translate(proj, src, tmp_path / "r.vi.txt", dict_dir)
    assert res_r.exit_code == 0
    assert res_r.report["vp_ratio"] == 1.0
    assert res_r.report["routes"][ROUTE_VIETPHRASE] == res_r.report["blocks"]


def test_status_shows_vietphrase_route(tmp_path):
    """zhvi status (State.status_info) hien thi route VIETPHRASE cho run moi."""
    from zhvi.config import ROUTE_VIETPHRASE

    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    assert _translate(tmp_path / "proj-x", src, tmp_path / "x.vi.txt", dict_dir).exit_code == 0

    st = State(tmp_path / "proj-x" / ".zhvi" / "state.sqlite3")
    try:
        info = st.status_info()
        assert set(info["routes"]) == {ROUTE_VIETPHRASE}
        assert info["routes"][ROUTE_VIETPHRASE] == info["blocks_total"]
    finally:
        st.close()
