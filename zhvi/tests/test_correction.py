"""Tests cho diff/rollback/affected-block rerun (story 2.5, SPEC CAP-5/AD-12).

diff hai revision: entry khac nhau + affected blocks; rollback la CAS active
pointer ve revision an toan (khong sua bundle cu, event append-only);
correction flow: sua glossary.manual.tsv -> revision moi -> fork run -> dich
lai DUNG tap block chua key, block khong chua key giu nguyen.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from zhvi.cli import app
from zhvi.correction import (
    affected_block_ids,
    diff_revisions,
    rollback_revision,
)
from zhvi.document import parse_document
from zhvi.pipeline import TranslateRequest, translate_project
from zhvi.project import create_project
from zhvi.revision import AutoEntry, publish_revision
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


def _publish(tmp_path: Path, autos=None, glossary: str | None = None):
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    if glossary is not None:
        project.manual_glossary.write_text(glossary, encoding="utf-8")
    result = publish_revision(dict_dir, project, autos or [])
    return dict_dir, project, result


# ---- diff ----


def test_diff_revisions_entries_and_keys(tmp_path):
    """diff REV_A REV_B: entry them/doi + affected keys tu entries.tsv."""
    _dict_dir, project, r1 = _publish(
        tmp_path, autos=[AutoEntry(source="天煞", target="Thiên Sát")]
    )
    # sua glossary (layer manual:book doi) + auto entry bien mat
    project.manual_glossary.write_text("玄女=Huyền Nữ\n", encoding="utf-8")
    r2 = publish_revision(_dict_dir, project, [], expected_active=r1.revision_id)
    diff = diff_revisions(project, r1.revision_id, r2.revision_id)
    assert "玄女" in diff["added"]  # entry moi trong manual:book
    assert "天煞" in diff["removed"]  # auto entry cua r1 bien mat
    assert set(diff["affected_keys"]) >= {"玄女", "天煞"}


def test_affected_block_ids_by_key():
    """Block chua key moi affected; block khong chua key — khong."""
    from zhvi.export import node_block_id

    text = "第一章\n\n青龙从天而降。\n\n凌天看着前方。\n"
    doc = parse_document(text)
    by_id = {node_block_id(n): n.content for n in doc.translatable_nodes()}
    affected = affected_block_ids(doc, {"青龙"})
    assert affected == sorted(bid for bid, content in by_id.items() if "青龙" in content)
    assert affected_block_ids(doc, {"không_có"}) == []


# ---- rollback ----


def test_rollback_cas_active_back(tmp_path):
    """Rollback: CAS active ve revision an toan; revision cu khong bi sua
    (bundle hash khong doi); event append-only duoc ghi."""
    _dict_dir, project, r1 = _publish(tmp_path)
    project.manual_glossary.write_text("玄女=Huyền Nữ\n", encoding="utf-8")
    r2 = publish_revision(_dict_dir, project, [], expected_active=r1.revision_id)

    rollback_revision(project, r1.revision_id, expected_active=r2.revision_id)

    st = State(project.db_path)
    try:
        assert st.active_revision_id("book", project.book_id) == r1.revision_id
        status1 = st.conn.execute(
            "SELECT status FROM dictionary_revisions WHERE id=?", (r1.revision_id,)
        ).fetchone()[0]
        events = st.conn.execute(
            "SELECT action, before_json, after_json FROM feedback_events"
        ).fetchall()
    finally:
        st.close()
    assert status1 == "active"
    assert any(e[0] == "dict_rollback" and r2.revision_id in e[1] and r1.revision_id in e[2]
               for e in events)
    # bundle revision cu nguyen ven
    import hashlib

    m = project.revisions_dir / r2.revision_id / "manifest.json"
    assert hashlib.sha256(m.read_bytes()).hexdigest() == r2.revision_id


def test_rollback_stale_expected_active(tmp_path):
    """expected_active sai -> StaleActiveError, active khong doi."""
    from zhvi.revision import StaleActiveError

    _dict_dir, project, r1 = _publish(tmp_path)
    with pytest.raises(StaleActiveError):
        rollback_revision(project, r1.revision_id, expected_active="khac")


# ---- correction flow (end-to-end) ----


def test_correction_reruns_only_affected_blocks(tmp_path):
    """Sua glossary entry -> translate lai: run moi fork, block chua key dich
    lai voi target moi; block KHONG chua key giu nguyen final_text."""
    dict_dir = _mini_dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    project.manual_glossary.write_text("青龙=Thanh Long Ngân\n", encoding="utf-8")
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    out1 = tmp_path / "v1.txt"
    res1 = translate_project(
        project, TranslateRequest(source=src, output=out1, dict_dir=str(dict_dir))
    )
    assert res1.exit_code == 0

    st = State(project.db_path)
    try:
        run1_id = res1.run_id
        old_blocks = st.committed_blocks(run1_id)
    finally:
        st.close()
    assert "Thanh Long Ngân" in out1.read_text(encoding="utf-8")

    # correction: doi target cua key 青龙 — refresh revision (story 2.5)
    project.manual_glossary.write_text("青龙=Thanh Long Tinh\n", encoding="utf-8")
    out2 = tmp_path / "v2.txt"
    res2 = translate_project(
        project, TranslateRequest(source=src, output=out2, dict_dir=str(dict_dir),
                                  refresh_revision=True)
    )
    assert res2.exit_code == 0
    assert res2.run_id != run1_id  # fork run moi (revision moi)

    st = State(project.db_path)
    try:
        new_blocks = st.committed_blocks(res2.run_id)
    finally:
        st.close()

    text2 = out2.read_text(encoding="utf-8")
    assert "Thanh Long Tinh" in text2  # block chua key dich lai
    # block khong chua 青龙 giu nguyen final_text
    assert "Lăng Thiên" in text2
    unaffected = [
        bid for bid, blk in new_blocks.items() if "青龙" not in old_blocks[bid]["final_text"]
        and bid in old_blocks and "Thanh Long" not in (old_blocks[bid]["final_text"] or "")
    ]
    assert unaffected, "phai co block khong chua key"
    for bid in unaffected:
        assert new_blocks[bid]["final_text"] == old_blocks[bid]["final_text"]


def test_cli_dict_diff_and_rollback(tmp_path):
    """CLI dict diff REV_A REV_B + dict rollback REV hoat dong."""
    _dict_dir, project, r1 = _publish(tmp_path)
    project.manual_glossary.write_text("玄女=Huyền Nữ\n", encoding="utf-8")
    r2 = publish_revision(_dict_dir, project, [], expected_active=r1.revision_id)

    runner = CliRunner()
    res_diff = runner.invoke(
        app, ["dict", "diff", r1.revision_id, r2.revision_id, "--project", str(project.root)]
    )
    assert res_diff.exit_code == 0, res_diff.output
    payload = json.loads(res_diff.output)
    assert "added" in payload and "affected_keys" in payload
    assert "affected_blocks" in payload  # AC 2.5: diff hien ca affected blocks

    res_rb = runner.invoke(
        app, ["dict", "rollback", r1.revision_id, "--project", str(project.root)]
    )
    assert res_rb.exit_code == 0, res_rb.output
