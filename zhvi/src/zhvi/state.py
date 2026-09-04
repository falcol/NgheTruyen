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

SCHEMA_VERSION = 3

# Trang thai dictionary revision (data-model): building/validating la phase
# in-memory cua builder; row DB chi ton tai tu 'ready'. 'rejected' = build
# fail (BuildError) — khong tao row.
REV_READY = "ready"
REV_ACTIVE = "active"
REV_SUPERSEDED = "superseded"
REV_REVOKED = "revoked"  # story 2.5: rollback/revoke tao revision thay the
REV_REJECTED = "rejected"


class StaleActiveError(RuntimeError):
    """Active revision da doi giua chung (writer khac activate truoc) — caller
    phai doc active moi va evaluate/build lai (SPEC AD-13 CAS)."""

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
    created_at TEXT NOT NULL,
    invalid INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS dictionary_revisions (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    manifest_json TEXT NOT NULL,
    bundle_path TEXT NOT NULL,
    created_at TEXT NOT NULL,
    activated_at TEXT
);
CREATE TABLE IF NOT EXISTS active_revisions (
    scope_type TEXT NOT NULL,
    scope_id TEXT NOT NULL,
    revision_id TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (scope_type, scope_id)
);

CREATE INDEX IF NOT EXISTS idx_blocks_run ON blocks(run_id, status);
CREATE INDEX IF NOT EXISTS idx_attempts_block ON attempts(block_id);
"""


def utc_now() -> str:
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
        db_version = int(row[0]) if row is not None else 0
        if db_version > SCHEMA_VERSION:
            raise RuntimeError(f"DB schema {db_version} moi hon binary {SCHEMA_VERSION}")
        if db_version < SCHEMA_VERSION:
            self._migrate(db_version)
        self.conn.commit()

    def _migrate(self, from_version: int) -> None:
        """Migration additive (SPEC AD-19): chi add/transform — khong drop/rewrite lich su."""
        with self.conn:
            if from_version < 2:
                # v1 -> v2 (story 1.3): moi cache v1 sinh voi cache key model-era
                # (chua prompt/router fingerprint) -> danh dau invalid, khong tai dung.
                cols = {r[1] for r in self.conn.execute("PRAGMA table_info(block_cache)")}
                if "invalid" not in cols:
                    self.conn.execute(
                        "ALTER TABLE block_cache ADD COLUMN invalid INTEGER NOT NULL DEFAULT 0"
                    )
                self.conn.execute("UPDATE block_cache SET invalid=1")
            # v2 -> v3 (story 2.2): bang dictionary_revisions + active_revisions
            # tao boi _SCHEMA (CREATE IF NOT EXISTS) — additive, khong invalidate cache.
            self.conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def close(self) -> None:
        self.conn.close()

    # ---- dictionary revisions (story 2.2, AD-13/AD-15) ----
    def activate_revision(
        self,
        revision_id: str,
        manifest_json: str,
        bundle_path: str,
        scope_type: str,
        scope_id: str,
        expected_active: str | None,
    ) -> str | None:
        """MOT transaction: insert revision 'ready' + CAS active pointer.

        CAS that (AD-13): pointer chi doi khi van dang tro expected_active —
        UPDATE ... WHERE revision_id=expected (atomic theo row, khong TOCTOU);
        kich hoat lan dau dung INSERT, writer khac den truoc -> unique key
        raise -> StaleActiveError. Stale: rollback toan bo (khong row moi),
        bundle da rename thanh orphan — GC don. Tra revision active cu
        (replaced) hoac None.
        """
        now = utc_now()
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO dictionary_revisions VALUES (?,?,?,?,?,?)",
                (revision_id, REV_READY, manifest_json, bundle_path, now, None),
            )
            if expected_active is None:
                try:
                    self.conn.execute(
                        "INSERT INTO active_revisions VALUES (?,?,?,?)",
                        (scope_type, scope_id, revision_id, now),
                    )
                except sqlite3.IntegrityError as exc:
                    raise StaleActiveError(
                        f"active revision da ton tai cho scope ({scope_type},{scope_id})"
                        " — evaluate/build lai tren active moi"
                    ) from exc
            else:
                cur = self.conn.execute(
                    "UPDATE active_revisions SET revision_id=?, updated_at=?"
                    " WHERE scope_type=? AND scope_id=? AND revision_id=?",
                    (revision_id, now, scope_type, scope_id, expected_active),
                )
                if cur.rowcount == 0:
                    raise StaleActiveError(
                        f"active revision da doi (ky vong {expected_active})"
                        " — evaluate/build lai tren active moi"
                    )
            replaced = expected_active if expected_active != revision_id else None
            if replaced is not None:
                self.conn.execute(
                    "UPDATE dictionary_revisions SET status=? WHERE id=?",
                    (REV_SUPERSEDED, replaced),
                )
            self.conn.execute(
                "UPDATE dictionary_revisions SET status=?, activated_at=? WHERE id=?",
                (REV_ACTIVE, now, revision_id),
            )
        return replaced

    def active_revision_id(self, scope_type: str, scope_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT revision_id FROM active_revisions WHERE scope_type=? AND scope_id=?",
            (scope_type, scope_id),
        ).fetchone()
        return row[0] if row else None

    # ---- source revisions ----
    def upsert_source_revision(
        self, id_: str, content_hash: str, encoding: str, byte_size: int, snapshot_path: str
    ) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO source_revisions VALUES (?,?,?,?,?,?)",
            (id_, content_hash, encoding, byte_size, snapshot_path, utc_now()),
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
            self.conn.execute("UPDATE runs SET status='running', updated_at=? WHERE id=?", (utc_now(), run.id))
            self.conn.commit()
            return RunRow(*self.conn.execute("SELECT * FROM runs WHERE id=?", (run.id,)).fetchone()), False
        now = utc_now()
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
            "UPDATE runs SET status=?, updated_at=? WHERE id=?", (status, utc_now(), run_id)
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
                 attempt["status"], attempt.get("duration_ms"), utc_now()),
            )
            if cache_key is not None:
                self.conn.execute(
                    "INSERT OR REPLACE INTO block_cache VALUES (?,?,?,?,0)",
                    (cache_key, final_text, json.dumps(qa, ensure_ascii=False), utc_now()),
                )

    def cache_lookup(self, cache_key: str) -> dict | None:
        row = self.conn.execute(
            "SELECT final_text, qa_json FROM block_cache WHERE cache_key=? AND invalid=0",
            (cache_key,),
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
    def route_counts(self, run_id: str) -> dict[str, int]:
        """Dem block committed theo route — tu route_decisions (join blocks).

        Nguon duy nhat cho metric routes: moi block staged (ke ca cache-hit)
        deu co row route_decisions (CAP-9).
        """
        cur = self.conn.execute(
            "SELECT r.route, COUNT(*) FROM route_decisions r JOIN blocks b ON b.id=r.block_id "
            "WHERE b.run_id=? GROUP BY r.route",
            (run_id,),
        )
        return {route: cnt for route, cnt in cur.fetchall()}

    def status_info(self) -> dict:
        run = self.latest_run()
        if run is None:
            return {"status": "no-run"}
        total = self.block_count(run.id)
        committed = self.block_count(run.id, "committed")
        routes = self.route_counts(run.id)
        return {
            "run_id": run.id,
            "status": run.status,
            "fingerprint": run.fingerprint[:16],
            "blocks_total": total,
            "blocks_committed": committed,
            "routes": routes,
            "updated_at": run.updated_at,
        }
