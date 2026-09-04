"""Tests cho projection + reconciler + ownership guard (story 2.4, SPEC AD-8/AD-15 buoc 10).

glossary.auto.tsv chi la projection dung lai tu active pointer; reconciler
kiem tra tinh khop luc startup; bundle thieu/hash sai la fatal corruption;
moi duong ghi may vao file human-owned bi chan.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

import zhvi.pipeline as pl
from zhvi.export import atomic_write
from zhvi.pipeline import TranslateRequest
from zhvi.project import create_project
from zhvi.projection import (
    OwnershipError,
    assert_machine_writable,
    reconcile_project,
)
from zhvi.revision import AutoEntry, publish_revision


def _mini_dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mini-dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text("凌天=Lăng Thiên\n", encoding="utf-8")
    return d


def _publish(tmp_path: Path, autos=None):
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    result = publish_revision(dict_dir, project, autos or [])
    return dict_dir, project, result


def test_projection_materialized_after_publish(tmp_path):
    """Publish commit xong -> glossary.auto.tsv duoc dung tu active pointer,
    chi chua auto entries (source=target)."""
    autos = [AutoEntry(source="天煞", target="Thiên Sát")]
    _dict_dir, project, result = _publish(tmp_path, autos)
    proj_file = project.root / "glossary.auto.tsv"
    assert proj_file.is_file()
    content = proj_file.read_text(encoding="utf-8")
    assert "天煞=Thiên Sát" in content
    # manual/base khong lo vao projection auto
    assert "凌天" not in content


def test_reconciler_rebuilds_stale_projection(tmp_path):
    """Projection cu/sua sai (crash truoc khi dung xong) -> reconciler dung lai."""
    autos = [AutoEntry(source="天煞", target="Thiên Sát")]
    _dict_dir, project, result = _publish(tmp_path, autos)
    proj_file = project.root / "glossary.auto.tsv"
    good = proj_file.read_text(encoding="utf-8")
    proj_file.write_text("rac=old content\n", encoding="utf-8")  # gia lap projection cu
    reconcile_project(project)
    assert proj_file.read_text(encoding="utf-8") == good
    # projection bi xoa -> cung duoc dung lai
    proj_file.unlink()
    reconcile_project(project)
    assert proj_file.read_text(encoding="utf-8") == good


def test_reconciler_noop_without_active(tmp_path):
    """Project chua co active revision — reconciler khong lam gi, khong loi."""
    project = create_project(tmp_path / "proj")
    reconcile_project(project)  # khong raise
    assert not (project.root / "glossary.auto.tsv").exists()


def test_reconciler_fatal_missing_bundle(tmp_path):
    """Bundle thieu (active row ton tai nhung dir mat) = fatal corruption."""
    _dict_dir, project, result = _publish(tmp_path)
    shutil.rmtree(project.revisions_dir / result.revision_id)
    with pytest.raises(RuntimeError, match="corrupt|thieu|bundle"):
        reconcile_project(project)


def test_reconciler_fatal_hash_mismatch(tmp_path):
    """Bundle hash sai = fatal corruption voi thong bao ro."""
    _dict_dir, project, result = _publish(tmp_path)
    (project.revisions_dir / result.revision_id / "manifest.json").write_text(
        "{}\n", encoding="utf-8"
    )
    with pytest.raises(RuntimeError, match="corrupt|hash"):
        reconcile_project(project)


def test_translate_startup_runs_reconciler(tmp_path, monkeypatch):
    """translate_project goi reconciler luc startup — projection cu tu dong
    duoc dung lai truoc khi dich."""
    monkeypatch.delenv("ZHVI_GLOBAL_GLOSSARY", raising=False)
    dict_dir, project, result = _publish(
        tmp_path, [AutoEntry(source="天煞", target="Thiên Sát")]
    )
    # isolation may: global glossary that cua may khong tham gia revision
    toml = project.root / "zhvi.toml"
    toml.write_text(
        toml.read_text(encoding="utf-8").replace(
            'global_glossary = "~/.config/zhvi/glossary.manual.tsv"',
            'global_glossary = ""',
        ),
        encoding="utf-8",
    )
    src = tmp_path / "truyen.txt"
    src.write_text("第一章\n\n天煞从天而降。\n", encoding="utf-8")
    # chay translate lan 1 (projection ok)
    res1 = pl.translate_project(
        project, TranslateRequest(source=src, output=tmp_path / "out.txt", dict_dir=str(dict_dir))
    )
    assert res1.exit_code == 0
    # hong projection
    (project.root / "glossary.auto.tsv").write_text("x=y\n", encoding="utf-8")
    res2 = pl.translate_project(
        project, TranslateRequest(source=src, output=tmp_path / "out.txt", dict_dir=str(dict_dir))
    )
    assert res2.exit_code == 0  # noop path — reconciler da chay, khong fatal
    assert "天煞=Thiên Sát" in (project.root / "glossary.auto.tsv").read_text(encoding="utf-8")


def test_guard_blocks_human_owned_files(tmp_path):
    """Moi duong ghi may vao file human-owned bi chan (AD-5): Custom.txt,
    QualityOverrides.txt, VietPhrase_*.txt, glossary.manual.tsv, .manual.*"""
    blocked = [
        "Custom.txt",
        "QualityOverrides.txt",
        "VietPhrase_1.txt",
        "VietPhrase_2.txt",
        "glossary.manual.tsv",
        "dict.manual.backup",
        "something.manual.tsv",
    ]
    for name in blocked:
        with pytest.raises(OwnershipError):
            assert_machine_writable(tmp_path / name)
    # may ghi duoc vao file machine-owned
    assert_machine_writable(tmp_path / "glossary.auto.tsv")
    assert_machine_writable(tmp_path / "AutoVietPhrase.txt")
    assert_machine_writable(tmp_path / ".zhvi" / "revisions" / "abc" / "manifest.json")


def test_atomic_write_enforces_guard(tmp_path):
    """export.atomic_write (writer chung) cung chay guard."""
    with pytest.raises(OwnershipError):
        atomic_write(tmp_path / "Custom.txt", b"x=1\n")


def test_bundle_files_constant_in_sync():
    """projection.BUNDLE_FILES phai dong bo voi revision.BUNDLE_FILES (hai ban
    copy tach de tranh import cheo — drift phai bi bat)."""
    from zhvi import projection, revision

    assert projection.BUNDLE_FILES == revision.BUNDLE_FILES
