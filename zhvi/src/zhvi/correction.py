"""Diff/rollback/affected-block rerun (story 2.5, SPEC CAP-5, AD-2/AD-12).

diff hai revision: entry khac nhau (added/removed/changed theo identity
(layer, scope, source)) + affected keys; affected blocks qua source index
(block chua key). Rollback la CAS active pointer ve revision an toan —
khong sua bundle cu (AD-12), event append-only. Correction flow (sua
glossary -> revision moi -> dich lai dung affected) nam trong pipeline
(revision.ensure_active_revision refresh=True + adopt unaffected blocks).
"""
from __future__ import annotations

from .export import node_block_id
from .project import Project, project_lock
from .projection import materialize_projection, read_bundle_entries
from .revision import BUNDLE_FILES
from .state import State
from .vietphrase.loader import to_simplified


def _entries_by_key(project: Project, revision_id: str) -> dict[tuple[str, str, str], str]:
    """(layer, scope, source) -> target tu bundle entries.tsv."""
    out: dict[tuple[str, str, str], str] = {}
    for parts in read_bundle_entries(project, revision_id):
        if len(parts) >= 4:
            out[(parts[0], parts[1], parts[2])] = parts[3]
    return out


def diff_revisions(project: Project, rev_a: str, rev_b: str) -> dict:
    """So sanh 2 bundle: added/removed/changed entries + affected keys."""
    a = _entries_by_key(project, rev_a)
    b = _entries_by_key(project, rev_b)
    added = sorted(k[2] for k in b if k not in a)
    removed = sorted(k[2] for k in a if k not in b)
    changed = sorted(k[2] for k in b if k in a and a[k] != b[k])
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "affected_keys": sorted(set(added) | set(removed) | set(changed)),
    }


def affected_block_ids(doc, keys: set[str], trad_simp: dict[str, str] | None = None) -> list[str]:
    """Block (theo source index) chua bat ky key nao — phồn thể match qua
    mapping giản thể khi duoc truyen."""
    out = []
    for node in doc.translatable_nodes():
        content = to_simplified(node.content, trad_simp) if trad_simp else node.content
        if any(key in content for key in keys):
            out.append(node_block_id(node))
    return sorted(set(out))


def rollback_revision(project: Project, target_revision: str, *, expected_active: str | None = None) -> str:
    """CAS active pointer ve revision an toan (AD-12: rollback KHONG sua
    revision cu — chi doi pointer + event append-only).

    expected_active = active hien tai caller ghi nhan (CAS chu dong, nhu
    publish); None = doc active hien tai (best-effort, khong chong writer khac).
    [Note] Content-addressed: tap entry tuong duong -> cung id, nen 'tao
    revision moi' cua AD-12 triet tieu la pointer-CAS ve id cu (transition
    superseded -> active chap nhan). Projection dung lai tu active moi.
    """
    bundle = project.revisions_dir / target_revision
    for name in BUNDLE_FILES:
        if not (bundle / name).is_file():
            raise RuntimeError(f"revision {target_revision} thieu {name} — khong rollback duoc")
    with project_lock(project, "publish"):
        st = State(project.db_path)
        try:
            st.rollback_active_revision(
                target_revision, expected_active, "book", project.book_id
            )
        finally:
            st.close()
        materialize_projection(project, target_revision)
    return target_revision
