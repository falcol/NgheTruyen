"""Tests CLI-level: exit codes (muc 34) + happy path 1 lenh (muc 3.1)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
DICT_DIR = REPO_ROOT / "crawler" / "vietphrase" / "dicts"
CHAP1 = REPO_ROOT / "raw_china" / "chap1_raw.txt"
ZHVI = str(REPO_ROOT / ".venv" / "bin" / "zhvi")


def run_cli(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [ZHVI, *args], capture_output=True, text=True, timeout=300,
        cwd=str(cwd or REPO_ROOT),
    )


def test_usage_error_exit_2(tmp_path):
    r = run_cli("translate")  # thieu ca file lan --project
    assert r.returncode == 2


def test_input_error_exit_3(tmp_path):
    r = run_cli("translate", str(tmp_path / "khong-co.txt"), "--dict-dir", str(DICT_DIR))
    assert r.returncode == 3


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_happy_path_one_command(tmp_path):
    """zhvi translate <txt> -o <out> — tu tao workspace ben canh input (muc 3.1)."""
    src = tmp_path / "truyen.txt"
    src.write_text("第一章\n\n凌天看着前方。\n", encoding="utf-8")
    out = tmp_path / "truyen.vi.txt"
    r = run_cli("translate", str(src), "-o", str(out), "--dict-dir", str(DICT_DIR), "--json")
    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert report["blocks"] == 2
    assert out.read_text(encoding="utf-8").startswith("Chương 1") or "Lăng Thiên" in out.read_text(encoding="utf-8")
    # workspace tu dong ben canh input
    assert (tmp_path / "truyen.zhvi" / ".zhvi" / "state.sqlite3").is_file()
    # no-op lan 2
    r2 = run_cli("translate", str(src), "-o", str(out), "--dict-dir", str(DICT_DIR), "--json")
    assert r2.returncode == 0
    assert json.loads(r2.stdout).get("noop") is True


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_status_and_inspect(tmp_path):
    src = tmp_path / "truyen.txt"
    src.write_text("第一章\n\n凌天。\n", encoding="utf-8")
    r = run_cli("translate", str(src), "-o", str(tmp_path / "vi.txt"), "--dict-dir", str(DICT_DIR))
    assert r.returncode == 0
    proj = tmp_path / "truyen.zhvi"
    st = run_cli("status", "--project", str(proj))
    assert st.returncode == 0
    info = json.loads(st.stdout)
    assert info["status"] == "exported"
    insp = run_cli("inspect", "--project", str(proj))
    assert insp.returncode == 0
    rep = json.loads(insp.stdout)
    assert rep["heading_count"] == 1


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_doctor_exit_0(tmp_path):
    r = run_cli("doctor", "--dict-dir", str(DICT_DIR))
    assert r.returncode == 0


def test_doctor_exit_4_missing_dict(tmp_path):
    r = run_cli("doctor", "--dict-dir", str(tmp_path / "khong-co-dict"))
    assert r.returncode == 4


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_export_command(tmp_path):
    src = tmp_path / "truyen.txt"
    src.write_text("第一章\n\n凌天。\n", encoding="utf-8")
    r = run_cli("translate", str(src), "-o", str(tmp_path / "vi.txt"), "--dict-dir", str(DICT_DIR))
    assert r.returncode == 0
    proj = tmp_path / "truyen.zhvi"
    out2 = tmp_path / "re-export.txt"
    r2 = run_cli("export", "--project", str(proj), "-o", str(out2))
    assert r2.returncode == 0, r2.stderr
    payload = json.loads(r2.stdout)
    assert Path(payload["output"]).read_bytes() == out2.read_bytes()
