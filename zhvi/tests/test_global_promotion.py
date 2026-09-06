"""Tests global promotion fail-closed (story 4.3, AD-14)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zhvi.cli import app
from zhvi.golden import approve_case, import_candidates
from zhvi.learning.global_promotion import (
    revoke_global_auto,
    run_global_promotion,
)
from zhvi.pipeline import TranslateRequest, translate_project
from zhvi.project import create_project
from zhvi.registry import (
    REGISTRY_DIRNAME,
    REGISTRY_SCHEMA_VERSION,
    EvidenceRecord,
    RegistryError,
    RegistryState,
    ingest_evidence,
    registry_lock,
    resolve_registry_dir,
)
from zhvi.state import State

SRC = "第一章\n\n凌天看着前方。\n"
TERM = "凌天"
TARGET = "Lăng Thiên"


def _mini_dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mini-dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "凌天=Lăng Thiên\n看着=nhìn về phía\n前方=phía trước\n第一章=Chương 1\n",
        encoding="utf-8",
    )
    return d


def _record(
    book_id: str,
    *,
    source: str = TERM,
    target: str = TARGET,
    total: int = 10,
    conflict: int = 0,
    group: str = "strength",
    signals: dict | None = None,
) -> EvidenceRecord:
    if signals is None:
        if group == "strength":
            signals = {"total_count": total}
        elif group == "risk":
            signals = {"manual_conflict": conflict}
        else:
            signals = {}
    return EvidenceRecord(
        book_id=book_id,
        source_revision_id="rev1",
        candidate_id=f"{book_id}-{group}",
        occurrence_span=group,
        dictionary_revision_id="drev1",
        group_name=group,
        signals_json=json.dumps(signals, sort_keys=True),
        score=1.0,
        source_created_at="2026-01-01T00:00:00+00:00",
        source=source,
        target=target,
    )


def _three_books(total: int = 10, conflict: int = 0, target: str = TARGET) -> list[EvidenceRecord]:
    rows: list[EvidenceRecord] = []
    for book in ("b1", "b2", "b3"):
        rows.append(_record(book, total=total, group="strength"))
        rows.append(_record(book, conflict=conflict, group="risk", target=target))
    return rows


def _project(tmp_path: Path, dict_dir: Path):
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    out = tmp_path / "out.vi.txt"
    result = translate_project(
        project,
        TranslateRequest(source=src, output=out, dict_dir=str(dict_dir)),
    )
    assert result.exit_code == 0
    return project, src, out


def _approve_golden(tmp_path: Path, src: Path, vi: str) -> Path:
    ref = tmp_path / "raw_china"
    ref.mkdir()
    (ref / "chap1_raw.txt").write_bytes(src.read_bytes())
    (ref / "expect.txt").write_text(vi, encoding="utf-8")
    manifest = tmp_path / "golden-manifest.json"
    import_candidates(ref, manifest)
    approve_case(manifest, "expect", actor="falcol")
    return manifest


# ---- AC 4 / 4.1: fail-closed khong golden ----


def test_fail_closed_without_approved_golden(tmp_path):
    dict_dir = _mini_dict_dir(tmp_path)
    project, _src, _out = _project(tmp_path, dict_dir)
    ingest_evidence(resolve_registry_dir(dict_dir), _three_books())
    st = State(project.db_path)
    try:
        book_rev = st.active_revision_id("book", project.book_id)
        empty = tmp_path / "empty-manifest.json"
        empty.write_text(
            json.dumps({"schema_version": 1, "cases": {}}, indent=2),
            encoding="utf-8",
        )
        summary = run_global_promotion(
            dict_dir=dict_dir,
            project=project,
            state=st,
            manifest_path=empty,
        )
        assert summary.promoted == 0
        assert any(g["name"] == "golden_manifest" and not g["passed"]
                   for g in summary.gates)
    finally:
        st.close()
    assert not (dict_dir / "AutoVietPhrase.txt").exists()
    reg = RegistryState(resolve_registry_dir(dict_dir))
    try:
        row = reg.conn.execute(
            "SELECT status FROM global_candidates WHERE source=?", (TERM,)
        ).fetchone()
        assert row is not None and row[0] == "global_candidate"
        after = State(project.db_path)
        try:
            assert after.active_revision_id("book", project.book_id) == book_rev
        finally:
            after.close()
    finally:
        reg.close()


def test_expect_files_do_not_open_global_gate(tmp_path):
    dict_dir = _mini_dict_dir(tmp_path)
    project, src, out = _project(tmp_path, dict_dir)
    ref = tmp_path / "raw_china"
    ref.mkdir()
    (ref / "chap1_raw.txt").write_bytes(src.read_bytes())
    (ref / "expect.txt").write_text(out.read_text(encoding="utf-8"), encoding="utf-8")
    manifest = tmp_path / "manifest.json"
    import_candidates(ref, manifest)
    ingest_evidence(resolve_registry_dir(dict_dir), _three_books())
    st = State(project.db_path)
    try:
        summary = run_global_promotion(
            dict_dir=dict_dir, project=project, state=st, manifest_path=manifest,
        )
        assert summary.promoted == 0
        assert any(g["name"] == "golden_manifest" and not g["passed"]
                   for g in summary.gates)
    finally:
        st.close()
    assert not (dict_dir / "AutoVietPhrase.txt").exists()


# ---- AC 2 / 4.3: pass path ----


def test_promote_when_golden_approved_and_evidence_enough(tmp_path):
    dict_dir = _mini_dict_dir(tmp_path)
    project, src, out = _project(tmp_path, dict_dir)
    manifest = _approve_golden(tmp_path, src, out.read_text(encoding="utf-8"))
    ingest_evidence(resolve_registry_dir(dict_dir), _three_books())
    st = State(project.db_path)
    try:
        book_rev = st.active_revision_id("book", project.book_id)
        summary = run_global_promotion(
            dict_dir=dict_dir, project=project, state=st, manifest_path=manifest,
        )
        assert summary.promoted == 1
        assert summary.revision_after
        assert summary.revision_after != summary.revision_before
        assert st.active_revision_id("book", project.book_id) == book_rev
    finally:
        st.close()
    avp = (dict_dir / "AutoVietPhrase.txt").read_text(encoding="utf-8")
    assert f"{TERM}={TARGET}" in avp
    drift = list((resolve_registry_dir(dict_dir) / "reports").glob("drift-*.json"))
    assert drift
    payload = json.loads(drift[0].read_text(encoding="utf-8"))
    assert TERM in payload["added"]
    assert set(payload) >= {"added", "changed", "revoked", "affected_books"}

    empty = tmp_path / "empty-manifest.json"
    empty.write_text(
        json.dumps({"schema_version": 1, "cases": {}}, indent=2),
        encoding="utf-8",
    )
    st2 = State(project.db_path)
    try:
        held = run_global_promotion(
            dict_dir=dict_dir, project=project, state=st2, manifest_path=empty,
        )
        assert held.promoted == 0
    finally:
        st2.close()
    reg = RegistryState(resolve_registry_dir(dict_dir))
    try:
        status = reg.conn.execute(
            "SELECT status FROM global_candidates WHERE source=?", (TERM,)
        ).fetchone()
        assert status is not None and status[0] == "global_auto"
    finally:
        reg.close()


def test_target_disagreement_holds(tmp_path):
    dict_dir = _mini_dict_dir(tmp_path)
    project, src, out = _project(tmp_path, dict_dir)
    manifest = _approve_golden(tmp_path, src, out.read_text(encoding="utf-8"))
    rows = _three_books()
    rows.append(_record("b-other", group="strength", target="KHAC", total=10))
    rows.append(_record("b-other", group="risk", target="KHAC", conflict=0))
    ingest_evidence(resolve_registry_dir(dict_dir), rows)
    st = State(project.db_path)
    try:
        held = run_global_promotion(
            dict_dir=dict_dir, project=project, state=st, manifest_path=manifest,
        )
        assert held.promoted == 0
        assert held.held >= 1
        assert any(g["name"] == "target_agreement" and not g["passed"]
                   for g in held.gates)
    finally:
        st.close()
    assert not (dict_dir / "AutoVietPhrase.txt").exists()


def test_revoke_removes_global_auto_entry(tmp_path):
    dict_dir = _mini_dict_dir(tmp_path)
    project, src, out = _project(tmp_path, dict_dir)
    manifest = _approve_golden(tmp_path, src, out.read_text(encoding="utf-8"))
    ingest_evidence(resolve_registry_dir(dict_dir), _three_books())
    st = State(project.db_path)
    try:
        ok = run_global_promotion(
            dict_dir=dict_dir, project=project, state=st, manifest_path=manifest,
        )
        assert ok.promoted == 1
        rev_before = ok.revision_after
        revoked = revoke_global_auto(dict_dir, TERM, actor="falcol")
        assert revoked.revision_id != rev_before
        rst = RegistryState(resolve_registry_dir(dict_dir))
        try:
            types = [
                r[0]
                for r in rst.conn.execute(
                    "SELECT event_type FROM global_promotion_events WHERE source=?",
                    (TERM,),
                )
            ]
            assert "revoked" in types
        finally:
            rst.close()
    finally:
        st.close()
    avp = (dict_dir / "AutoVietPhrase.txt").read_text(encoding="utf-8")
    assert f"{TERM}={TARGET}" not in avp


def test_cli_learn_global_and_lock(tmp_path):
    dict_dir = _mini_dict_dir(tmp_path)
    project, src, out = _project(tmp_path, dict_dir)
    manifest = _approve_golden(tmp_path, src, out.read_text(encoding="utf-8"))
    ingest_evidence(resolve_registry_dir(dict_dir), _three_books())
    runner = CliRunner()
    r = runner.invoke(
        app,
        [
            "learn", "--global",
            "-p", str(project.root),
            "--dict-dir", str(dict_dir),
            "--manifest", str(manifest),
        ],
    )
    assert r.exit_code == 0, r.output
    payload = json.loads(r.stdout or r.output)
    assert "global_promotion" in payload

    r_bad = runner.invoke(
        app,
        [
            "learn", "--global",
            "-p", str(project.root),
            "--dict-dir", str(dict_dir),
            "--manifest", str(tmp_path / "khong-co.json"),
        ],
    )
    assert r_bad.exit_code != 0
    err = (r_bad.stderr or "") + (r_bad.output or "")
    assert "error" in err.lower()

    reg = resolve_registry_dir(dict_dir)
    with registry_lock(reg):
        st = State(project.db_path)
        try:
            with pytest.raises(RegistryError):
                run_global_promotion(
                    dict_dir=dict_dir, project=project, state=st, manifest_path=manifest,
                )
        finally:
            st.close()


def test_migration_v2_to_v3_adds_columns(tmp_path):
    dict_dir = _mini_dict_dir(tmp_path)
    real = dict_dir.resolve()
    reg = real / REGISTRY_DIRNAME
    reg.mkdir()
    conn = sqlite3.connect(reg / "state.sqlite3")
    conn.executescript(
        "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);"
        "CREATE TABLE global_evidence("
        "book_id TEXT, source_revision_id TEXT, candidate_id TEXT, "
        "occurrence_span TEXT, dictionary_revision_id TEXT, group_name TEXT, "
        "signals_json TEXT, score REAL, ingested_at TEXT);"
        "CREATE TABLE book_sources("
        "book_id TEXT PRIMARY KEY, active_source_revision_id TEXT, "
        "active_source_created_at TEXT, updated_at TEXT);"
        "INSERT INTO meta VALUES('schema_version', '2');"
        "INSERT INTO meta VALUES('keep', 'yes');"
    )
    conn.commit()
    conn.close()
    st = RegistryState(reg)
    try:
        ver = st.conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()[0]
        assert int(ver) == REGISTRY_SCHEMA_VERSION == 3
        cols = {r[1] for r in st.conn.execute("PRAGMA table_info(global_evidence)")}
        assert {"source", "target"} <= cols
        tables = {
            r[0] for r in st.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"global_candidates", "global_promotion_events", "global_active"} <= tables
        assert st.conn.execute(
            "SELECT value FROM meta WHERE key='keep'"
        ).fetchone()[0] == "yes"
    finally:
        st.close()
