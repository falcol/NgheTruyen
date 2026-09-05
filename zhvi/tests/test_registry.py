"""Tests cho registry.py: realpath identity, writer lock, book_id stable (story 4.1)."""
from __future__ import annotations

import os
import shutil
import string
from pathlib import Path

import pytest

from zhvi.learning.discovery import run_discovery
from zhvi.project import Project, create_project
from zhvi.registry import (
    RegistryError,
    RegistryState,
    registry_lock,
    resolve_registry_dir,
)
from zhvi.revision import ensure_active_revision, load_revision_dictionary
from zhvi.snapshot import import_snapshot
from zhvi.state import State

SRC = "第一章\n\n天宗。\n\n第二章\n\n天宗玄天。\n"


def _dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "天=thiên\n", encoding="utf-8"
    )
    return d


# ---- AC 1: realpath resolve — moi resolved root dung mot registry ----


def test_resolve_registry_dir_uses_realpath(tmp_path):
    real = _dict_dir(tmp_path)
    link = tmp_path / "dicts-link"
    os.symlink(real, link)
    assert resolve_registry_dir(link) == resolve_registry_dir(real)
    assert resolve_registry_dir(real) == real.resolve() / ".zhvi-registry"


def test_registry_state_open_same_file_via_symlink(tmp_path):
    real = _dict_dir(tmp_path)
    link = tmp_path / "dicts-link"
    os.symlink(real, link)
    st_a = RegistryState(resolve_registry_dir(real))
    try:
        st_b = RegistryState(resolve_registry_dir(link))
    finally:
        st_a.close()
    try:
        version = st_b.conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        assert version is not None and int(version[0]) == 1
    finally:
        st_b.close()


def test_registry_state_idempotent_reopen(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    st = RegistryState(reg)
    st.close()
    st2 = RegistryState(reg)
    try:
        version = st2.conn.execute(
            "SELECT value FROM meta WHERE key='schema_version'"
        ).fetchone()
        assert int(version[0]) == 1
    finally:
        st2.close()


def test_registry_lazy_init_and_init_does_not_touch_registry(tmp_path):
    dict_dir = _dict_dir(tmp_path)
    # zhvi init la book scope — khong tao registry tai dictionary root.
    create_project(tmp_path / "proj")
    assert not resolve_registry_dir(dict_dir).exists()
    # Registry khoi tao LAZY lan dau RegistryState mo (mkdir + schema).
    st = RegistryState(resolve_registry_dir(dict_dir))
    try:
        assert (resolve_registry_dir(dict_dir) / "state.sqlite3").is_file()
    finally:
        st.close()


def test_registry_state_rejects_newer_schema(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    st = RegistryState(reg)
    st.conn.execute(
        "UPDATE meta SET value='2' WHERE key='schema_version'"
    )
    st.conn.commit()
    st.close()
    # DB moi hon binary -> RegistryError (chuan bi cho 4.2 bump version).
    with pytest.raises(RegistryError):
        RegistryState(reg)


# ---- AC 1/3: writer lock ----


def test_registry_lock_dedupe_across_symlink(tmp_path):
    real = _dict_dir(tmp_path)
    link = tmp_path / "dicts-link"
    os.symlink(real, link)
    with registry_lock(resolve_registry_dir(real)):
        # Layout spec (data-model): lock tai <registry>/locks/registry.lock.
        assert (resolve_registry_dir(real) / "locks" / "registry.lock").is_file()
        with pytest.raises(RegistryError) as exc:
            with registry_lock(resolve_registry_dir(link)):
                pass
    # Thong bao ro: path lock file day du + pid holder (task 2.2).
    assert "registry.lock" in str(exc.value)
    assert "pid=" in str(exc.value)


def test_registry_lock_conflict_two_fds_same_process(tmp_path):
    """flock gan open file description — 2 fd rieng cung process van conflict."""
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    with registry_lock(reg):
        with pytest.raises(RegistryError):
            with registry_lock(reg):
                pass


def test_registry_lock_released_after_exit(tmp_path):
    reg = resolve_registry_dir(_dict_dir(tmp_path))
    with registry_lock(reg):
        pass
    # Lock nha ra: acquire lan 2 thanh cong.
    with registry_lock(reg):
        pass


# ---- AC 2: book_id stable, copy giu ID ----


def test_book_id_created_once_and_stable_on_reinit(tmp_path):
    project = create_project(tmp_path / "proj")
    first = project.book_id
    # book_id la uuid hex 32 ky tu (project.py: uuid.uuid4().hex).
    assert len(first) == 32 and all(c in string.hexdigits for c in first)
    # Re-init idempotent: khong doi ID.
    create_project(tmp_path / "proj")
    assert project.book_id == first


def test_book_id_survives_project_copy(tmp_path):
    project = create_project(tmp_path / "proj")
    copy_root = tmp_path / "proj-copy"
    shutil.copytree(tmp_path / "proj", copy_root)
    # Luong thuc te: copy xong chay lai init tren ban copy (duong 4.2 ingest).
    create_project(copy_root)
    copied = Project(copy_root)
    # Copy project giu cung ID — registry khong tinh la truyen doc lap.
    assert copied.book_id == project.book_id


# ---- AC 3: discovery khong giu registry lock ----


def test_discovery_runs_while_registry_lock_held(tmp_path):
    """Khoi global lock trong discovery la violation (data-model Concurrency).

    Giu registry lock bang process khac fd; discovery van chay binh thuong
    vi hoan toan book-local — khong cho/khong can registry lock.
    """
    dict_dir = _dict_dir(tmp_path)
    (dict_dir / "QualityOverrides.txt").write_text(
        "天宗=thiên tông\n玄天=huyền thiên\n第一章=Chương 1\n第二章=Chương 2\n",
        encoding="utf-8",
    )
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    rev = import_snapshot(project, src)
    st = State(project.db_path)
    try:
        st.upsert_source_revision(
            rev.id, rev.content_hash, rev.encoding, rev.byte_size, str(rev.snapshot_path)
        )
        drev = ensure_active_revision(dict_dir, project)
        dic = load_revision_dictionary(project, drev)
        # dict_dir la cung root voi registry — lock giu trong khi discovery chay.
        with registry_lock(resolve_registry_dir(dict_dir)):
            summary = run_discovery(
                st, source_revision=rev, dictionary=dic, dictionary_revision_id=drev
            )
        assert summary.source_revision_id == rev.id
    finally:
        st.close()
