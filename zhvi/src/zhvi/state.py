"""SQLite state store (thiet ke muc 27/28/29). WAL, mot controller writer.

Block chi COMMITTED khi output + trace + QA metadata vao CUNGL mot transaction.
Resume: block RUNNING chua commit -> PENDING.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 6

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
CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    source_revision_id TEXT NOT NULL,
    dictionary_revision_id TEXT NOT NULL,
    ngram TEXT NOT NULL,
    ngram_original TEXT NOT NULL,
    length INTEGER NOT NULL,
    total_count INTEGER NOT NULL,
    chapter_count INTEGER NOT NULL,
    chapters_json TEXT NOT NULL,
    left_contexts_json TEXT NOT NULL,
    right_contexts_json TEXT NOT NULL,
    left_entropy REAL NOT NULL,
    right_entropy REAL NOT NULL,
    min_pmi REAL NOT NULL,
    is_single_char_run INTEGER NOT NULL DEFAULT 0,
    is_unknown INTEGER NOT NULL DEFAULT 0,
    alt_segmentation INTEGER NOT NULL DEFAULT 0,
    repetition_unstable INTEGER NOT NULL DEFAULT 0,
    pattern_hits_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    UNIQUE(source_revision_id, ngram)
);

CREATE INDEX IF NOT EXISTS idx_blocks_run ON blocks(run_id, status);
CREATE INDEX IF NOT EXISTS idx_attempts_block ON attempts(block_id);
CREATE INDEX IF NOT EXISTS idx_observations_rev
    ON observations(source_revision_id, total_count DESC);
CREATE TABLE IF NOT EXISTS candidate_evidence (
    id TEXT PRIMARY KEY,
    candidate_id TEXT NOT NULL,
    book_id TEXT NOT NULL,
    dictionary_revision_id TEXT NOT NULL,
    group_name TEXT NOT NULL,
    signals_json TEXT NOT NULL,
    score REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    UNIQUE(candidate_id, group_name)
);
CREATE INDEX IF NOT EXISTS idx_evidence_scope
    ON candidate_evidence(book_id, dictionary_revision_id);
"""

_OBS_COLS = (
    "id", "source_revision_id", "dictionary_revision_id", "ngram",
    "ngram_original", "length", "total_count", "chapter_count",
    "chapters_json", "left_contexts_json", "right_contexts_json",
    "left_entropy", "right_entropy", "min_pmi", "is_single_char_run",
    "is_unknown", "alt_segmentation", "repetition_unstable",
    "pattern_hits_json",
)

_CAND_COLS = (
    "id", "book_id", "source", "proposed_target", "kind", "status",
    "provenance_json", "dictionary_revision_id", "eligible_auto",
)

_EV_COLS = (
    "id", "candidate_id", "book_id", "dictionary_revision_id",
    "group_name", "signals_json", "score",
)


def cursor_dicts(cur: sqlite3.Cursor) -> list[dict]:
    """Rows cua cursor thanh list dict theo ten cot (helper dung chung)."""
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


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


@dataclass(frozen=True)
class ObservationRow:
    """Mot observation ngram (story 3.1) — field khop cot bang observations.

    Discovery build row; State lo transaction ghi. Typo field name loi ngay
    luc construct (thay vi KeyError giua transaction nhu dict thuong).
    """

    id: str
    source_revision_id: str
    dictionary_revision_id: str
    ngram: str
    ngram_original: str
    length: int
    total_count: int
    chapter_count: int
    chapters_json: str
    left_contexts_json: str
    right_contexts_json: str
    left_entropy: float
    right_entropy: float
    min_pmi: float
    is_single_char_run: int
    is_unknown: int
    alt_segmentation: int
    repetition_unstable: int
    pattern_hits_json: str


@dataclass(frozen=True)
class EvidenceRow:
    """Evidence mot nhom tin hieu cua mot candidate (story 3.3).

    Score CHI dung xep hang (AD-7) — hard gate la story 3.4.
    """

    id: str
    candidate_id: str
    book_id: str
    dictionary_revision_id: str
    group_name: str  # strength|stability|benefit|risk|scope|regression
    signals_json: str
    score: float


@dataclass(frozen=True)
class CandidateRow:
    """Mot candidate tu observation (story 3.2) — term_candidates mo rong v5."""

    id: str
    book_id: str
    source: str
    proposed_target: str  # '' khi status=unresolved (cot NOT NULL)
    kind: str  # term | name | pattern
    status: str  # candidate | unresolved
    provenance_json: str
    dictionary_revision_id: str
    eligible_auto: int


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
            # v3 -> v4 (story 3.1): bang observations + index tao boi _SCHEMA
            # (CREATE IF NOT EXISTS) — additive, khong anh huong data hien co.
            # v4 -> v5 (story 3.2): term_candidates mo cot dictionary_revision_id
            # + eligible_auto cho candidate builder — additive, bang chua co code ghi.
            # v5 -> v6 (story 3.3): bang candidate_evidence tao boi _SCHEMA
            # (CREATE IF NOT EXISTS) — additive, khong anh huong data hien co.
            if from_version < 5:
                cols = {
                    r[1] for r in self.conn.execute("PRAGMA table_info(term_candidates)")
                }
                if "dictionary_revision_id" not in cols:
                    self.conn.execute(
                        "ALTER TABLE term_candidates "
                        "ADD COLUMN dictionary_revision_id TEXT NOT NULL DEFAULT ''"
                    )
                if "eligible_auto" not in cols:
                    self.conn.execute(
                        "ALTER TABLE term_candidates "
                        "ADD COLUMN eligible_auto INTEGER NOT NULL DEFAULT 0"
                    )
            self.conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    def close(self) -> None:
        self.conn.close()

    # ---- dictionary revisions (story 2.2, AD-13/AD-15) ----
    def _cas_active_locked(
        self, scope_type: str, scope_id: str, revision_id: str,
        expected_active: str | None, now: str,
    ) -> None:
        """CAS active pointer — CHI goi trong transaction dang mo. UPDATE ...
        WHERE revision_id=expected (atomic theo row, khong TOCTOU); kich hoat
        lan dau dung INSERT, writer khac den truoc -> unique key -> stale."""
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

    def _supersede_and_activate_locked(
        self, replaced: str | None, revision_id: str, now: str,
    ) -> None:
        if replaced is not None:
            self.conn.execute(
                "UPDATE dictionary_revisions SET status=? WHERE id=?",
                (REV_SUPERSEDED, replaced),
            )
        self.conn.execute(
            "UPDATE dictionary_revisions SET status=?, activated_at=? WHERE id=?",
            (REV_ACTIVE, now, revision_id),
        )

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

        Stale: rollback toan bo (khong row moi), bundle da rename thanh
        orphan — GC don. Tra revision active cu (replaced) hoac None.
        """
        now = utc_now()
        with self.conn:
            self.conn.execute(
                "INSERT OR REPLACE INTO dictionary_revisions VALUES (?,?,?,?,?,?)",
                (revision_id, REV_READY, manifest_json, bundle_path, now, None),
            )
            self._cas_active_locked(scope_type, scope_id, revision_id, expected_active, now)
            replaced = expected_active if expected_active != revision_id else None
            self._supersede_and_activate_locked(replaced, revision_id, now)
        return replaced

    def rollback_active_revision(
        self,
        target_revision: str,
        expected_active: str | None,
        scope_type: str,
        scope_id: str,
        *,
        action: str = "dict_rollback",
    ) -> None:
        """MOT transaction: CAS active pointer ve target + supersede active cu
        + event append-only (AD-12: rollback khong sua bundle/revision cu).

        [Note] Content-addressed: tap entry tuong duong -> CUNG id — nen
        'revision moi' cua AD-12 triet tieu la pointer-CAS ve id cu; transition
        superseded -> active la hau qua chap nhan cua cach do.
        """
        now = utc_now()
        with self.conn:
            if expected_active is None:
                expected_active = self.active_revision_id(scope_type, scope_id)
            self._cas_active_locked(scope_type, scope_id, target_revision, expected_active, now)
            replaced = expected_active if expected_active != target_revision else None
            self._supersede_and_activate_locked(replaced, target_revision, now)
            self.conn.execute(
                "INSERT INTO feedback_events VALUES (?,?,?,?,?,?,?,?)",
                (uuid.uuid4().hex, action, None, None, None,
                 json.dumps({"active": expected_active}),
                 json.dumps({"active": target_revision}), now),
            )

    def active_revision_id(self, scope_type: str, scope_id: str) -> str | None:
        row = self.conn.execute(
            "SELECT revision_id FROM active_revisions WHERE scope_type=? AND scope_id=?",
            (scope_type, scope_id),
        ).fetchone()
        return row[0] if row else None

    def latest_completed_run_for_source(
        self, source_revision_id: str, exclude_run_id: str | None = None
    ) -> RunRow | None:
        """Run completed/exported gan nhat cua mot source (de seed unaffected
        blocks khi correction tao run moi — story 2.5)."""
        q = (
            "SELECT * FROM runs"
            " WHERE source_revision_id=? AND status IN ('completed','exported')"
        )
        args: list = [source_revision_id]
        if exclude_run_id is not None:
            q += " AND id<>?"
            args.append(exclude_run_id)
        q += " ORDER BY updated_at DESC LIMIT 1"
        row = self.conn.execute(q, args).fetchone()
        return RunRow(*row) if row else None

    def adopt_blocks(self, new_run_id: str, block_ids: list[str]) -> int:
        """Chuyen block da commit sang run moi (story 2.5: block khong chua key
        sua duoc giu nguyen — correction chi dich lai affected).

        [Note] blocks.id la PK toan cuc nen day la DI CHUYEN row (run cu mat
        block, final_text khong doi) — AD-19 "giu lich su" o muc run->block
        bi xoi mon; schema per-run can story rieng. Confirm xu ly?
        """
        with self.conn:
            for bid in block_ids:
                self.conn.execute(
                    "UPDATE blocks SET run_id=? WHERE id=?", (new_run_id, bid)
                )
        return len(block_ids)

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

    # ---- observations (story 3.1) ----
    def replace_observations(
        self, source_revision_id: str, rows: list[ObservationRow]
    ) -> None:
        """Ghi de toan bo observation cua mot source revision trong MOT transaction.

        Discovery deterministic (AC 3.1.2): chay lai cung revision thi replace,
        khong append.
        """
        sql = (
            f"INSERT INTO observations ({','.join(_OBS_COLS)}, created_at) "
            f"VALUES ({','.join('?' * len(_OBS_COLS))}, ?)"
        )
        now = utc_now()
        with self.conn:
            self.conn.execute(
                "DELETE FROM observations WHERE source_revision_id=?",
                (source_revision_id,),
            )
            for row in sorted(rows, key=lambda r: r.ngram):
                self.conn.execute(sql, [getattr(row, c) for c in _OBS_COLS] + [now])

    # ---- term_candidates (story 3.2) ----
    def replace_candidates(
        self, book_id: str, dictionary_revision_id: str, rows: list[CandidateRow]
    ) -> None:
        """Ghi de toan bo candidate cua (book, dictionary_revision) trong 1 transaction.

        Scope truyen ro bang tham so — rows rong van xoa scope (dong semantics
        voi replace_observations; AD-8 — candidate la book learning state).
        """
        sql = (
            f"INSERT INTO term_candidates ({','.join(_CAND_COLS)}) "
            f"VALUES ({','.join('?' * len(_CAND_COLS))})"
        )
        with self.conn:
            self.conn.execute(
                "DELETE FROM term_candidates "
                "WHERE book_id=? AND dictionary_revision_id=?",
                (book_id, dictionary_revision_id),
            )
            for row in sorted(rows, key=lambda r: r.source):
                self.conn.execute(sql, [getattr(row, c) for c in _CAND_COLS])

    # ---- candidate_evidence (story 3.3) ----
    def replace_evidence(
        self, book_id: str, dictionary_revision_id: str, rows: list[EvidenceRow]
    ) -> None:
        """Ghi de toan bo evidence cua (book, dictionary_revision) trong 1 transaction.

        Scope explicit — rows rong van xoa scope (dong semantics
        replace_candidates/replace_observations; AD-8).
        """
        sql = (
            f"INSERT INTO candidate_evidence ({','.join(_EV_COLS)}, created_at) "
            f"VALUES ({','.join('?' * len(_EV_COLS))}, ?)"
        )
        now = utc_now()
        with self.conn:
            self.conn.execute(
                "DELETE FROM candidate_evidence "
                "WHERE book_id=? AND dictionary_revision_id=?",
                (book_id, dictionary_revision_id),
            )
            for row in sorted(rows, key=lambda r: (r.candidate_id, r.group_name)):
                self.conn.execute(sql, [getattr(row, c) for c in _EV_COLS] + [now])

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
