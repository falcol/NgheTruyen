"""Tests cho publish protocol (story 2.2, SPEC AD-15 buoc 8-10, AD-13 CAS).

Temp → fsync → atomic rename → SQLite transaction (insert ready + CAS active
pointer) → projection sau commit (story 2.4). Crash tung buoc khong lam mat
active revision hop le; bundle rename ma chua commit DB = orphan, GC duoc.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

import zhvi.revision as rev
from zhvi.cli import app
from zhvi.project import create_project
from zhvi.revision import AutoEntry, StaleActiveError, build_revision, publish_revision
from zhvi.revision import gc_orphan_revisions
from zhvi.state import State


def _mini_dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mini-dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text("凌天=Lăng Thiên\n青龙=Thanh Long\n", encoding="utf-8")
    return d


def _current_active(project) -> str | None:
    st = State(project.db_path)
    try:
        row = st.conn.execute(
            "SELECT revision_id FROM active_revisions WHERE scope_type='book' AND scope_id=?",
            (project.book_id,),
        ).fetchone()
        return row[0] if row else None
    finally:
        st.close()


def _revision_status(project, revision_id: str) -> str | None:
    st = State(project.db_path)
    try:
        row = st.conn.execute(
            "SELECT status FROM dictionary_revisions WHERE id=?", (revision_id,)
        ).fetchone()
        return row[0] if row else None
    finally:
        st.close()


def test_publish_inserts_ready_and_activates(tmp_path):
    """Publish: transaction insert ready + active pointer; status active."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    result = publish_revision(dict_dir, project, [])
    assert result.status == "active"
    assert _current_active(project) == result.revision_id
    assert _revision_status(project, result.revision_id) == "active"
    assert result.replaced is None  # lan dau — chua co active cu


def test_publish_cas_supersedes_old_active(tmp_path):
    """Publish lan 2 voi expected_active dung: active moi, cu thanh superseded."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    r1 = publish_revision(dict_dir, project, [])
    r2 = publish_revision(
        dict_dir, project, [AutoEntry(source="天煞", target="Thiên Sát")],
        expected_active=r1.revision_id,
    )
    assert _current_active(project) == r2.revision_id
    assert _revision_status(project, r1.revision_id) == "superseded"
    assert _revision_status(project, r2.revision_id) == "active"
    assert r2.replaced == r1.revision_id


def test_publish_stale_writer_rejected(tmp_path):
    """expected_active khac active hien tai (writer khac da activate giua chung)
    -> StaleActiveError, active khong doi, khong row revision moi."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    r1 = publish_revision(dict_dir, project, [])
    r2 = publish_revision(
        dict_dir, project, [AutoEntry(source="天煞", target="Thiên Sát")],
        expected_active=r1.revision_id,
    )
    with pytest.raises(StaleActiveError):
        # writer khac da activate r2 giua chung — ky vong r1 bay gio la stale
        publish_revision(
            dict_dir, project, [AutoEntry(source="玄女", target="Huyền Nữ")],
            expected_active=r1.revision_id,
        )
    assert _current_active(project) == r2.revision_id  # khong doi


def test_crash_before_rename_active_unchanged(tmp_path):
    """Crash giua materialize (truoc atomic rename): active khong doi, chi con
    dir tam — GC dọn duoc."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")

    def boom(*_a, **_kw):
        raise KeyboardInterrupt

    real_replace = rev.os.replace
    rev.os.replace = boom
    try:
        with pytest.raises(KeyboardInterrupt):
            publish_revision(dict_dir, project, [])
    finally:
        rev.os.replace = real_replace
    assert _current_active(project) is None
    assert list(project.revisions_dir.glob(".tmp-*"))  # tam con lai
    gc_orphan_revisions(project)
    assert not list(project.revisions_dir.glob(".tmp-*"))
    assert not list(project.revisions_dir.iterdir())  # khong con gi


def test_crash_after_rename_before_commit_is_orphan(tmp_path, monkeypatch):
    """Crash DUNG giua rename va transaction (activate_revision chua chay):
    bundle rename xong nhung khong co row DB = orphan vo hai — active khong
    doi, GC xoa bundle do."""
    import zhvi.state as st_mod

    def boom(self, *args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(st_mod.State, "activate_revision", boom)
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    with pytest.raises(KeyboardInterrupt):
        publish_revision(dict_dir, project, [])
    st = State(project.db_path)
    try:
        orphan_ids = [r[0] for r in st.conn.execute("SELECT id FROM dictionary_revisions")]
    finally:
        st.close()
    assert orphan_ids == []  # chua co row nao — crash truoc transaction
    assert _current_active(project) is None
    assert list(project.revisions_dir.glob("*"))  # bundle da rename vao <id>/
    gc_orphan_revisions(project)
    assert not list(project.revisions_dir.iterdir())


def test_gc_keeps_published_bundle(tmp_path):
    """GC giu nguyen bundle co row ready/active; chi xoa orphan + dir tam."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    r1 = publish_revision(dict_dir, project, [])
    (project.revisions_dir / ".tmp-deadbeef").mkdir()
    orphan = build_revision(dict_dir, project, [AutoEntry(source="玄女", target="Huyền Nữ")])
    gc_orphan_revisions(project)
    assert (project.revisions_dir / r1.revision_id).is_dir()
    assert not orphan.path.exists()
    assert not list(project.revisions_dir.glob(".tmp-*"))


def test_manifest_recorded_in_db(tmp_path):
    """Row dictionary_revisions luu manifest + bundle path de reproduce (2.3)."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    r1 = publish_revision(dict_dir, project, [])
    st = State(project.db_path)
    try:
        row = st.conn.execute(
            "SELECT manifest_json, bundle_path FROM dictionary_revisions WHERE id=?",
            (r1.revision_id,),
        ).fetchone()
        assert row is not None
        manifest = json.loads(row[0])
        assert manifest["format"] == "zhvi-revision-1"
        assert Path(row[1]) == project.revisions_dir / r1.revision_id
    finally:
        st.close()


def test_publish_idempotent_same_revision(tmp_path):
    """Publish lai cung noi dung (cung id): active giu nguyen, bundle active
    KHONG bi materialize lai (short-circuit reuse — khong cua so rmtree)."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    r1 = publish_revision(dict_dir, project, [])
    inode_before = (project.revisions_dir / r1.revision_id / "dictionary.bin").stat().st_ino
    r2 = publish_revision(dict_dir, project, [], expected_active=r1.revision_id)
    assert r2.revision_id == r1.revision_id
    assert _current_active(project) == r1.revision_id
    # bundle nguyen ven — khong xoa/ghi lai
    for name in ("manifest.json", "entries.tsv", "patterns.jsonl", "dictionary.bin"):
        assert (project.revisions_dir / r1.revision_id / name).is_file()
    assert (project.revisions_dir / r1.revision_id / "dictionary.bin").stat().st_ino == inode_before


def test_cli_dict_gc(tmp_path):
    """CLI `zhvi dict gc -p`: don dir tam + bundle orphan, giu bundle active."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    r1 = publish_revision(dict_dir, project, [])
    (project.revisions_dir / ".tmp-deadbeef").mkdir()

    result = CliRunner().invoke(app, ["dict", "gc", "--project", str(project.root)])
    assert result.exit_code == 0, result.output
    assert (project.revisions_dir / r1.revision_id).is_dir()
    assert not list(project.revisions_dir.glob(".tmp-*"))
