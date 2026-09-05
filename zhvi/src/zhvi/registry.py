"""Global registry tai dictionary root (story 4.1, AD-13/AD-17).

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
from pathlib import Path

REGISTRY_DIRNAME = ".zhvi-registry"
# Schema version registry rieng voi book DB (state.SCHEMA_VERSION).
# v1 (story 4.1): chi meta — bang global evidence/candidate/active pointer
# thuoc 4.2/4.3, them qua migration additive (AD-19).
REGISTRY_SCHEMA_VERSION = 1

_REGISTRY_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
"""


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
            # v0 -> v1 (story 4.1): bang meta tao boi _SCHEMA (CREATE IF NOT
            # EXISTS) — additive; bang global 4.2/4.3 se bump version o day.
            self.conn.execute(
                "INSERT OR REPLACE INTO meta(key, value) VALUES('schema_version', ?)",
                (str(REGISTRY_SCHEMA_VERSION),),
            )

    def close(self) -> None:
        self.conn.close()


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
