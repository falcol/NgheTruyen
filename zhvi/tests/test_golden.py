"""Tests golden manifest tooling (story 5.2, AD-14 / CAP-8)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zhvi.cli import app
from zhvi.golden import (
    DEFAULT_GOLDEN_MANIFEST,
    GoldenError,
    _compare,
    approve_case,
    approved_cases,
    import_candidates,
    is_approved,
    load_manifest,
    run_golden_report,
    save_manifest,
)
from zhvi.pipeline import TranslateRequest, translate_project
from zhvi.project import create_project

SRC1 = "第一章\n\n凌天看着前方。\n"
SRC2 = "第二章\n\n青龙从天而降。\n"


def _mini_dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mini-dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "凌天=Lăng Thiên\n青龙=Thanh Long\n看着=nhìn về phía\n前方=phía trước\n"
        "从天而降=rơi từ trời xuống\n第一章=Chương 1\n第二章=Chương 2\n",
        encoding="utf-8",
    )
    return d


def _ref_dir(tmp_path: Path, *, chap2: bool = True) -> Path:
    """Mini raw_china: 2 source + expect.txt + excpect2.txt + noise files."""
    ref = tmp_path / "raw_china"
    ref.mkdir()
    (ref / "chap1_raw.txt").write_text(SRC1, encoding="utf-8")
    if chap2:
        (ref / "chap2_raw.txt").write_text(SRC2, encoding="utf-8")
    (ref / "expect.txt").write_text("expect-one\n", encoding="utf-8")
    (ref / "excpect2.txt").write_text("expect-two\n", encoding="utf-8")
    (ref / "out.txt").write_text("khong-nhat\n", encoding="utf-8")
    (ref / "meta.json").write_text("{}", encoding="utf-8")
    return ref


def _complete_case(**overrides) -> dict:
    case = {
        "source_path": "/tmp/chap1_raw.txt",
        "source_sha256": "a" * 64,
        "expected_path": "/tmp/expect.txt",
        "expected_sha256": "b" * 64,
        "assertion_scope": "full",
        "provenance": {
            "origin": "expect.txt",
            "mapping_rule": "chap{n}_raw.txt",
            "imported_at": "2026-01-01T00:00:00+00:00",
        },
        "approval": None,
        "note": "",
    }
    case.update(overrides)
    return case


# ---- Task 1: default path + schema ----


def test_default_manifest_path_under_tests_golden():
    assert DEFAULT_GOLDEN_MANIFEST.name == "manifest.json"
    assert DEFAULT_GOLDEN_MANIFEST.parts[-2] == "golden"
    assert "tests" in DEFAULT_GOLDEN_MANIFEST.parts


def test_manifest_schema_version_guard(tmp_path):
    path = tmp_path / "manifest.json"
    path.write_text(
        json.dumps({"schema_version": 2, "cases": {}}, indent=2),
        encoding="utf-8",
    )
    with pytest.raises(GoldenError, match="schema_version"):
        load_manifest(path)


# ---- Task 2: import candidates (AC 1, AD-14, AD-19) ----


def test_import_candidates_globs_and_mapping(tmp_path):
    ref = _ref_dir(tmp_path)
    manifest_path = tmp_path / "golden" / "manifest.json"
    summary = import_candidates(ref, manifest_path)
    assert summary["imported"] == 2
    assert summary["updated"] == 0
    assert summary["unchanged"] == 0
    assert summary["total"] == 2

    manifest = load_manifest(manifest_path)
    assert manifest["schema_version"] == 1
    cases = manifest["cases"]
    assert set(cases) == {"expect", "excpect2"}

    c1 = cases["expect"]
    assert Path(c1["source_path"]).name == "chap1_raw.txt"
    assert Path(c1["expected_path"]).name == "expect.txt"
    assert c1["approval"] is None
    assert c1["assertion_scope"] == "full"
    assert c1["provenance"]["origin"] == "expect.txt"
    assert c1["source_sha256"]
    assert c1["expected_sha256"]

    c2 = cases["excpect2"]
    assert Path(c2["source_path"]).name == "chap2_raw.txt"
    assert Path(c2["expected_path"]).name == "excpect2.txt"
    assert c2["provenance"]["origin"] == "excpect2.txt"
    assert c2["approval"] is None

    # Noise files khong bi nhat
    for case in cases.values():
        assert "out.txt" not in case["expected_path"]
        assert not case["expected_path"].endswith(".json")
        assert "chap" not in Path(case["expected_path"]).name

    # AD-14: import xong khong tu approved
    assert approved_cases(manifest) == []
    assert not is_approved(c1)
    assert not is_approved(c2)


def test_import_idempotent_and_stale_hash_resets_approval(tmp_path):
    ref = _ref_dir(tmp_path)
    manifest_path = tmp_path / "manifest.json"
    import_candidates(ref, manifest_path)
    approve_case(manifest_path, "expect", actor="reviewer")
    manifest = load_manifest(manifest_path)
    assert is_approved(manifest["cases"]["expect"])

    again = import_candidates(ref, manifest_path)
    assert again["imported"] == 0
    assert again["updated"] == 0
    assert again["unchanged"] == 2
    kept = load_manifest(manifest_path)["cases"]["expect"]
    assert is_approved(kept)
    assert kept["approval"]["actor"] == "reviewer"

    # Source hash doi: khong reset approval (Dev Notes)
    (ref / "chap1_raw.txt").write_text(SRC1 + "x\n", encoding="utf-8")
    src_changed = import_candidates(ref, manifest_path)
    assert src_changed["updated"] == 0
    assert src_changed["unchanged"] == 2
    still = load_manifest(manifest_path)["cases"]["expect"]
    assert is_approved(still)
    assert still["approval"]["actor"] == "reviewer"

    manifest = load_manifest(manifest_path)
    manifest["cases"]["expect"]["assertion_scope"] = "contains"
    manifest["cases"]["expect"]["note"] = "keep-me"
    save_manifest(manifest_path, manifest)

    (ref / "expect.txt").write_text("expect-one-changed\n", encoding="utf-8")
    stale = import_candidates(ref, manifest_path)
    assert stale["updated"] == 1
    assert stale["unchanged"] == 1
    reset = load_manifest(manifest_path)["cases"]["expect"]
    assert reset["approval"] is None
    assert not is_approved(reset)
    assert reset["assertion_scope"] == "contains"
    assert reset["note"] == "keep-me"


def test_import_missing_source_does_not_crash(tmp_path):
    ref = _ref_dir(tmp_path, chap2=False)
    manifest_path = tmp_path / "manifest.json"
    summary = import_candidates(ref, manifest_path)
    assert summary["imported"] == 2
    c2 = load_manifest(manifest_path)["cases"]["excpect2"]
    assert c2["source_path"] == ""
    assert c2["source_sha256"] == ""
    assert "thieu source" in (c2.get("note") or "")
    assert c2["approval"] is None


# ---- Task 3: approve + AC 3 hop dong 4.3 ----


def test_approve_requires_fields_and_feeds_approved_cases(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    save_manifest(
        manifest_path,
        {
            "schema_version": 1,
            "cases": {
                "ok": _complete_case(),
                "no_source_hash": _complete_case(source_sha256=""),
                "no_approval": _complete_case(),
            },
        },
    )
    approved = approve_case(manifest_path, "ok", actor="falcol")
    assert approved["approval"]["actor"] == "falcol"
    assert approved["approval"]["approved_at"]
    manifest = load_manifest(manifest_path)
    assert is_approved(manifest["cases"]["ok"])
    names = [k for k, c in manifest["cases"].items() if is_approved(c)]
    assert names == ["ok"]
    assert len(approved_cases(manifest)) == 1

    with pytest.raises(GoldenError, match="source_sha256"):
        approve_case(manifest_path, "no_source_hash", actor="falcol")

    save_manifest(
        manifest_path,
        {
            "schema_version": 1,
            "cases": {
                **load_manifest(manifest_path)["cases"],
                "empty": _complete_case(
                    source_sha256="",
                    expected_sha256="",
                    assertion_scope="bad",
                    provenance={},
                ),
            },
        },
    )
    with pytest.raises(GoldenError) as exc:
        approve_case(manifest_path, "empty", actor="falcol")
    msg = str(exc.value)
    assert "source_sha256" in msg
    assert "expected_sha256" in msg
    assert "assertion_scope" in msg
    assert "provenance.origin" in msg
    assert "provenance.mapping_rule" in msg
    assert "provenance.imported_at" in msg

    # 6.5: du moi field khac, thieu approval -> khong mo gate
    assert not is_approved(load_manifest(manifest_path)["cases"]["no_approval"])
    gated = approved_cases(load_manifest(manifest_path))
    assert len(gated) == 1
    assert gated[0]["source_sha256"] == "a" * 64


def test_is_approved_contains_scope_and_rejects_bad_scope():
    ok = _complete_case(
        assertion_scope="contains",
        approval={"actor": "a", "approved_at": "2026-01-01T00:00:00+00:00"},
    )
    assert is_approved(ok)
    bad = _complete_case(
        assertion_scope="fuzzy",
        approval={"actor": "a", "approved_at": "2026-01-01T00:00:00+00:00"},
    )
    assert not is_approved(bad)
    incomplete = _complete_case(
        provenance={"origin": "expect.txt"},
        approval={"actor": "a", "approved_at": "2026-01-01T00:00:00+00:00"},
    )
    assert not is_approved(incomplete)


def test_approve_import_missing_source_lists_fields(tmp_path):
    ref = _ref_dir(tmp_path, chap2=False)
    manifest_path = tmp_path / "manifest.json"
    import_candidates(ref, manifest_path)
    with pytest.raises(GoldenError, match="source_sha256"):
        approve_case(manifest_path, "excpect2", actor="falcol")


def test_contains_pass_suppresses_diff():
    passed, n, mm, hint = _compare(
        "foo\n",
        "prefix foo suffix",
        "contains",
        "c1",
        source_text=SRC1,
        source_path="chap1_raw.txt",
    )
    assert passed is True
    assert n == 0 and mm == [] and hint == ""


# ---- Task 4: diff report (AC 1) ----


def test_report_pass_fail_and_missing_source(tmp_path):
    dict_dir = _mini_dict_dir(tmp_path)
    ref = tmp_path / "raw_china"
    ref.mkdir()
    chap1 = ref / "chap1_raw.txt"
    chap1.write_text(SRC1, encoding="utf-8")

    project = create_project(tmp_path / "proj")
    out = tmp_path / "out.vi.txt"
    result = translate_project(
        project,
        TranslateRequest(source=chap1, output=out, dict_dir=str(dict_dir)),
    )
    assert result.exit_code == 0
    vi = out.read_text(encoding="utf-8")
    (ref / "expect.txt").write_text(vi, encoding="utf-8")
    wrong = vi.splitlines()
    assert wrong, "expected translation must have lines"
    wrong[0] = wrong[0] + " SAI"
    (ref / "expect_wrong.txt").write_text("\n".join(wrong) + "\n", encoding="utf-8")
    (ref / "excpect2.txt").write_text("orphan\n", encoding="utf-8")

    manifest_path = tmp_path / "manifest.json"
    import_candidates(ref, manifest_path)
    approve_case(manifest_path, "expect", actor="falcol")

    report = run_golden_report(project, manifest_path, dict_dir=str(dict_dir))
    by_id = {c["case_id"]: c for c in report["cases"]}

    passed = by_id["expect"]
    assert passed["status"] == "approved"
    assert passed["pass"] is True
    assert passed["diff_lines"] == 0
    assert passed["source_sha256_match"] is True
    assert passed["expected_sha256_match"] is True

    failed = by_id["expect_wrong"]
    assert failed["status"] == "candidate"
    assert failed["pass"] is False
    assert failed["diff_lines"] > 0
    assert failed["mismatches"]
    assert len(failed["mismatches"]) <= 5
    assert "zhvi explain" in failed["trace_hint"]
    assert "第一章" in failed["trace_hint"]
    assert "chap1_raw.txt" in failed["trace_hint"]

    orphan = by_id["excpect2"]
    assert orphan["status"] == "candidate"
    assert orphan.get("error") == "missing source"
    assert orphan["pass"] is False

    report_path = Path(report["report_path"])
    assert report_path == project.root / ".zhvi" / "reports" / "golden-diff.json"
    assert report_path.is_file()
    disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert {c["case_id"] for c in disk["cases"]} == set(by_id)


# ---- Task 5: CLI ----


def test_cli_golden_import_approve_report(tmp_path):
    dict_dir = _mini_dict_dir(tmp_path)
    ref = _ref_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    manifest_path = tmp_path / "manifest.json"
    runner = CliRunner()

    r_imp = runner.invoke(
        app,
        [
            "golden",
            "import",
            "-p",
            str(project.root),
            "--dir",
            str(ref),
            "--manifest",
            str(manifest_path),
        ],
    )
    assert r_imp.exit_code == 0, r_imp.output
    summary = json.loads(r_imp.stdout or r_imp.output)
    assert summary["imported"] == 2
    assert summary["total"] == 2

    r_ok = runner.invoke(
        app,
        [
            "golden",
            "approve",
            "expect",
            "--actor",
            "falcol",
            "--manifest",
            str(manifest_path),
        ],
    )
    assert r_ok.exit_code == 0, r_ok.output
    approved = json.loads(r_ok.stdout or r_ok.output)
    assert approved["approval"]["actor"] == "falcol"

    r_bad = runner.invoke(
        app,
        [
            "golden",
            "approve",
            "khong-ton-tai",
            "--actor",
            "falcol",
            "--manifest",
            str(manifest_path),
        ],
    )
    assert r_bad.exit_code != 0
    err = (r_bad.stderr or "") + (r_bad.output or "")
    assert "error" in err.lower()
    assert "Khong co case" in err

    r_rep = runner.invoke(
        app,
        [
            "golden",
            "report",
            "-p",
            str(project.root),
            "--manifest",
            str(manifest_path),
            "--dict-dir",
            str(dict_dir),
        ],
    )
    assert r_rep.exit_code == 0, r_rep.output
    payload = json.loads(r_rep.stdout or r_rep.output)
    assert "cases" in payload
    assert {c["case_id"] for c in payload["cases"]} == {"expect", "excpect2"}
    expect_row = next(c for c in payload["cases"] if c["case_id"] == "expect")
    assert expect_row["status"] == "approved"
