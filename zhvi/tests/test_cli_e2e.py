"""E2E CLI (story 5.4): translate fixture ghi manifest; --no-learn khong discovery."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zhvi.cli import app

REPO_ROOT = Path(__file__).resolve().parents[2]
DICT_DIR = REPO_ROOT / "crawler" / "vietphrase" / "dicts"
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "mini_story.txt"

runner = CliRunner()

need_dict = pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")


def _copy_fixture(tmp_path: Path) -> Path:
    dest = tmp_path / "mini_story.txt"
    shutil.copy(FIXTURE, dest)
    return dest


def _translate_cmd(src: Path | None, out: Path, *extra: str) -> list[str]:
    args = ["translate"]
    if src is not None:
        args.append(str(src))
    args += ["-o", str(out), "--dict-dir", str(DICT_DIR), *extra, "--json"]
    return args


@need_dict
def test_happy_path_translate_writes_output(tmp_path: Path):
    src = _copy_fixture(tmp_path)
    out = tmp_path / "out.vi.txt"
    r = runner.invoke(app, _translate_cmd(src, out))
    assert r.exit_code == 0, r.stdout + str(r.exception)
    assert out.is_file() and out.stat().st_size > 0
    report = json.loads(r.stdout)
    assert report.get("stateless") is True
    assert report["blocks"] > 0
    assert not (tmp_path / ".zhvi").exists()


@need_dict
def test_no_state_writes_output_without_sqlite(tmp_path: Path):
    src = _copy_fixture(tmp_path)
    out = tmp_path / "out.vi.txt"
    r = runner.invoke(
        app,
        ["translate", str(src), "-o", str(out), "--dict-dir", str(DICT_DIR), "--no-state", "--json"],
    )
    assert r.exit_code == 0, r.stdout + str(r.exception)
    assert out.is_file() and out.stat().st_size > 0
    assert not (tmp_path / ".zhvi").exists()
    report = json.loads(r.stdout)
    assert report.get("stateless") is True
    assert report["blocks"] > 0


@need_dict
def test_no_learn_flag_still_translates(tmp_path: Path):
    src = _copy_fixture(tmp_path)
    out = tmp_path / "out.vi.txt"
    r = runner.invoke(app, _translate_cmd(src, out, "--no-learn"))
    assert r.exit_code == 0, r.stdout + str(r.exception)
    assert out.is_file() and out.stat().st_size > 0
    assert not (tmp_path / ".zhvi").exists()


@need_dict
def test_translate_project_flag_needs_file(tmp_path: Path):
    """translate -p khong con doc snapshot sqlite — can FILE."""
    src = _copy_fixture(tmp_path)
    proj = tmp_path / "proj"
    assert runner.invoke(app, ["init", str(proj)]).exit_code == 0
    out = tmp_path / "out.vi.txt"
    r = runner.invoke(
        app, _translate_cmd(src, out, "-p", str(proj))
    )
    assert r.exit_code == 0, r.stdout + str(r.exception)
    assert out.is_file() and out.stat().st_size > 0


@need_dict
def test_doctor_after_plain_translate(tmp_path: Path):
    src = _copy_fixture(tmp_path)
    out = tmp_path / "out.vi.txt"
    r = runner.invoke(app, _translate_cmd(src, out))
    assert r.exit_code == 0, r.stdout + str(r.exception)
    doc = runner.invoke(app, ["doctor", "--dict-dir", str(DICT_DIR)])
    assert doc.exit_code == 0, doc.stdout + str(doc.exception)
