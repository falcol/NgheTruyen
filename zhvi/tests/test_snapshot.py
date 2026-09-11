"""Tests cho snapshot.py + project.py (thiet ke muc 5/6/29)."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

import pytest

from zhvi.project import (
    Project,
    ProjectError,
    create_project,
    default_output_path,
    open_project,
    project_lock,
    workspace_for,
)
from zhvi.snapshot import DecodeError, SourceRevision, import_snapshot


@pytest.fixture()
def project(tmp_path: Path):
    return create_project(tmp_path / "book")


def make_source(tmp_path: Path, text: str = "第一章\n\n正文。\n") -> Path:
    src = tmp_path / "truyen.txt"
    src.write_text(text, encoding="utf-8")
    return src


def test_layout_created(tmp_path):
    p = create_project(tmp_path / "book2")
    assert p.db_path.parent.exists()
    for d in (p.sources_dir, p.dictionaries_dir, p.runs_dir, p.logs_dir, p.cache_dir, p.locks_dir, p.dist_dir):
        assert d.is_dir()
    assert (p.root / "zhvi.toml").is_file()
    assert p.manual_glossary.is_file()


def test_snapshot_hash_and_path(project, tmp_path):
    src = make_source(tmp_path)
    rev = import_snapshot(project, src)
    expected = hashlib.sha256(src.read_bytes()).hexdigest()
    assert rev.id == expected
    assert Path(rev.snapshot_path).read_bytes() == src.read_bytes()
    assert rev.byte_size == src.stat().st_size


def test_snapshot_idempotent(project, tmp_path):
    src = make_source(tmp_path)
    r1 = import_snapshot(project, src)
    r2 = import_snapshot(project, src)
    assert r1.id == r2.id
    assert list(project.sources_dir.glob("*.txt")) == [Path(r1.snapshot_path)]


def test_snapshot_detects_change(project, tmp_path):
    src = make_source(tmp_path)
    r1 = import_snapshot(project, src)
    src.write_text("第一章\n\n正文 sửa rồi。\n", encoding="utf-8")
    r2 = import_snapshot(project, src)
    assert r1.id != r2.id
    # ca hai snapshot bat bien cung ton tai
    assert Path(r1.snapshot_path).exists() and Path(r2.snapshot_path).exists()


def test_decode_error_reports_offset(project, tmp_path):
    src = tmp_path / "bad.txt"
    src.write_bytes(b"abc \xff\xfe xyz")
    with pytest.raises(DecodeError) as ei:
        import_snapshot(project, src)
    assert ei.value.byte_offset == 4


def test_gb18030_explicit_encoding(project, tmp_path):
    src = tmp_path / "gbk.txt"
    src.write_bytes("第一章 正文。".encode("gb18030"))
    rev = import_snapshot(project, src, encoding="gb18030")
    assert rev.encoding == "gb18030"


def test_missing_source_file(project, tmp_path):
    from zhvi.snapshot import SnapshotError

    with pytest.raises(SnapshotError):
        import_snapshot(project, tmp_path / "khong-ton-tai.txt")


def test_open_project_requires_state_dir(tmp_path):
    with pytest.raises(ProjectError):
        open_project(tmp_path / "rong")


def test_workspace_for(tmp_path, monkeypatch):
    monkeypatch.setenv("ZHVI_PROJECT", str(tmp_path / "ws"))
    ws = workspace_for(Path("/x/truyen.txt"))
    assert ws == (tmp_path / "ws").resolve()
    assert workspace_for(Path("/y/other.txt")) == ws


@pytest.mark.keep_default_workspace
def test_default_workspace_is_package_dir(monkeypatch):
    monkeypatch.delenv("ZHVI_PROJECT", raising=False)
    from zhvi.project import default_workspace

    ws = default_workspace()
    assert ws.name == "workspace"
    assert (ws.parent / "pyproject.toml").is_file()
    assert ws.parent.name == "zhvi"


def test_default_output_path_uses_source_stem(tmp_path):
    p = Project(tmp_path)
    assert default_output_path(p, Path("chap1_raw.txt")).name == "chap1_raw.vi.txt"
    assert default_output_path(p, None).name == "book.vi.txt"


def test_project_lock_blocks_second_holder(project):
    # flock tranh chap theo open file description — thu phan cap fd thu 2 cung process.
    import fcntl

    path = project.locks_dir / "translate.lock"
    with project_lock(project):
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o644)
        try:
            with pytest.raises(BlockingIOError):
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:
            os.close(fd)


def test_lock_released_after_context(project):
    with project_lock(project):
        pass
    with project_lock(project):  # khong deadlock
        pass
