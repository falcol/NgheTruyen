"""Tests cho learning/candidate.py + bang term_candidates mo rong (story 3.2)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from zhvi.learning.candidate import (
    MIN_OCCURRENCES,
    _normalize_target,
    build_candidates,
)
from zhvi.learning.discovery import run_discovery
from zhvi.project import create_project, open_project
from zhvi.revision import ensure_active_revision, load_revision_dictionary
from zhvi.snapshot import import_snapshot
from zhvi.state import CandidateRow, ObservationRow, State


@pytest.fixture()
def st(tmp_path):
    s = State(tmp_path / "state.sqlite3")
    yield s
    s.close()


def _cand_row(source: str, **over) -> CandidateRow:
    fields = {
        "id": f"id-{source}",
        "book_id": "book-1",
        "source": source,
        "proposed_target": "mục tiêu",
        "kind": "term",
        "status": "candidate",
        "provenance_json": '{"resolver": "lower_layer"}',
        "dictionary_revision_id": "drev1",
        "eligible_auto": 1,
    }
    fields.update(over)
    return CandidateRow(**fields)


def test_schema_v5_term_candidates_columns(st):
    cols = {r[1] for r in st.conn.execute("PRAGMA table_info(term_candidates)")}
    assert {"dictionary_revision_id", "eligible_auto"} <= cols
    version = st.conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()[0]
    # v5 = story 3.2 term_candidates mo rong; v6 = story 3.3 candidate_evidence.
    assert int(version) >= 5


def test_replace_candidates_replaces_per_book_and_drev(st):
    st.replace_candidates("book-1", "drev1", [_cand_row("玄天")])
    st.replace_candidates(
        "book-1", "drev1", [_cand_row("玄天"), _cand_row("紫霄", id="id-紫霄")]
    )
    rows = st.conn.execute(
        "SELECT source FROM term_candidates WHERE book_id='book-1' "
        "AND dictionary_revision_id='drev1' ORDER BY source"
    ).fetchall()
    assert [r[0] for r in rows] == ["玄天", "紫霄"]

    # Book khac hoac dict revision khac khong bi anh huong.
    st.replace_candidates(
        "book-1", "drev2", [_cand_row("天诀", dictionary_revision_id="drev2")]
    )
    count_drev1 = st.conn.execute(
        "SELECT COUNT(*) FROM term_candidates WHERE dictionary_revision_id='drev1'"
    ).fetchone()[0]
    assert count_drev1 == 2


def test_replace_candidates_atomic_on_bad_row(st):
    st.replace_candidates("book-1", "drev1", [_cand_row("玄天")])
    with pytest.raises(AttributeError):
        st.replace_candidates(
            "book-1", "drev1", [_cand_row("紫霄", id="id-紫霄"), "not-a-row"]
        )
    rows = st.conn.execute(
        "SELECT source FROM term_candidates WHERE dictionary_revision_id='drev1'"
    ).fetchall()
    assert [r[0] for r in rows] == ["玄天"]


# ---- build_candidates (Task 2+) ----

SRC = (
    "第一章\n\n"
    "李慕白看着前方。紫霄山高。未知语起。\n\n"
    "第二章\n\n"
    "李慕白运转玄天诀。紫霄山远。未知语灭。\n\n"
    "第三章\n\n"
    "李慕白望着紫霄山。未知语终。\n\n"
)


def _dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mini-dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "看着=nhìn về phía trước\n前方=phía trước\n运转=vận chuyển\n"
        "玄天=huyền thiên\n紫=tử\n霄=tiêu\n山=núi\n诀=quyết\n"
        "望着=nhìn về\n第一章=Chương 1\n第二章=Chương 2\n第三章=Chương 3\n",
        encoding="utf-8",
    )
    (d / "ChinesePhienAmWords.txt").write_text(
        "李=lý\n慕=mộ\n白=bạch\n", encoding="utf-8"
    )
    return d


def _learned(tmp_path, text: str = SRC):
    dict_dir = _dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(text, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    rev = import_snapshot(project, src)
    st = State(project.db_path)
    st.upsert_source_revision(
        rev.id, rev.content_hash, rev.encoding, rev.byte_size, str(rev.snapshot_path)
    )
    drev = ensure_active_revision(dict_dir, project)
    dic = load_revision_dictionary(project, drev)
    run_discovery(st, source_revision=rev, dictionary=dic, dictionary_revision_id=drev)
    summary = build_candidates(
        st,
        book_id=project.book_id,
        dictionary=dic,
        dictionary_revision_id=drev,
        source_revision_id=rev.id,
    )
    return st, summary, drev


def _cand(st, source: str) -> dict:
    cur = st.conn.execute(
        "SELECT * FROM term_candidates WHERE source=?", (source,)
    )
    row = cur.fetchone()
    assert row is not None, f"thieu candidate: {source}"
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def test_build_candidates_six_sources_or_unresolved(tmp_path):
    st, summary, _ = _learned(tmp_path)

    # AC 1: ten rieng co phien am Han-Viet tung ky tu + provenance nguon.
    name = _cand(st, "李慕白")
    assert name["status"] == "candidate"
    assert name["proposed_target"] == "lý mộ bạch"
    assert name["kind"] == "name"
    prov = json.loads(name["provenance_json"])
    assert prov["resolver"] == "phien_am"

    # AC 1 + 4: ghep longest-match entry con, moi entry con mot target.
    frag = _cand(st, "紫霄山")
    assert frag["status"] == "candidate"
    assert frag["proposed_target"] == "tử tiêu núi"
    prov_frag = json.loads(frag["provenance_json"])
    assert prov_frag["resolver"] == "compound"

    # AC 1: khong dung duoc target tu nguon nao -> unresolved, target rong.
    unk = _cand(st, "未知语")
    assert unk["status"] == "unresolved"
    assert unk["proposed_target"] == ""
    assert json.loads(unk["provenance_json"])["resolver"] is None


def test_build_candidates_skips_manual_conflict(tmp_path):
    st, _, drev = _learned(tmp_path)
    # Gan observation gia cho key da co manual entry (QualityOverrides =
    # GLOBAL_MANUAL) + tin hieu hoc: phai bi loai, khong tao candidate.
    # (replace_candidates tu xoa scope — khong can DELETE tay.)
    st.replace_observations(
        "rev-manual",
        [
            ObservationRow(
                id=f"id-manual-{i}",
                source_revision_id="rev-manual",
                dictionary_revision_id=drev,
                ngram=ng,
                ngram_original=ng,
                length=len(ng),
                total_count=MIN_OCCURRENCES,
                chapter_count=1,
                chapters_json='{"0": 3}',
                left_contexts_json="{}",
                right_contexts_json="{}",
                left_entropy=0.0,
                right_entropy=0.0,
                min_pmi=1.0,
                is_single_char_run=1,
                is_unknown=1,
                alt_segmentation=0,
                repetition_unstable=0,
                pattern_hits_json="[]",
            )
            for i, ng in enumerate(("看着", "前方"))
        ],
    )
    project_dir = tmp_path / "proj"
    project = open_project(project_dir)
    dic = load_revision_dictionary(project, drev)
    summary = build_candidates(
        st,
        book_id=project.book_id,
        dictionary=dic,
        dictionary_revision_id=drev,
        source_revision_id="rev-manual",
    )
    assert summary.skipped_manual == 2
    assert summary.candidates == 0 and summary.unresolved == 0


def test_build_candidates_deterministic(tmp_path):
    st, summary, drev = _learned(tmp_path)
    first = st.conn.execute(
        "SELECT source, proposed_target, kind, status, provenance_json, eligible_auto "
        "FROM term_candidates ORDER BY source"
    ).fetchall()
    project = open_project(tmp_path / "proj")
    dic = load_revision_dictionary(project, drev)
    rev_id = st.conn.execute(
        "SELECT source_revision_id FROM observations LIMIT 1"
    ).fetchone()[0]
    build_candidates(
        st,
        book_id=project.book_id,
        dictionary=dic,
        dictionary_revision_id=drev,
        source_revision_id=rev_id,
    )
    second = st.conn.execute(
        "SELECT source, proposed_target, kind, status, provenance_json, eligible_auto "
        "FROM term_candidates ORDER BY source"
    ).fetchall()
    assert first == second and len(first) > 0


def test_build_candidates_ac4_ambiguous_part_not_eligible(tmp_path):
    """AC 4: entry con co 2 target uu tien khac nhau -> eligible_auto=0."""
    dict_dir = _dict_dir(tmp_path)
    # Thu moi 2 target cho cung entry con 紫 (loader _insert append — 2 entries).
    with (dict_dir / "QualityOverrides.txt").open("a", encoding="utf-8") as fh:
        fh.write("紫=tím\n")
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    rev = import_snapshot(project, src)
    st = State(project.db_path)
    st.upsert_source_revision(
        rev.id, rev.content_hash, rev.encoding, rev.byte_size, str(rev.snapshot_path)
    )
    drev = ensure_active_revision(dict_dir, project)
    dic = load_revision_dictionary(project, drev)
    run_discovery(st, source_revision=rev, dictionary=dic, dictionary_revision_id=drev)
    build_candidates(
        st,
        book_id=project.book_id,
        dictionary=dic,
        dictionary_revision_id=drev,
        source_revision_id=rev.id,
    )
    frag = _cand(st, "紫霄山")
    assert frag["status"] == "candidate"
    assert frag["eligible_auto"] == 0
    prov = json.loads(frag["provenance_json"])
    assert "紫" in prov["sources"][0]["info"]["ambiguous_parts"]


def test_normalize_target_strips_edge_punctuation():
    """AC 2: rule dau cau — strip dau cau hai dau, collapse khoang trang."""
    assert _normalize_target("  huyền   thiên. ") == "huyền thiên"
    assert _normalize_target("，tử tiêu núi，") == "tử tiêu núi"
    assert _normalize_target("«huyền thiên»") == "huyền thiên"
    # Dau cau ben trong la phan nghia — giu nguyen.
    assert _normalize_target("mộ-bạch") == "mộ-bạch"
