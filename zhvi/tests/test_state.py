"""Tests cho state.py + fingerprint + resume/crash (thiet ke muc 8/27/29/39)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from zhvi.fingerprint import build_run_fingerprint
from zhvi.config import Config
from zhvi.project import create_project
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
