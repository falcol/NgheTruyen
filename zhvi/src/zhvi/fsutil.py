"""Filesystem writers + ownership guard (story 2.4, SPEC AD-5). Leaf module.

Moi writer may phai di qua day: guard chan ghi vao file human-owned
(Custom.txt, QualityOverrides.txt, VietPhrase_*.txt, glossary.manual.tsv,
.manual.*) — may khong bao gio ghi chu khong phai no (spec Non-goals).
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
from pathlib import Path

HUMAN_OWNED_EXACT = frozenset({
    "Custom.txt",
    "QualityOverrides.txt",
    "ContextPatterns.txt",
    "glossary.manual.tsv",
})
HUMAN_OWNED_GLOBS = ("VietPhrase_*.txt",)


class OwnershipError(RuntimeError):
    """Writer may co gang ghi file human-owned — bi chan (AD-5)."""


def assert_machine_writable(path: Path | str) -> None:
    """Raise OwnershipError neu path la file human-owned."""
    name = Path(path).name
    if (
        name in HUMAN_OWNED_EXACT
        or any(fnmatch.fnmatch(name, g) for g in HUMAN_OWNED_GLOBS)
        or ".manual." in name
    ):
        raise OwnershipError(f"file human-owned — may khong duoc ghi: {path}")


def fsync_dir(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(destination: Path, content: bytes) -> str:
    """Temp cung filesystem, fsync, os.replace, fsync dir (muc 30).
    Guard ownership truoc khi ghi (story 2.4)."""
    assert_machine_writable(destination)
    tmp = destination.with_name(destination.name + ".tmp")
    with tmp.open("wb") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    digest = hashlib.sha256(content).hexdigest()
    os.replace(tmp, destination)
    fsync_dir(destination.parent)
    return digest
