"""Tests cho learning/evidence.py + bang candidate_evidence (story 3.3)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from zhvi.learning.candidate import MIN_OCCURRENCES, build_candidates
from zhvi.learning.discovery import run_discovery
from zhvi.learning.evidence import evaluate_candidates
from zhvi.project import create_project
from zhvi.revision import ensure_active_revision, load_revision_dictionary
from zhvi.snapshot import import_snapshot
from zhvi.state import EvidenceRow, State


@pytest.fixture()
def st(tmp_path):
    s = State(tmp_path / "state.sqlite3")
    yield s
    s.close()


def _ev_row(candidate_id: str, group: str, **over) -> EvidenceRow:
    fields = {
        "id": f"id-{candidate_id}-{group}",
        "candidate_id": candidate_id,
        "book_id": "book-1",
        "dictionary_revision_id": "drev1",
        "group_name": group,
        "signals_json": '{"total_count": 3}',
        "score": 1.5,
    }
    fields.update(over)
    return EvidenceRow(**fields)


def test_schema_v6_has_candidate_evidence(st):
    tables = {
        r[0]
        for r in st.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "candidate_evidence" in tables
    from zhvi.state import SCHEMA_VERSION

    version = st.conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()[0]
    assert int(version) == SCHEMA_VERSION


def test_replace_evidence_replaces_scope_even_empty(st):
    st.replace_evidence("book-1", "drev1", [_ev_row("c1", "strength")])
    # Rows rong van xoa scope (semantics dong replace_candidates sau review 3.2).
    st.replace_evidence("book-1", "drev1", [])
    count = st.conn.execute(
        "SELECT COUNT(*) FROM candidate_evidence WHERE dictionary_revision_id='drev1'"
    ).fetchone()[0]
    assert count == 0

    st.replace_evidence("book-1", "drev1", [_ev_row("c1", "strength")])
    # Scope khac khong bi anh huong (candidate_id thuc te la content-addressed
    # theo scope nen khong trung).
    st.replace_evidence(
        "book-2",
        "drev2",
        [_ev_row("c9", "strength", book_id="book-2", dictionary_revision_id="drev2")],
    )
    drev1 = st.conn.execute(
        "SELECT COUNT(*) FROM candidate_evidence WHERE dictionary_revision_id='drev1'"
    ).fetchone()[0]
    assert drev1 == 1


def test_replace_evidence_atomic_on_bad_row(st):
    st.replace_evidence("book-1", "drev1", [_ev_row("c1", "strength")])
    with pytest.raises(AttributeError):
        st.replace_evidence("book-1", "drev1", [_ev_row("c2", "risk"), "not-a-row"])
    rows = st.conn.execute(
        "SELECT candidate_id FROM candidate_evidence WHERE dictionary_revision_id='drev1'"
    ).fetchall()
    assert [r[0] for r in rows] == ["c1"]


# ---- evaluate_candidates (Task 2+) ----

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


def _evaluated(tmp_path):
    dict_dir = _dict_dir(tmp_path)
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
    summary = evaluate_candidates(
        st, book_id=project.book_id, dictionary=dic, dictionary_revision_id=drev
    )
    return st, summary, project, drev


def _groups(st, source: str) -> dict:
    cur = st.conn.execute(
        "SELECT e.group_name, e.signals_json, e.score FROM candidate_evidence e "
        "JOIN term_candidates c ON c.id = e.candidate_id WHERE c.source=?",
        (source,),
    )
    return {g: (json.loads(sj), score) for g, sj, score in cur.fetchall()}


def test_evidence_six_groups_per_candidate(tmp_path):
    st, summary, project, drev = _evaluated(tmp_path)
    assert summary.candidates > 0
    assert summary.evidence_rows == summary.candidates * 6
    groups = _groups(st, "李慕白")
    assert set(groups) == {
        "strength", "stability", "benefit", "risk", "scope", "regression",
    }
    # AC 3: candidate co tin hieu hoc that (dict co PhienAm singles nen
    # 李慕白 la fragmented run chu khong unknown) co benefit duong.
    assert groups["benefit"][0]["reduces_single_char"] == 1
    assert groups["benefit"][1] > 0
    # AC 3 nguyen van: n-gram unknown that cung co benefit duong (khoi
    # unresolved van duoc ghi evidence de nguoi duyet thay).
    unk_groups = _groups(st, "未知语")
    assert unk_groups["benefit"][0]["reduces_unknown"] == 1
    assert unk_groups["benefit"][1] > 0
    # AC 3 / AC 2: regression la placeholder deferred.
    assert groups["regression"][0] == {"deferred": "story-3.4"}


def test_evidence_strength_from_observation(tmp_path):
    st, _, _, _ = _evaluated(tmp_path)
    obs = st.conn.execute(
        "SELECT total_count, min_pmi FROM observations WHERE ngram='李慕白'"
    ).fetchone()
    strength = _groups(st, "李慕白")["strength"]
    assert strength[0]["total_count"] == obs[0]
    assert strength[0]["min_pmi"] == obs[1]


def test_evidence_independent_of_output(tmp_path):
    """AC 2: co run cu voi output khac — evidence khong doi."""
    st, summary, project, drev = _evaluated(tmp_path)
    first = st.conn.execute(
        "SELECT candidate_id, group_name, signals_json, score FROM candidate_evidence "
        "ORDER BY candidate_id, group_name"
    ).fetchall()
    # Gia lap run cu voi output bat ky.
    st.upsert_source_revision("rev-old", "hash-old", "utf-8", 1, "/tmp/old.txt")
    run, _ = st.resume_or_create("r-old", "fp-old", "rev-old", drev, {})
    st.stage_block(
        run_id="r-old", block_id="b-old", chapter_ordinal=0, block_ordinal=1,
        source_start=0, source_end=9, source_hash="h", final_text="output cu",
        qa={}, route="DIRECT_VP", reasons=[], features={}, router_version="v1",
        attempt={"id": "a-old", "engine": "vp", "input_hash": "h", "status": "ok"},
    )
    dic = load_revision_dictionary(project, drev)
    evaluate_candidates(
        st, book_id=project.book_id, dictionary=dic, dictionary_revision_id=drev
    )
    second = st.conn.execute(
        "SELECT candidate_id, group_name, signals_json, score FROM candidate_evidence "
        "ORDER BY candidate_id, group_name"
    ).fetchall()
    assert first == second


def test_evidence_manual_conflict_risk(tmp_path):
    """AC 3: candidate overlap span manual entry co risk manual_conflict."""
    st, summary, project, drev = _evaluated(tmp_path)
    # Chen observation gia cho key chua manual entry lam prefix (看着前 chua
    # 着着...) vao CUNG source revision goc roi build + evaluate lai.
    rev_id = st.conn.execute(
        "SELECT source_revision_id FROM observations WHERE ngram='李慕白'"
    ).fetchone()[0]
    st.conn.execute(
        "INSERT OR REPLACE INTO observations "
        "(id, source_revision_id, dictionary_revision_id, ngram, ngram_original, "
        "length, total_count, chapter_count, chapters_json, left_contexts_json, "
        "right_contexts_json, left_entropy, right_entropy, min_pmi, "
        "is_single_char_run, is_unknown, alt_segmentation, repetition_unstable, "
        "pattern_hits_json, created_at) "
        "VALUES('id-看着前',?,?,'看着前','看着前',3,3,1,'{\"0\":3}','{}','{}',"
        "0.0,0.0,1.0,1,1,0,0,'[]','2026-01-01')",
        (rev_id, drev),
    )
    st.conn.commit()

    dic = load_revision_dictionary(project, drev)
    build_candidates(
        st,
        book_id=project.book_id,
        dictionary=dic,
        dictionary_revision_id=drev,
        source_revision_id=rev_id,
        min_occurrences=MIN_OCCURRENCES,
    )
    evaluate_candidates(
        st, book_id=project.book_id, dictionary=dic, dictionary_revision_id=drev
    )
    groups = _groups(st, "看着前")
    assert groups["risk"][0]["manual_conflict"] == 1
