"""Projection + startup reconciler (story 2.4, SPEC AD-8, AD-15 buoc 10).

glossary.auto.tsv chi la PROJECTION dung lai tu active pointer — khong phai
nguon chan ly (SQLite so huu state). Materialize SAU DB commit; crash truoc
khi dung xong duoc reconciler luc startup dung lai. Bundle thieu/hash sai
la fatal corruption voi thong bao ro.

DEFERRAL (epic 4): AutoVietPhrase.txt (projection auto TOAN CUC tai dict_dir)
chi duoc materialize boi global registry — khong thuoc scope book project
nao, nen story 2.4 chi lam projection book scope.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from .fsutil import OwnershipError, assert_machine_writable, atomic_write
from .project import Project
from .state import State
from .vietphrase.layers import Layer

__all__ = [
    "AUTO_PROJECTION", "OwnershipError", "assert_machine_writable",
    "materialize_projection", "reconcile_project",
]

PROJECTION_HEADER = "# machine-owned projection — dung lai tu active revision (AD-8); sua = sua entry + publish revision moi\n"
AUTO_PROJECTION = "glossary.auto.tsv"
# Dong bo voi revision.BUNDLE_FILES (import chéo tao cycle — revision import projection)
BUNDLE_FILES = ("manifest.json", "entries.tsv", "patterns.jsonl", "dictionary.bin")


def _auto_entries_tsv(project: Project, revision_id: str) -> str:
    """Doc entries auto:book tu bundle da pin (entries.tsv) — projection dung
    tu bundle bat bien, khong doc lai tu state store."""
    rows = (project.revisions_dir / revision_id / "entries.tsv").read_text(
        encoding="utf-8"
    ).splitlines()
    lines = []
    for row in rows:
        parts = row.split("\t")
        if len(parts) >= 4 and parts[0] == str(int(Layer.BOOK_AUTO)) and parts[1] == "book":
            lines.append(f"{parts[2]}={parts[3]}")
    return PROJECTION_HEADER + "\n".join(lines) + ("\n" if lines else "")


def materialize_projection(project: Project, revision_id: str) -> Path:
    """Dung glossary.auto.tsv tu active revision (goi SAU DB commit — buoc 10)."""
    out = project.root / AUTO_PROJECTION
    atomic_write(out, _auto_entries_tsv(project, revision_id).encode("utf-8"))
    return out


def reconcile_project(project: Project) -> str | None:
    """Kiem active pointer + bundle hash + projection luc startup.

    - Chua co active: noop.
    - Bundle thieu file / manifest hash khong khop id: FATAL corruption
      (RuntimeError, thong bao ro) — khong tu dong chua.
    - Projection cu/thieu (crash giua commit va materialize): dung lai tu
      active pointer.
    Tra revision id active, hoac None.
    """
    st = State(project.db_path)
    try:
        active = st.active_revision_id("book", project.book_id)
    finally:
        st.close()
    if active is None:
        return None

    bundle = project.revisions_dir / active
    for name in BUNDLE_FILES:
        if not (bundle / name).is_file():
            raise RuntimeError(
                f"corrupt: active revision {active} thieu {name} trong {bundle}"
                " — chay zhvi doctor; bundle mat la mat du lieu, khong tu chua"
            )
    digest = hashlib.sha256((bundle / "manifest.json").read_bytes()).hexdigest()
    if digest != active:
        raise RuntimeError(
            f"corrupt: bundle {active} manifest hash khong khop ({digest[:16]})"
            " — bundle bi sua doi sau publish"
        )

    proj_file = project.root / AUTO_PROJECTION
    expected = _auto_entries_tsv(project, active)
    if not proj_file.is_file() or proj_file.read_text(encoding="utf-8") != expected:
        materialize_projection(project, active)
    return active
