"""Tests cho ReviewStore (review.py) — route/reasons tu DB, khong tu qa_json.

Story epic 1 review finding: ReviewEntry doc qa.get("route"/"reasons"/"fallback")
— pipeline khong ghi cac key do vao qa (route/reasons nam o bang
route_decisions) nen luon tra default. Fix: doc tu route_decisions.
"""
from __future__ import annotations

from pathlib import Path

from zhvi.project import create_project
from zhvi.review import ReviewStore
from zhvi.state import State

SRC = "第一章\n\n青龙从天而降。\n"


def _project_with_reviewable_block(tmp_path: Path) -> Path:
    """Project co 1 block NEEDS_REVIEW: stage_block voi qa.invariant_errors
    + route/reasons ghi vao route_decisions nhu pipeline that."""
    project = create_project(tmp_path / "proj")
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    st = State(project.db_path)
    st.upsert_source_revision("rev1", "hash1", "utf-8", len(SRC), str(src))
    st.resume_or_create(
        run_id="run1",
        fingerprint="fp1",
        source_revision_id="rev1",
        dictionary_revision_id="d1",
        resolved_config={},
    )
    st.stage_block(
        run_id="run1",
        block_id="c0b2",
        chapter_ordinal=0,
        block_ordinal=0,
        source_start=0,
        source_end=7,
        source_hash="sh1",
        final_text="Thanh Long",
        qa={"unknown_spans": 0, "invariant_errors": ["CJK_LEFT"]},
        route="VIETPHRASE",
        reasons=["X1"],
        features={},
        router_version="none",
        attempt={"id": "a1", "engine": "vietphrase-lattice", "input_hash": "sh1",
                 "status": "ok"},
    )
    st.close()
    return project.root


def test_review_entry_route_and_reasons_from_db(tmp_path):
    """entry.route/entry.reasons phai lay tu route_decisions, khong phai
    qa_json key khong ton tai (luon default)."""
    project_root = _project_with_reviewable_block(tmp_path)
    rs = ReviewStore(project_root)
    entries = rs.list_review()
    assert len(entries) == 1
    e = entries[0]
    assert e.route == "VIETPHRASE"
    assert e.reasons == ["X1"]  # tu route_decisions.reasons_json
    assert e.invariant_errors == ["CJK_LEFT"]
    assert e.source == "青龙从天而降。"  # map qua block_id tu document


def test_review_json_no_fallback_field(tmp_path):
    """VP-only: khong con engine fallback — entry/json khong con field fallback."""
    project_root = _project_with_reviewable_block(tmp_path)
    rs = ReviewStore(project_root)
    entries = rs.list_review()
    assert len(entries) == 1
    assert "fallback" not in entries[0].to_json()
