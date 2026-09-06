"""Global registry tai dictionary root (story 4.1 + 4.2, AD-13/AD-17).

Registry xac dinh DUY NHAT qua realpath(dict_dir) — moi resolved root
dung mot .zhvi-registry/ + mot writer lock; chi registry writer duoc
mutate global state/projection. Book DB (state.py) va registry la hai
mutation scope rieng biet.
"""
from __future__ import annotations

import fcntl
import os
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

# Leaf helper tu state — registry KHONG import class State/book DB (hai
# mutation scope rieng biet, AD-13).
from zhvi.state import cursor_dicts, utc_now

REGISTRY_DIRNAME = ".zhvi-registry"
# Schema version registry rieng voi book DB (state.SCHEMA_VERSION).
# v1 (story 4.1): chi meta.
# v2 (story 4.2): them global_evidence + book_sources (AD-17 dedupe +
#   active source revision pointer) — additive, khong drop/sua v1 (AD-19).
# Bang global candidate/entry/active revision thuoc 4.3.
REGISTRY_SCHEMA_VERSION = 2

_REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS global_evidence(
  book_id TEXT NOT NULL,
  source_revision_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  occurrence_span TEXT NOT NULL,
  dictionary_revision_id TEXT NOT NULL,
  group_name TEXT NOT NULL,
  signals_json TEXT NOT NULL,
  score REAL NOT NULL DEFAULT 0.0,
  ingested_at TEXT NOT NULL,
  UNIQUE(book_id, source_revision_id, candidate_id, occurrence_span)
);
CREATE TABLE IF NOT EXISTS book_sources(
  book_id TEXT PRIMARY KEY,
  active_source_revision_id TEXT NOT NULL,
  active_source_created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class EvidenceRecord:
    """Payload bat bien book gui vao registry (AD-17).

    occurrence_span la TEXT opaque voi registry — submitter dinh nghia
    semantics (learning/ingest.py: dat bang group_name cua evidence).
    source_created_at: created_at cua source_revisions trong book DB —
    registry dung de chon active revision, khong tin thu tu goi ingest.
    """

    book_id: str
    source_revision_id: str
    candidate_id: str
    occurrence_span: str
    dictionary_revision_id: str
    group_name: str
    signals_json: str
    score: float
    source_created_at: str


class RegistryError(RuntimeError):
    pass


def resolve_registry_dir(dict_dir: Path | str) -> Path:
    """realpath(dict_dir) resolve symlink TRUOC khi xac dinh registry
    (data-model 'Concurrency': moi resolved root dung mot registry)."""
    return Path(os.path.realpath(dict_dir)) / REGISTRY_DIRNAME


class RegistryState:
    """SQLite global state tai <registry>/state.sqlite3 — copy pattern
    State.__init__ (WAL + synchronous=FULL + meta schema_version)."""

    def __init__(self, registry_dir: Path) -> None:
        registry_dir.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(registry_dir / "state.sqlite3")
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=FULL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript(_REGISTRY_SCHEMA)
        cur = self.conn.execute("SELECT value FROM meta WHERE key='schema_version'")
        row = cur.fetchone()
        db_version = int(row[0]) if row is not None else 0
        if db_version > REGISTRY_SCHEMA_VERSION:
            # khac State.__init__: dong conn truoc raise — khong leak connection.
            self.conn.close()
            raise RegistryError(
                f"Registry schema {db_version} moi hon binary {REGISTRY_SCHEMA_VERSION}"
            )
        if db_version < REGISTRY_SCHEMA_VERSION:
            self._migrate(db_version)
        self.conn.commit()

    def _migrate(self, from_version: int) -> None:
        """Migration additive (AD-19): chi add/transform, khong drop."""
        with self.conn:
            # v0 -> v1 (4.1) / v1 -> v2 (4.2): bang tao boi _REGISTRY_SCHEMA
            # (CREATE IF NOT EXISTS) — additive; bang global candidate/entry
            # cua 4.3 se bump version o day.
            self.conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(REGISTRY_SCHEMA_VERSION),),
            )

    def cross_book_summary(self) -> list[dict]:
        """Per candidate: books = DISTINCT book_id, occurrences = so row —
        CHI tinh row cua active source revision moi book (AD-17). Query
        thuan, khong gate — 4.3 dung cho hard gates."""
        return cursor_dicts(self.conn.execute(
            "SELECT ge.candidate_id, COUNT(DISTINCT ge.book_id) AS books, "
            "COUNT(*) AS occurrences FROM global_evidence ge "
            "JOIN book_sources bs ON bs.book_id = ge.book_id "
            "AND bs.active_source_revision_id = ge.source_revision_id "
            "GROUP BY ge.candidate_id ORDER BY ge.candidate_id"
        ))

    def close(self) -> None:
        self.conn.close()


def ingest_evidence(
    registry_dir: Path, records: list[EvidenceRecord]
) -> dict:
    """Ingest evidence bat bien vao registry (AD-17, AC 4.2).

    - Giu registry_lock quanh toan bo mutation (AD-13).
    - INSERT OR IGNORE theo UNIQUE(book_id, source_revision_id, candidate_id,
      occurrence_span): re-ingest trung key la no-op (copy project khong
      tang cross-book count).
    - Upsert book_sources: pointer chi move khi source_created_at MOI HON
      (chong ingest out-of-order lui active revision).
    """
    with registry_lock(registry_dir):
        st = RegistryState(registry_dir)
        try:
            now = utc_now()
            inserted = 0
            with st.conn:
                for r in records:
                    cur = st.conn.execute(
                        "INSERT OR IGNORE INTO global_evidence("
                        "book_id, source_revision_id, candidate_id, "
                        "occurrence_span, dictionary_revision_id, group_name, "
                        "signals_json, score, ingested_at"
                        ") VALUES(?,?,?,?,?,?,?,?,?)",
                        (
                            r.book_id, r.source_revision_id, r.candidate_id,
                            r.occurrence_span, r.dictionary_revision_id,
                            r.group_name, r.signals_json, r.score, now,
                        ),
                    )
                    # rowcount: 1 neu insert, 0 neu bi dedupe boi UNIQUE.
                    inserted += max(cur.rowcount, 0)
                    # Upsert pointer tung record: WHERE chong lui la hang rao
                    # DUY NHAT — dung moi thu tu record trong batch lan thu tu
                    # goi ingest (out-of-order). Boi vi so sanh string ISO
                    # (utc_now: isoformat seconds, timezone co dinh +00:00),
                    # moi writer dung cung format thi thu tu tuong dong.
                    st.conn.execute(
                        "INSERT INTO book_sources("
                        "book_id, active_source_revision_id, "
                        "active_source_created_at, updated_at"
                        ") VALUES(?,?,?,?) "
                        "ON CONFLICT(book_id) DO UPDATE SET "
                        "active_source_revision_id=excluded.active_source_revision_id, "
                        "active_source_created_at=excluded.active_source_created_at, "
                        "updated_at=excluded.updated_at "
                        "WHERE excluded.active_source_created_at "
                        "> book_sources.active_source_created_at",
                        (r.book_id, r.source_revision_id,
                         r.source_created_at, now),
                    )
            return {"submitted": len(records), "inserted": inserted}
        finally:
            st.close()


@contextmanager
def registry_lock(registry_dir: Path):
    """Registry writer lock (AD-13): chi mot writer mutate global
    state/projection. Copy pattern project_lock — exit loi ro rang kem
    path lock. KHONG giu lock trong discovery; chi lock khi
    build/activate global revision (data-model 'Concurrency')."""
    locks_dir = registry_dir / "locks"
    locks_dir.mkdir(parents=True, exist_ok=True)
    path = locks_dir / "registry.lock"
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            # Doc pid holder da ghi trong lock file (task 2.2: message kem pid).
            holder_pid = ""
            try:
                holder_pid = path.read_text(encoding="utf-8").strip()
            except OSError:
                pass  # khong doc duoc pid — van bao day du path lock
            raise RegistryError(
                f"Một process khác đang giữ lock registry: {path}"
                + (f" (pid={holder_pid})" if holder_pid else "")
            ) from None
        os.write(fd, f"{os.getpid()}\n".encode())
        yield
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
