"""E2E CLI (story 5.4): translate fixture ghi manifest; --no-learn khong discovery."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zhvi.cli import app
from zhvi.state import State

REPO_ROOT = Path(__file__).resolve().parents[2]
DICT_DIR = REPO_ROOT / "crawler" / "vietphrase" / "dicts"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_story.txt"

runner = CliRunner()

need_dict = pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / "mini_story.txt"
    shutil.copy(FIXTURE, dest)
    return dest


def _workspace(src: Path) -> Path:
    return src.with_name(src.stem + ".zhvi")


def _obs_count(ws: Path) -> int:
    st = State(ws / ".zhvi" / "state.sqlite3")
    try:
        row = st.conn.execute("SELECT COUNT(*) FROM observations").fetchone()
        return int(row[0]) if row else 0
    finally:
        st.close()


def _translate_cmd(src: Path | None, out: Path, *extra: str) -> list[str]:
    args = ["translate"]
    if src is not None:
        args.append(str(src))
    args += ["-o", str(out), "--dict-dir", str(DICT_DIR), *extra, "--json"]
    return args


@need_dict
def test_happy_path_translate_writes_manifest(tmp_path: Path):
    src = _copy_fixture(tmp_path)
    out = tmp_path / "out.vi.txt"
    r = runner.invoke(app, _translate_cmd(src, out))
    assert r.exit_code == 0, r.stdout + str(r.exception)
    assert out.is_file()
    report = json.loads(r.stdout)
    run_id = report["run_id"]
    assert run_id

    ws = _workspace(src)
    manifest_path = ws / ".zhvi" / "runs" / run_id / "manifest.json"
    assert manifest_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == run_id
    rev = manifest["dictionary_revision"]
    assert isinstance(rev, str) and len(rev) == 64
    sha = manifest["output"]["sha256"]
    assert isinstance(sha, str) and len(sha) == 64
    assert _obs_count(ws) > 0


@need_dict
def test_no_learn_skips_discovery(tmp_path: Path):
    src = _copy_fixture(tmp_path)
    out = tmp_path / "out.vi.txt"
    r = runner.invoke(app, _translate_cmd(src, out, "--no-learn"))
    assert r.exit_code == 0, r.stdout + str(r.exception)
    assert out.is_file()
    ws = _workspace(src)
    assert (ws / ".zhvi" / "state.sqlite3").is_file()
    assert _obs_count(ws) == 0


@need_dict
def test_translate_project_flag_uses_imported_snapshot(tmp_path: Path):
    """pipeline-contract: zhvi translate -p PROJECT --no-learn (khong FILE)."""
    src = _copy_fixture(tmp_path)
    proj = tmp_path / "proj"
    assert runner.invoke(app, ["init", str(proj)]).exit_code == 0
    imp = runner.invoke(app, ["import-", str(src), "-p", str(proj)])
    assert imp.exit_code == 0, imp.stdout + str(imp.exception)
    out = tmp_path / "out.vi.txt"
    r = runner.invoke(
        app, _translate_cmd(None, out, "-p", str(proj), "--no-learn")
    )
    assert r.exit_code == 0, r.stdout + str(r.exception)
    assert out.is_file()
    assert _obs_count(proj) == 0


@need_dict
def test_status_export_doctor_after_translate(tmp_path: Path):
    src = _copy_fixture(tmp_path)
    out = tmp_path / "out.vi.txt"
    r = runner.invoke(app, _translate_cmd(src, out))
    assert r.exit_code == 0, r.stdout + str(r.exception)
    ws = _workspace(src)
    original = out.read_bytes()

    st = runner.invoke(app, ["status", "--project", str(ws)])
    assert st.exit_code == 0, st.stdout + str(st.exception)
    info = json.loads(st.stdout)
    assert info["status"] == "exported"
    assert info["run_id"]

    re_out = tmp_path / "re.txt"
    ex = runner.invoke(app, ["export", "--project", str(ws), "-o", str(re_out)])
    assert ex.exit_code == 0, ex.stdout + str(ex.exception)
    payload = json.loads(ex.stdout)
    assert Path(payload["output"]).read_bytes() == original
    assert re_out.read_bytes() == original
    assert len(payload["sha256"]) == 64

    doc = runner.invoke(app, ["doctor", "--dict-dir", str(DICT_DIR)])
    assert doc.exit_code == 0, doc.stdout + str(doc.exception)
