"""Tests cho cross-book evidence ingest + dedupe (story 4.2, AD-17)."""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from zhvi.learning.candidate import build_candidates
from zhvi.learning.discovery import run_discovery
from zhvi.learning.evidence import evaluate_candidates
from zhvi.learning.ingest import build_evidence_records, submit_book_evidence
from zhvi.project import Project, create_project
from zhvi.registry import (
    REGISTRY_SCHEMA_VERSION,
    EvidenceRecord,
    RegistryError,
    RegistryState,
    ingest_evidence,
    registry_lock,
    resolve_registry_dir,
)
from zhvi.revision import ensure_active_revision, load_revision_dictionary
from zhvi.snapshot import import_snapshot
from zhvi.state import State

SRC = (
    "第一章\n\n"
    "李慕白看着前方。紫霄山高。未知语起。\n\n"
    "第二章\n\n"
    "李慕白运转玄天诀。紫霄山远。未知语灭。\n\n"
    "第三章\n\n"
    "李慕白望着紫霄山。未知语终。\n\n"
)

GROUPS = ["strength", "stability", "benefit", "risk", "scope", "regression"]


def _dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "dicts"
    d.mkdir(exist_ok=True)
    (d / "QualityOverrides.txt").write_text(
        "看着=nhìn về phía trước\n前方=phía trước\n运转=vận chuyển\n"
        "玄天=huyền thiên\n紫=tử\n霄=tiêu\n山=núi\n诀=quyết\n"
        "望着=nhìn về\n第一章=Chương 1\n第二章=Chương 2\n第三章=Chương 3\n",
        encoding="utf-8",
    )
    (d / "ChinesePhienAmWords.txt").write_text(
        "李=lý\n慕=mộ\n白=bạch\n", encoding="utf-8"
    )
    return d


def _learned_book(tmp_path: Path, dict_dir: Path, sub: str):
    """Pipeline mini: create_project -> snapshot -> discovery -> candidates
    -> evidence (pattern _evaluated test_evidence.py)."""
    root = tmp_path / sub
    root.mkdir()
    src = root / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    project = create_project(root / "proj")
    rev = import_snapshot(project, src)
    st = State(project.db_path)
    st.upsert_source_revision(
        rev.id, rev.content_hash, rev.encoding, rev.byte_size, str(rev.snapshot_path)
    )
    drev = ensure_active_revision(dict_dir, project)
    dic = load_revision_dictionary(project, drev)
    run_discovery(
        st, source_revision=rev, dictionary=dic, dictionary_revision_id=drev
    )
    build_candidates(
        st,
        book_id=project.book_id,
        dictionary=dic,
        dictionary_revision_id=drev,
        source_revision_id=rev.id,
    )
    evaluate_candidates(
        st, book_id=project.book_id, dictionary=dic, dictionary_revision_id=drev
    )
    return st, project


def _record(
    book_id: str = "b1",
    source_revision_id: str = "rev1",
    candidate_id: str = "c1",
    group: str = "strength",
    source_created_at: str = "2026-01-01T00:00:00+00:00",
    **over,
) -> EvidenceRecord:
    fields = {
        "book_id": book_id,
        "source_revision_id": source_revision_id,
        "candidate_id": candidate_id,
        "occurrence_span": group,
        "dictionary_revision_id": "drev1",
        "group_name": group,
        "signals_json": '{"total_count": 3}',
        "score": 1.5,
        "source_created_at": source_created_at,
    }
    fields.update(over)
    return EvidenceRecord(**fields)


def _summary_one(st: RegistryState, candidate_id: str) -> dict | None:
    for row in st.cross_book_summary():
        if row["candidate_id"] == candidate_id:
            return row
    return None


# ---- AC 1: dedupe theo (book_id, source_revision_id, candidate_id, span) ----


def test_ingest_dedupes_same_records(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    records = [_record(group=g) for g in GROUPS]
    first = ingest_evidence(reg, records)
    assert first["submitted"] == 6 and first["inserted"] == 6
    second = ingest_evidence(reg, records)
    assert second["inserted"] == 0
    st = RegistryState(reg)
    try:
        count = st.conn.execute("SELECT COUNT(*) FROM global_evidence").fetchone()[0]
        assert count == 6
        summary = _summary_one(st, "c1")
        assert summary == {"candidate_id": "c1", "books": 1, "occurrences": 6}
    finally:
        st.close()


def test_ingest_summary_lists_all_candidates_sorted(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    ingest_evidence(reg, [_record(candidate_id="c2", group=g) for g in GROUPS[:2]]
                    + [_record(candidate_id="c1", group=g) for g in GROUPS[:2]])
    st = RegistryState(reg)
    try:
        summary = st.cross_book_summary()
        assert [row["candidate_id"] for row in summary] == ["c1", "c2"]
        assert all(row["occurrences"] == 2 for row in summary)
    finally:
        st.close()


# ---- AC 2: copy project + re-ingest khong tang cross-book count ----


def test_copy_project_reingest_no_growth(tmp_path):
    dict_dir = _dict_dir(tmp_path)
    reg = resolve_registry_dir(dict_dir)
    st, project = _learned_book(tmp_path, dict_dir, "a")
    try:
        assert build_evidence_records(st), "pipeline mini phai tao evidence"
        first = submit_book_evidence(st, dict_dir)
        assert first["inserted"] > 0 and first["books"] == 1
        st_before = RegistryState(reg)
        before = st_before.cross_book_summary()
        st_before.close()
    finally:
        st.close()
    # Copy project + re-init idempotent (luong that cua user copy thu muc).
    copy_root = tmp_path / "a" / "proj-copy"
    shutil.copytree(tmp_path / "a" / "proj", copy_root)
    create_project(copy_root)
    st_copy = State(Project(copy_root).db_path)
    try:
        records = build_evidence_records(st_copy)
        again = ingest_evidence(reg, records)
        assert again["inserted"] == 0
    finally:
        st_copy.close()
    # AC #2 chu: import LAI cung source (literal) — snapshot content-addressed
    # nen cung source_revision_id, trung dedupe key.
    project_orig = Project(tmp_path / "a" / "proj")
    rev2 = import_snapshot(project_orig, tmp_path / "a" / "truyen.txt")
    st_re = State(project_orig.db_path)
    try:
        st_re.upsert_source_revision(
            rev2.id, rev2.content_hash, rev2.encoding, rev2.byte_size,
            str(rev2.snapshot_path),
        )
        re_records = build_evidence_records(st_re)
        assert ingest_evidence(reg, re_records)["inserted"] == 0
    finally:
        st_re.close()
    st2 = RegistryState(reg)
    try:
        after = st2.cross_book_summary()
        assert [r["candidate_id"] for r in after] == [
            r["candidate_id"] for r in before
        ]
        for row in after:
            assert row["books"] == 1
        assert [r["occurrences"] for r in after] == [r["occurrences"] for r in before]
    finally:
        st2.close()


# ---- AC 1: chi active source revision moi book vao promotion evidence ----


def test_summary_counts_only_active_source_revision(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    ingest_evidence(reg, [_record(source_revision_id="rev1", group=g)
                          for g in GROUPS[:3]])
    # Source sua: revision moi (created_at moi hon) thay the.
    ingest_evidence(reg, [_record(source_revision_id="rev2", group=g,
                                  source_created_at="2026-02-01T00:00:00+00:00")
                          for g in GROUPS[:2]])
    st = RegistryState(reg)
    try:
        summary = _summary_one(st, "c1")
        # Chi rev2 (active) duoc tinh: 2 occurrence, khong phai 5.
        assert summary["occurrences"] == 2 and summary["books"] == 1
        # Row rev1 VAN CON (bao toan) chi la khong duoc dem.
        count = st.conn.execute(
            "SELECT COUNT(*) FROM global_evidence WHERE source_revision_id='rev1'"
        ).fetchone()[0]
        assert count == 3
        pointer = st.conn.execute(
            "SELECT active_source_revision_id FROM book_sources WHERE book_id='b1'"
        ).fetchone()
        assert pointer is not None and pointer[0] == "rev2"
    finally:
        st.close()


def test_out_of_order_ingest_keeps_newest_revision(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    new = [_record(source_revision_id="rev2", group="strength",
                   source_created_at="2026-02-01T00:00:00+00:00")]
    old = [_record(source_revision_id="rev1", group="strength")]
    ingest_evidence(reg, new)
    ingest_evidence(reg, old)  # rev cu den sau — pointer khong lui.
    st = RegistryState(reg)
    try:
        pointer = st.conn.execute(
            "SELECT active_source_revision_id FROM book_sources WHERE book_id='b1'"
        ).fetchone()
        assert pointer[0] == "rev2"
        assert _summary_one(st, "c1")["occurrences"] == 1
    finally:
        st.close()


def test_two_books_same_candidate_counts_cross_book(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    ingest_evidence(reg, [_record(book_id="b1", group="strength"),
                          _record(book_id="b2", group="strength")])
    st = RegistryState(reg)
    try:
        summary = _summary_one(st, "c1")
        assert summary["books"] == 2 and summary["occurrences"] == 2
    finally:
        st.close()


# ---- AC 1: ingest qua registry writer lock (AD-13) ----


def test_ingest_blocked_when_registry_lock_held(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    with registry_lock(reg):
        with pytest.raises(RegistryError) as exc:
            ingest_evidence(reg, [_record()])
        assert "registry.lock" in str(exc.value)
    # Lock nha ra: ingest tiep binh thuong.
    assert ingest_evidence(reg, [_record()])["inserted"] == 1


# ---- AD-19: migration v1 -> v2 additive ----


def test_migration_v1_to_v2_preserves_meta(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    reg.mkdir(parents=True)
    conn = sqlite3.connect(reg / "state.sqlite3")
    conn.execute(
        "CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO meta(key, value) VALUES('schema_version', '1')"
    )
    conn.execute("INSERT INTO meta(key, value) VALUES('custom', 'giu-lai')")
    conn.commit()
    conn.close()
    st = RegistryState(reg)
    try:
        version = st.conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()[0]
        assert int(version) == REGISTRY_SCHEMA_VERSION == 2
        tables = {
            r[0]
            for r in st.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert {"meta", "global_evidence", "book_sources"} <= tables
        kept = st.conn.execute(
            "SELECT value FROM meta WHERE key='custom'"
        ).fetchone()[0]
        assert kept == "giu-lai"
    finally:
        st.close()


# ---- AC 1: book khong mutate global candidate/revision truc tiep ----


def test_ingest_creates_no_global_candidate_or_revision_tables(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    ingest_evidence(reg, [_record()])
    st = RegistryState(reg)
    try:
        tables = {
            r[0]
            for r in st.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert tables == {"meta", "global_evidence", "book_sources"}
    finally:
        st.close()


def test_build_records_empty_without_source_revision(tmp_path):
    dict_dir = _dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    st = State(project.db_path)
    try:
        assert build_evidence_records(st) == []
    finally:
        st.close()
    # Build rong khong mo registry — khong tao .zhvi-registry lazy.
    assert not resolve_registry_dir(dict_dir).exists()
