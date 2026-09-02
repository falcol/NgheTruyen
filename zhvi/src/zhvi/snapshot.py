"""Snapshot an toàn khi import TXT (thiet ke muc 6).

Trinh tu: stat -> copy bytes vao tmp (vua copy vua tinh SHA-256) -> stat lai
-> neu file thay doi, bo tmp va retry huu han -> fsync -> atomic rename.
Decode UTF-8 strict; loi decode bao cao byte offset, khong auto-detect encoding.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

from .project import Project

MAX_SNAPSHOT_RETRIES = 3


class SnapshotError(RuntimeError):
    pass


class DecodeError(SnapshotError):
    def __init__(self, path: Path, byte_offset: int, encoding: str) -> None:
        super().__init__(
            f"Decode {encoding} that bai tai {path} byte offset {byte_offset}. "
            f"Chi dinh encoding khac: --encoding gb18030"
        )
        self.byte_offset = byte_offset


@dataclass(frozen=True)
class SourceRevision:
    id: str  # sha256 hex cua noi dung
    encoding: str
    byte_size: int
    snapshot_path: Path

    @property
    def content_hash(self) -> str:
        return self.id


def _stat_sig(st: os.stat_result) -> tuple[int, float, int]:
    return (st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def decode_strict(data: bytes, encoding: str) -> str:
    try:
        return data.decode(encoding)
    except UnicodeDecodeError as e:
        raise DecodeError(Path("<bytes>"), e.start, encoding) from e


def import_snapshot(
    project: Project,
    source_file: Path,
    *,
    encoding: str = "utf-8",
    replace_existing: bool = False,
) -> SourceRevision:
    """Copy source vao .zhvi/sources/<sha256>.txt bat bien. Tra ve revision."""
    if not source_file.is_file():
        raise SnapshotError(f"Khong tim thay file source: {source_file}")
    project.sources_dir.mkdir(parents=True, exist_ok=True)

    last_err: Exception | None = None
    for attempt in range(1, MAX_SNAPSHOT_RETRIES + 1):
        before = _stat_sig(source_file.stat())
        tmp = project.sources_dir / f".tmp-import-{os.getpid()}-{attempt}"
        digest = hashlib.sha256()
        try:
            with source_file.open("rb") as src, tmp.open("wb") as dst:
                while chunk := src.read(1 << 20):
                    digest.update(chunk)
                    dst.write(chunk)
                dst.flush()
                os.fsync(dst.fileno())
            after = _stat_sig(source_file.stat())
            if before != after:
                raise SnapshotError("File source thay doi trong luc copy — thu lai")
            sha = digest.hexdigest()
            final = project.sources_dir / f"{sha}.txt"
            if final.exists() and not replace_existing:
                tmp.unlink(missing_ok=True)
                data = final.read_bytes()
                decode_strict(data, encoding)  # van verify decode theo encoding
                return SourceRevision(sha, encoding, len(data), final)
            os.replace(tmp, final)
            _fsync_dir(final.parent)
            data = final.read_bytes()
            decode_strict(data, encoding)
            return SourceRevision(sha, encoding, len(data), final)
        except SnapshotError:
            tmp.unlink(missing_ok=True)
            raise
        except UnicodeDecodeError as e:
            tmp.unlink(missing_ok=True)
            raise DecodeError(source_file, e.start, encoding) from e
        except OSError as e:  # transient IO
            tmp.unlink(missing_ok=True)
            last_err = e
    raise SnapshotError(f"Import that bai sau {MAX_SNAPSHOT_RETRIES} lan: {last_err}")


def _fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
