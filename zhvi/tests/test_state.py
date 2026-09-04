"""Tests cho state.py + fingerprint + resume/crash (thiet ke muc 8/27/29/39)."""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from zhvi.fingerprint import build_run_fingerprint
from zhvi.config import Config
from zhvi.state import State


@pytest.fixture()
def st(tmp_path):
    s = State(tmp_path / "state.sqlite3")
    yield s
    s.close()


def _stage(s: State, run_id: str, block_id: str, text: str = "dịch", src_hash: str = "h1", ord_: int = 1):
    s.stage_block(
        run_id=run_id,
        block_id=block_id,
        chapter_ordinal=0,
        block_ordinal=ord_,
        source_start=0,
        source_end=10,
        source_hash=src_hash,
        final_text=text,
        qa={"coverage": 1.0},
        route="DIRECT_VP",
        reasons=[],
        features={},
        router_version="v1",
        attempt={"id": f"a-{block_id}", "engine": "vp", "input_hash": src_hash, "status": "ok"},
    )


def test_schema_created(st):
    tables = {
        r[0]
        for r in st.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {
        "source_revisions", "runs", "blocks", "attempts",
        "route_decisions", "term_candidates", "feedback_events", "meta",
    } <= tables


def test_wal_mode(st):
    assert st.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"


def test_resume_or_create_and_fingerprint_unique(st):
    st.upsert_source_revision("rev1", "hash1", "utf-8", 100, "/tmp/rev1.txt")
    run, created = st.resume_or_create("r1", "fp1", "rev1", "dict1", {"a": 1})
    assert created and run.status == "running"
    run2, created2 = st.resume_or_create("r2", "fp1", "rev1", "dict1", {"a": 1})
    assert not created2 and run2.id == run.id  # cung fingerprint -> resume


def test_running_block_reset_to_pending_on_resume(st):
    st.upsert_source_revision("rev1", "hash1", "utf-8", 100, "/tmp/rev1.txt")
    st.resume_or_create("r1", "fp1", "rev1", "d", {})
    _stage(st, "r1", "b1")
    st.conn.execute("UPDATE blocks SET status='running' WHERE id='b1'")
    st.conn.commit()
    st.resume_or_create("r2", "fp1", "rev1", "d", {})
    row = st.conn.execute("SELECT status FROM blocks WHERE id='b1'").fetchone()
    assert row[0] == "pending"


def test_block_commit_atomic(st):
    st.upsert_source_revision("rev1", "hash1", "utf-8", 100, "/tmp/rev1.txt")
    st.resume_or_create("r1", "fp1", "rev1", "d", {})
    _stage(st, "r1", "b1", text="kết quả", src_hash="sha")
    blk = st.get_block("b1")
    assert blk["status"] == "committed"
    assert blk["final_text"] == "kết quả"
    rd = st.conn.execute("SELECT route FROM route_decisions WHERE block_id='b1'").fetchone()
    assert rd[0] == "DIRECT_VP"
    at = st.conn.execute("SELECT engine FROM attempts WHERE block_id='b1'").fetchone()
    assert at[0] == "vp"


def test_committed_blocks_roundtrip(st):
    st.upsert_source_revision("rev1", "hash1", "utf-8", 100, "/tmp/rev1.txt")
    st.resume_or_create("r1", "fp1", "rev1", "d", {})
    _stage(st, "r1", "b1")
    _stage(st, "r1", "b2", text="hai", ord_=2)
    blocks = st.committed_blocks("r1")
    assert set(blocks) == {"b1", "b2"}
    assert blocks["b2"]["final_text"] == "hai"


def test_status_info(st):
    st.upsert_source_revision("rev1", "hash1", "utf-8", 100, "/tmp/rev1.txt")
    st.resume_or_create("r1", "fp1", "rev1", "d", {})
    _stage(st, "r1", "b1")
    info = st.status_info()
    assert info["blocks_total"] == 1
    assert info["blocks_committed"] == 1
    assert info["routes"] == {"DIRECT_VP": 1}


def test_find_completed_run(st):
    st.upsert_source_revision("rev1", "hash1", "utf-8", 100, "/tmp/rev1.txt")
    st.resume_or_create("r1", "fp1", "rev1", "d", {})
    assert st.find_completed_run("fp1") is None
    st.set_run_status("r1", "completed")
    assert st.find_completed_run("fp1") is not None


def test_fingerprint_changes_with_source(st):
    cfg = Config()
    fp1 = build_run_fingerprint(
        source_revision_hash="a", encoding="utf-8", dictionary_fingerprint="d",
        book_glossary_hash="g", cfg=cfg,
    )
    fp2 = build_run_fingerprint(
        source_revision_hash="b", encoding="utf-8", dictionary_fingerprint="d",
        book_glossary_hash="g", cfg=cfg,
    )
    fp3 = build_run_fingerprint(
        source_revision_hash="a", encoding="utf-8", dictionary_fingerprint="d2",
        book_glossary_hash="g", cfg=cfg,
    )
    assert fp1 != fp2 != fp3
    fp1b = build_run_fingerprint(
        source_revision_hash="a", encoding="utf-8", dictionary_fingerprint="d",
        book_glossary_hash="g", cfg=cfg,
    )
    assert fp1 == fp1b  # deterministic


def test_db_reopen_persists(tmp_path):
    s1 = State(tmp_path / "db.sqlite3")
    s1.upsert_source_revision("rev1", "hash1", "utf-8", 100, "/tmp/rev1.txt")
    s1.resume_or_create("r1", "fp1", "rev1", "d", {})
    _stage(s1, "r1", "b1")
    s1.close()
    s2 = State(tmp_path / "db.sqlite3")
    assert s2.get_block("b1")["final_text"] == "dịch"
    s2.close()


# Schema v1 (thiet ke 2.0, truoc story 1.3): block_cache chua co cot invalid.
_SCHEMA_V1 = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE source_revisions (
    id TEXT PRIMARY KEY, content_hash TEXT NOT NULL UNIQUE, encoding TEXT NOT NULL,
    byte_size INTEGER NOT NULL, snapshot_path TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE runs (
    id TEXT PRIMARY KEY, source_revision_id TEXT NOT NULL, fingerprint TEXT NOT NULL,
    dictionary_revision_id TEXT NOT NULL, resolved_config_json TEXT NOT NULL,
    status TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, UNIQUE(fingerprint));
CREATE TABLE blocks (
    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, chapter_ordinal INTEGER NOT NULL,
    block_ordinal INTEGER NOT NULL, source_start INTEGER NOT NULL, source_end INTEGER NOT NULL,
    source_hash TEXT NOT NULL, status TEXT NOT NULL, final_text TEXT, qa_json TEXT,
    UNIQUE(run_id, chapter_ordinal, block_ordinal));
CREATE TABLE attempts (
    id TEXT PRIMARY KEY, block_id TEXT NOT NULL, engine TEXT NOT NULL, model_digest TEXT,
    prompt_hash TEXT, input_hash TEXT NOT NULL, output_json TEXT, status TEXT NOT NULL,
    duration_ms INTEGER, created_at TEXT NOT NULL);
CREATE TABLE route_decisions (
    block_id TEXT PRIMARY KEY, route TEXT NOT NULL, reasons_json TEXT NOT NULL,
    features_json TEXT NOT NULL, router_version TEXT NOT NULL);
CREATE TABLE block_cache (
    cache_key TEXT PRIMARY KEY, final_text TEXT NOT NULL, qa_json TEXT NOT NULL,
    created_at TEXT NOT NULL);
"""


def _make_v1_db(db_path: Path, model_era_cache_key: str) -> None:
    """Fixture: DB thiet ke 2.0 — run cu voi route model + cache model-era."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA_V1)
    conn.execute("INSERT INTO meta VALUES('schema_version', '1')")
    conn.execute(
        "INSERT INTO source_revisions VALUES('rev1','hash1','utf-8',100,'/tmp/rev1.txt','2026-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO runs VALUES('r1','rev1','fp-model-era','d','{}','completed',"
        "'2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO blocks VALUES('b1','r1',0,1,0,10,'h1','committed','kết quả cũ','{}')"
    )
    conn.execute(
        "INSERT INTO attempts VALUES('a1','b1','hachimi-ct2','digest-x','prompt-y','h1',"
        "'{}','ok',10,'2026-01-01T00:00:00+00:00')"
    )
    conn.execute(
        "INSERT INTO route_decisions VALUES('b1','HACHIMI_CANDIDATE','[]','{}','zhvi-router-3')"
    )
    conn.execute(
        "INSERT INTO block_cache VALUES(?,?,?,'2026-01-01T00:00:00+00:00')",
        (model_era_cache_key, "kết quả cache model-era", "{}"),
    )
    conn.commit()
    conn.close()


def test_migrate_v1_db_additive_and_cache_invalidated(tmp_path):
    """Story 1.3: mo DB 2.0 bang binary 3.0 — history giu nguyen, cache model-era invalid."""
    from zhvi.config import ROUTE_VIETPHRASE
    from zhvi.state import SCHEMA_VERSION

    db = tmp_path / "old.sqlite3"
    old_cache_key = "model-era-cache-key"
    _make_v1_db(db, old_cache_key)

    st = State(db)  # migrate ngay khi mo
    try:
        # schema version tang (2 = story 1.3 cache invalid; 3 = story 2.2 bang revision)
        ver = st.conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0]
        assert int(ver) == SCHEMA_VERSION == 3

        # history doc duoc, khong rewrite: run/block/route model-era giu nguyen
        assert st.latest_source_revision().id == "rev1"
        run = st.get_run("r1")
        assert run.status == "completed"
        blk = st.get_block("b1")
        assert blk["final_text"] == "kết quả cũ"
        rd = st.conn.execute("SELECT route FROM route_decisions WHERE block_id='b1'").fetchone()
        assert rd[0] == "HACHIMI_CANDIDATE"  # read-only, khong chuyen hoa

        # cache model-era bi danh dau invalid -> khong hit
        row = st.conn.execute(
            "SELECT invalid FROM block_cache WHERE cache_key=?", (old_cache_key,)
        ).fetchone()
        assert row[0] == 1
        assert st.cache_lookup(old_cache_key) is None

        # run moi chi ghi route VIETPHRASE
        st.resume_or_create("r2", "fp-v3", "rev1", "d2", {})
        _stage_vietphrase(st, "r2", "b2")
        rd2 = st.conn.execute("SELECT route FROM route_decisions WHERE block_id='b2'").fetchone()
        assert rd2[0] == ROUTE_VIETPHRASE
    finally:
        st.close()


def _stage_vietphrase(s: State, run_id: str, block_id: str) -> None:
    s.stage_block(
        run_id=run_id, block_id=block_id, chapter_ordinal=0, block_ordinal=2,
        source_start=0, source_end=10, source_hash="h2",
        final_text="kết quả mới", qa={"coverage": 1.0},
        route="VIETPHRASE", reasons=[], features={}, router_version="none",
        attempt={"id": "a2", "engine": "vietphrase-lattice", "input_hash": "h2", "status": "ok"},
    )
