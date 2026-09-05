"""Tests CLI-level: exit codes (muc 34) + happy path 1 lenh (muc 3.1)."""
from __future__ import annotations

import json
import subprocess
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


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_vp_only_route_stats(tmp_path):
    """Story 1.1/1.3: pipeline VP-only — moi block route VIETPHRASE, khong model digest."""
    src = tmp_path / "truyen.txt"
    # Mot block sach (khong Han) + mot block co chu Han.
    src.write_text("第一章\n\nHello world.\n\n凌天看着远方。\n", encoding="utf-8")
    proj = tmp_path / "truyen.zhvi"
    r0 = run_cli("init", str(proj))
    assert r0.returncode == 0, r0.stderr
    r = run_cli("translate", str(src), "-o", str(tmp_path / "vi.txt"),
                "--dict-dir", str(DICT_DIR), "--project", str(proj), "--json")
    assert r.returncode == 0, r.stderr
    report = json.loads(r.stdout)
    assert "routes" in report
    assert report["routes"] == {"VIETPHRASE": report["blocks"]}
    # VP-only: khong con truong model digest nao trong report
    assert not any("digest" in key for key in report)


@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_review_command(tmp_path):
    """M2: `zhvi review --list` in ra block can review (fallback/abstain)."""
    src = tmp_path / "truyen.txt"
    src.write_text("第一章\n\n天地不仁以万物为刍狗。\n", encoding="utf-8")
    proj = tmp_path / "truyen.zhvi"
    r0 = run_cli("init", str(proj))
    assert r0.returncode == 0, r0.stderr
    r = run_cli("translate", str(src), "-o", str(tmp_path / "vi.txt"),
                "--dict-dir", str(DICT_DIR), "--project", str(proj), "--json")
    assert r.returncode == 0, r.stderr
    rv = run_cli("review", "--project", str(proj), "--list")
    assert rv.returncode == 0, rv.stderr
    payload = json.loads(rv.stdout)
    assert "count" in payload


def test_model_flags_removed(tmp_path):
    """Story 1.2: --hachimi/--qwen/--profile da bien mat — usage error (exit 2)."""
    src = tmp_path / "truyen.txt"
    src.write_text("第一章\n\n凌天。\n", encoding="utf-8")
    for flag in ("--hachimi", "--no-qwen", "--profile", "fast"):
        r = run_cli("translate", str(src), flag)
        assert r.returncode == 2, f"{flag} van duoc chap nhan"


def test_config_load_from_template(tmp_path):
    """Story 1.2: config load duoc tu PROJECT_TOML_TEMPLATE (schema SPEC 3.0)."""
    from zhvi.config import PROJECT_TOML_TEMPLATE, LearningConfig, load_project_config

    root = tmp_path
    (root / "zhvi.toml").write_text(PROJECT_TOML_TEMPLATE, encoding="utf-8")
    cfg = load_project_config(root)
    assert cfg.style == "convert-qt"
    assert cfg.output_policy == "strict-final"
    assert cfg.collapse_repetitions is True
    assert cfg.qa_strip_junk is True
    assert cfg.pattern_rules is True
    assert cfg.encoding == "utf-8"
    assert cfg.learning == LearningConfig()
    assert cfg.runtime.checkpoint_blocks == 50
    # Override qua TOML phan [learning]
    (root / "zhvi.toml").write_text(
        PROJECT_TOML_TEMPLATE.replace("enabled = true", "enabled = false", 1)
        .replace("min_chapters = 2", "min_chapters = 7", 1),
        encoding="utf-8",
    )
    cfg2 = load_project_config(root)
    assert cfg2.learning.enabled is False
    assert cfg2.learning.min_chapters == 7



@pytest.mark.skipif(not DICT_DIR.is_dir(), reason="can tu dien nen")
def test_discover_command_json(tmp_path):
    """zhvi discover: import -> discover in JSON summary observations (story 3.1)."""
    src = tmp_path / "truyen.txt"
    src.write_text(
        "第一章\n\n李慕白看着前方。\n\n第二章\n\n李慕白运转玄天诀。\n",
        encoding="utf-8",
    )
    proj = tmp_path / "proj"
    assert run_cli("init", str(proj)).returncode == 0
    r_imp = run_cli("import-", str(src), "-p", str(proj))
    assert r_imp.returncode == 0, r_imp.stderr
    r = run_cli("discover", "-p", str(proj), "--dict-dir", str(DICT_DIR))
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["observations"] > 0
    assert data["source_revision"] and data["dictionary_revision"]
    assert set(data["flags"]) == {
        "single_char_run", "unknown", "alt_segmentation", "repetition_unstable",
    }
