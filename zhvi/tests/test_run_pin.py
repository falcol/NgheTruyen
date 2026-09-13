"""Tests cho run pin revision (story 2.3, SPEC CAP-2/AD-3/AD-11).

Run freeze dictionary_revision_id luc tao; loader chi nap bundle da pin
(dictionary.bin, hash verify); doi file tu dien/projection giua chang khong
lam thay noi dung run dang dich hoac run resume; run moi chi pin active
revision; run lich su doc duoc bundle superseded de reproduce.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

import zhvi.pipeline as pl
from zhvi.pipeline import PipelineResult, TranslateRequest, translate_project
from zhvi.project import create_project
from zhvi.revision import (
    AutoEntry,
    ensure_active_revision,
    load_revision_dictionary,
    publish_revision,
)
from zhvi.state import State

SRC = "第一章\n\n凌天看着前方。\n\n青龙从天而降。\n"


def _mini_dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mini-dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "凌天=Lăng Thiên\n青龙=Thanh Long\n看着=nhìn về phía trước\n"
        "前方=phía trước\n从天而降=rơi từ trời xuống\n第一章=Chương 1\n",
        encoding="utf-8",
    )
    return d


def _translate(project_dir: Path, src: Path, out: Path, dict_dir: Path) -> PipelineResult:
    p = create_project(project_dir)
    return translate_project(
        p, TranslateRequest(source=src, output=out, dict_dir=str(dict_dir))
    )


def test_translate_pins_active_revision(tmp_path):
    """Run moi ghi dictionary_revision_id = active revision; bundle ton tai."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    res = _translate(tmp_path / "proj", src, tmp_path / "out.txt", dict_dir)
    assert res.exit_code == 0

    st = State(project.db_path)
    try:
        active = st.active_revision_id("book", project.book_id)
        run = st.get_run(res.run_id)
    finally:
        st.close()
    assert active is not None
    assert run.dictionary_revision_id == active
    assert (project.revisions_dir / active / "dictionary.bin").is_file()


def test_resume_pins_old_bundle_after_dict_change(tmp_path, monkeypatch):
    """Run bi gian doan, file tu dien doi, resume: van pin revision cu —
    output khop clean run dich voi tu dien CU (AD-3)."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")

    # clean run truoc khi doi dict (dung revision dau)
    out_clean = tmp_path / "clean.txt"
    assert _translate(tmp_path / "proj-clean", src, out_clean, dict_dir).exit_code == 0
    clean_sha = hashlib.sha256(out_clean.read_bytes()).hexdigest()

    real_vp_plan = pl.vp_plan
    calls = {"n": 0}

    def flaky_vp_plan(dic, text, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyboardInterrupt
        return real_vp_plan(dic, text, **kw)

    monkeypatch.setattr(pl, "vp_plan", flaky_vp_plan)
    res_i = _translate(tmp_path / "proj-i", src, tmp_path / "i.txt", dict_dir)
    assert res_i.exit_code == 130

    # doi file tu dien GIUA chang — revision active van la cu
    (dict_dir / "Custom.txt").write_text("看着=nhin\n", encoding="utf-8")

    monkeypatch.setattr(pl, "vp_plan", real_vp_plan)
    out_i = tmp_path / "i.txt"
    res_r = _translate(tmp_path / "proj-i", src, out_i, dict_dir)
    assert res_r.exit_code == 0
    assert res_r.run_id == res_i.run_id  # resume cung run
    assert hashlib.sha256(out_i.read_bytes()).hexdigest() == clean_sha


def test_new_active_revision_new_run_retranslates(tmp_path):
    """Publish revision moi (entry moi) -> run moi pin revision moi, block
    cache cu khong hit (cache key gom revision — AD-11)."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    out1 = tmp_path / "v1.txt"
    r1 = _translate(tmp_path / "proj", src, out1, dict_dir)
    assert r1.exit_code == 0

    project = create_project(tmp_path / "proj")
    st = State(project.db_path)
    try:
        old_active = st.active_revision_id("book", project.book_id)
    finally:
        st.close()
    # entry moi thay doi target cua tu co trong source
    (dict_dir / "Custom.txt").write_text("青龙=Thanh Long Ngân\n", encoding="utf-8")
    publish_revision(dict_dir, project, [], expected_active=old_active)

    out2 = tmp_path / "v2.txt"
    r2 = _translate(tmp_path / "proj", src, out2, dict_dir)
    assert r2.exit_code == 0
    assert r2.run_id != r1.run_id
    assert "Thanh Long Ngân" in out2.read_text(encoding="utf-8")
    assert "Thanh Long Ngân" not in out1.read_text(encoding="utf-8")


def test_load_superseded_bundle_for_reproduce(tmp_path):
    """Bundle superseded van doc duoc de reproduce run lich su (CAP-2)."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    p1 = publish_revision(dict_dir, project, [])
    p2 = publish_revision(
        dict_dir, project, [AutoEntry(source="玄女", target="Huyền Nữ")],
        expected_active=p1.revision_id,
    )
    assert p1.revision_id != p2.revision_id

    st = State(project.db_path)
    try:
        status1 = st.conn.execute(
            "SELECT status FROM dictionary_revisions WHERE id=?", (p1.revision_id,)
        ).fetchone()[0]
    finally:
        st.close()
    assert status1 == "superseded"

    dic = load_revision_dictionary(project, p1.revision_id)
    node = dic.root
    for ch in "凌天":
        node = node.children[ch]
    assert any(t == "Lăng Thiên" for t, _p, _pol in node.entries)
    # entry cua revision 2 khong co trong bundle 1 — walk tu root
    node2 = dic.root
    for ch in "玄女":
        node2 = node2.children.get(ch)
        if node2 is None:
            break
    assert node2 is None or "Huyền Nữ" not in [t for t, _p, _pol in node2.entries]


def test_bundle_corruption_detected(tmp_path):
    """Manifest hash khong khop revision id = corruption — tu choi nap."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    r1 = publish_revision(dict_dir, project, [])
    manifest_path = project.revisions_dir / r1.revision_id / "manifest.json"
    manifest_path.write_text("{}\n", encoding="utf-8")  # hash sai
    with pytest.raises(RuntimeError, match="manifest"):
        load_revision_dictionary(project, r1.revision_id)


def test_load_revoked_bundle_for_reproduce(tmp_path):
    """Bundle revoked van doc duoc de reproduce run lich su (AC 2.3)."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    p1 = publish_revision(dict_dir, project, [])
    p2 = publish_revision(dict_dir, project, [], expected_active=p1.revision_id)
    st = State(project.db_path)
    try:
        # revoke chua co API (story 2.5) — mo phong trang thai trong DB
        st.conn.execute(
            "UPDATE dictionary_revisions SET status='revoked' WHERE id=?", (p2.revision_id,)
        )
        st.conn.commit()
    finally:
        st.close()
    dic = load_revision_dictionary(project, p2.revision_id)
    assert dic.fingerprint == p2.revision_id


def test_cache_key_includes_renderer_version(tmp_path, monkeypatch):
    """AD-11: cache key gom renderer version — bump renderer lam mat cache cu."""
    from zhvi.config import Config
    from zhvi.pipeline import block_cache_key

    cfg = Config()
    k1 = block_cache_key("src-hash-x", "rev-1", cfg)
    monkeypatch.setattr("zhvi.pipeline.RENDERER_VERSION", "zhvi-renderer-test-bump")
    k2 = block_cache_key("src-hash-x", "rev-1", cfg)
    assert k1 != k2
    monkeypatch.setattr("zhvi.pipeline.RENDERER_VERSION", "zhvi-renderer-8")
    assert block_cache_key("src-hash-x", "rev-1", cfg) == k1


def test_resume_same_run_when_glossary_changes(tmp_path, monkeypatch):
    """AC 2.3: doi glossary.manual.tsv giua chang — run van resume (cung
    run_id, pin revision cu), khong fork run moi (revision chua doi)."""
    dict_dir = _mini_dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    out_clean = tmp_path / "clean.txt"
    assert _translate(tmp_path / "proj-clean", src, out_clean, dict_dir).exit_code == 0
    clean_sha = hashlib.sha256(out_clean.read_bytes()).hexdigest()

    real_vp_plan = pl.vp_plan
    calls = {"n": 0}

    def flaky_vp_plan(dic, text, **kw):
        calls["n"] += 1
        if calls["n"] > 1:
            raise KeyboardInterrupt
        return real_vp_plan(dic, text, **kw)

    monkeypatch.setattr(pl, "vp_plan", flaky_vp_plan)
    res_i = _translate(tmp_path / "proj-g", src, tmp_path / "g.txt", dict_dir)
    assert res_i.exit_code == 130

    # doi glossary manual giua chang
    proj_g = tmp_path / "proj-g"
    (proj_g / "glossary.manual.tsv").write_text(
        "第一章=Chương Một\n", encoding="utf-8"
    )

    monkeypatch.setattr(pl, "vp_plan", real_vp_plan)
    out_g = tmp_path / "g.txt"
    res_r = _translate(proj_g, src, out_g, dict_dir)
    assert res_r.exit_code == 0
    assert res_r.run_id == res_i.run_id  # resume — khong fork
    assert hashlib.sha256(out_g.read_bytes()).hexdigest() == clean_sha


def test_ensure_active_revision_bootstrap(tmp_path):
    """Chua co active -> ensure publish bootstrap; lan sau tra nguyen id."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    first = ensure_active_revision(dict_dir, project)
    second = ensure_active_revision(dict_dir, project)
    assert first == second
    st = State(project.db_path)
    try:
        assert st.active_revision_id("book", project.book_id) == first
    finally:
        st.close()
