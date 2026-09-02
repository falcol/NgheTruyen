"""SQLite state store (thiet ke muc 27/28/29). WAL, mot controller writer.

Block chi COMMITTED khi output + trace + QA metadata vao CUNGL mot transaction.
Resume: block RUNNING chua commit -> PENDING.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_revisions (
    id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL UNIQUE,
    encoding TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    snapshot_path TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS runs (
    id TEXT PRIMARY KEY,
    source_revision_id TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    dictionary_revision_id TEXT NOT NULL,
    resolved_config_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(fingerprint)
);

CREATE TABLE IF NOT EXISTS blocks (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    chapter_ordinal INTEGER NOT NULL,
    block_ordinal INTEGER NOT NULL,
    source_start INTEGER NOT NULL,
    source_end INTEGER NOT NULL,
    source_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    final_text TEXT,
    qa_json TEXT,
    UNIQUE(run_id, chapter_ordinal, block_ordinal)
);

CREATE TABLE IF NOT EXISTS attempts (
    id TEXT PRIMARY KEY,
    block_id TEXT NOT NULL,
    engine TEXT NOT NULL,
    model_digest TEXT,
    prompt_hash TEXT,
    input_hash TEXT NOT NULL,
    output_json TEXT,
    status TEXT NOT NULL,
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS route_decisions (
    block_id TEXT PRIMARY KEY,
    route TEXT NOT NULL,
    reasons_json TEXT NOT NULL,
    features_json TEXT NOT NULL,
    router_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS term_candidates (
    id TEXT PRIMARY KEY,
    book_id TEXT NOT NULL,
    source TEXT NOT NULL,
    proposed_target TEXT NOT NULL,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    provenance_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_events (
    id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    segment_id TEXT,
    candidate_id TEXT,
    entry_id TEXT,
    before_json TEXT,
    after_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS block_cache (
    cache_key TEXT PRIMARY KEY,
    final_text TEXT NOT NULL,
    qa_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_blocks_run ON blocks(run_id, status);
CREATE INDEX IF NOT EXISTS idx_attempts_block ON attempts(block_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class SourceRevisionRow:
    id: str
    content_hash: str
    encoding: str
    byte_size: int
    snapshot_path: str
    created_at: str


@dataclass
class RunRow:
    id: str
    source_revision_id: str
    fingerprint: str
    dictionary_revision_id: str
    resolved_config_json: str
    status: str
    created_at: str
    updated_at: str

    @property
    def resolved_config(self) -> dict:
        return json.loads(self.resolved_config_json)


class State:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_SCHEMA)
        cur = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = cur.fetchone()
        if row is None:
            self.conn.execute(
                "INSERT INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )
            self.conn.commit()
        elif int(row[0]) > SCHEMA_VERSION:
            raise RuntimeError(f"DB schema {row[0]} moi hon binary {SCHEMA_VERSION}")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # ---- source revisions ----
    def upsert_source_revision(
        self, id_: str, content_hash: str, encoding: str, byte_size: int, snapshot_path: str
    ) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO source_revisions VALUES (?,?,?,?,?,?)",
            (id_, content_hash, encoding, byte_size, snapshot_path, _now()),
        )
        self.conn.commit()

    def latest_source_revision(self) -> SourceRevisionRow | None:
        cur = self.conn.execute(
            "SELECT id, content_hash, encoding, byte_size, snapshot_path, created_at "
            "FROM source_revisions ORDER BY created_at DESC LIMIT 1"
        )
        row = cur.fetchone()
        return SourceRevisionRow(*row) if row else None

    # ---- runs ----
    def resume_or_create(
        self,
        run_id: str,
        fingerprint: str,
        source_revision_id: str,
        dictionary_revision_id: str,
        resolved_config: dict,
    ) -> tuple[RunRow, bool]:
        """Tra (run, created_moi). Cung fingerprint -> resume (muc 4/8)."""
        cur = self.conn.execute("SELECT * FROM runs WHERE fingerprint=?", (fingerprint,))
        row = cur.fetchone()
        if row:
            run = RunRow(*row)
            # block RUNNING chua commit -> pending (muc 29)
            self.conn.execute(
                "UPDATE blocks SET status='pending' WHERE run_id=? AND status='running'",
                (run.id,),
            )
            self.conn.execute("UPDATE runs SET status='running', updated_at=? WHERE id=?", (_now(), run.id))
            self.conn.commit()
            return RunRow(*self.conn.execute("SELECT * FROM runs WHERE id=?", (run.id,)).fetchone()), False
        now = _now()
        self.conn.execute(
            "INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)",
            (run_id, source_revision_id, fingerprint, dictionary_revision_id,
             json.dumps(resolved_config, sort_keys=True, ensure_ascii=False), "running", now, now),
        )
        self.conn.commit()
        return self.get_run(run_id), True

    def get_run(self, run_id: str) -> RunRow:
        row = self.conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise KeyError(run_id)
        return RunRow(*row)

    def find_completed_run(self, fingerprint: str) -> RunRow | None:
        cur = self.conn.execute(
            "SELECT * FROM runs WHERE fingerprint=? AND status IN ('completed','exported')",
            (fingerprint,),
        )
        row = cur.fetchone()
        return RunRow(*row) if row else None

    def set_run_status(self, run_id: str, status: str) -> None:
        self.conn.execute(
            "UPDATE runs SET status=?, updated_at=? WHERE id=?", (status, _now(), run_id)
        )
        self.conn.commit()

    def latest_run(self) -> RunRow | None:
        row = self.conn.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT 1").fetchone()
        return RunRow(*row) if row else None

    # ---- blocks ----
    def stage_block(
        self,
        run_id: str,
        block_id: str,
        chapter_ordinal: int,
        block_ordinal: int,
        source_start: int,
        source_end: int,
        source_hash: str,
        final_text: str,
        qa: dict[str, Any],
        route: str,
        reasons: list[str],
        features: dict[str, Any],
        router_version: str,
        attempt: dict[str, Any],
        cache_key: str | None = None,
    ) -> None:
        """Commit block + trace + attempt trong MOT transaction (muc 27)."""
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO blocks VALUES (?,?,?,?,?,?,?,?,?,?)",
                (block_id, run_id, chapter_ordinal, block_ordinal, source_start, source_end,
                 source_hash, "committed", final_text, json.dumps(qa, ensure_ascii=False)),
            )
            self.conn.execute(
                "INSERT OR REPLACE INTO route_decisions VALUES (?,?,?,?,?)",
                (block_id, route, json.dumps(reasons), json.dumps(features, ensure_ascii=False), router_version),
            )
            self.conn.execute(
                "INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?,?)",
                (attempt["id"], block_id, attempt["engine"], attempt.get("model_digest"),
                 attempt.get("prompt_hash"), attempt["input_hash"],
                 json.dumps(attempt.get("output", {}), ensure_ascii=False),
                 attempt["status"], attempt.get("duration_ms"), _now()),
            )
            if cache_key is not None:
                self.conn.execute(
                    "INSERT OR REPLACE INTO block_cache VALUES (?,?,?,?)",
                    (cache_key, final_text, json.dumps(qa, ensure_ascii=False), _now()),
                )

    def cache_lookup(self, cache_key: str) -> dict | None:
        row = self.conn.execute(
            "SELECT final_text, qa_json FROM block_cache WHERE cache_key=?", (cache_key,)
        ).fetchone()
        if row is None:
            return None
        return {"final_text": row[0], "qa": json.loads(row[1])}

    def get_block(self, block_id: str) -> sqlite3.Row | None:
        cur = self.conn.execute("SELECT * FROM blocks WHERE id=?", (block_id,))
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))

    def committed_blocks(self, run_id: str) -> dict[str, dict]:
        cur = self.conn.execute("SELECT * FROM blocks WHERE run_id=? AND status='committed'", (run_id,))
        cols = [d[0] for d in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}

    def block_count(self, run_id: str, status: str | None = None) -> int:
        q = "SELECT COUNT(*) FROM blocks WHERE run_id=?"
        args: list = [run_id]
        if status:
            q += " AND status=?"
            args.append(status)
        return self.conn.execute(q, args).fetchone()[0]

    # ---- status / report ----
    def status_info(self) -> dict:
        run = self.latest_run()
        if run is None:
            return {"status": "no-run"}
        total = self.block_count(run.id)
        committed = self.block_count(run.id, "committed")
        routes: dict[str, int] = {}
        cur = self.conn.execute(
            "SELECT r.route, COUNT(*) FROM route_decisions r JOIN blocks b ON b.id=r.block_id "
            "WHERE b.run_id=? GROUP BY r.route",
            (run.id,),
        )
        for route, cnt in cur.fetchall():
            routes[route] = cnt
        return {
            "run_id": run.id,
            "status": run.status,
            "fingerprint": run.fingerprint[:16],
            "blocks_total": total,
            "blocks_committed": committed,
            "routes": routes,
            "updated_at": run.updated_at,
        }
