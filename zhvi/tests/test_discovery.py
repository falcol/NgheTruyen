"""Tests cho learning/discovery.py + bang observations (story 3.1)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from zhvi.learning.discovery import run_discovery
from zhvi.project import create_project
from zhvi.revision import ensure_active_revision, load_revision_dictionary
from zhvi.snapshot import import_snapshot
from zhvi.state import ObservationRow, State


@pytest.fixture()
def st(tmp_path):
    s = State(tmp_path / "state.sqlite3")
    yield s
    s.close()


def _obs_row(ngram: str, **over) -> ObservationRow:
    fields = {
        "id": f"id-{ngram}",
        "source_revision_id": "rev1",
        "dictionary_revision_id": "drev1",
        "ngram": ngram,
        "ngram_original": ngram,
        "length": len(ngram),
        "total_count": 3,
        "chapter_count": 2,
        "chapters_json": '{"1": 2, "2": 1}',
        "left_contexts_json": '{"的": 3}',
        "right_contexts_json": '{"是": 3}',
        "left_entropy": 0.0,
        "right_entropy": 0.0,
        "min_pmi": 1.5,
        "is_single_char_run": 0,
        "is_unknown": 0,
        "alt_segmentation": 0,
        "repetition_unstable": 0,
        "pattern_hits_json": '["person"]',
    }
    fields.update(over)
    return ObservationRow(**fields)


def test_schema_v4_has_observations(st):
    tables = {
        r[0]
        for r in st.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "observations" in tables
    version = st.conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()[0]
    # v4 = story 3.1 bang observations; v5 = story 3.2 term_candidates mo rong.
    assert int(version) >= 4


def test_replace_observations_replaces_per_revision(st):
    st.replace_observations("rev1", [_obs_row("天宗"), _obs_row("玄天")])
    count = st.conn.execute(
        "SELECT COUNT(*) FROM observations WHERE source_revision_id='rev1'"
    ).fetchone()[0]
    assert count == 2

    # Replace cung revision: khong append — bo cu ghi moi.
    st.replace_observations(
        "rev1", [_obs_row("天宗"), _obs_row("玄天"), _obs_row("李慕白")]
    )
    rows = st.conn.execute(
        "SELECT ngram FROM observations WHERE source_revision_id='rev1' ORDER BY ngram"
    ).fetchall()
    assert [r[0] for r in rows] == ["天宗", "李慕白", "玄天"]

    # Revision khac khong bi anh huong.
    st.replace_observations(
        "rev2", [_obs_row("天宗", source_revision_id="rev2", id="id-rev2-天宗")]
    )
    count_rev1 = st.conn.execute(
        "SELECT COUNT(*) FROM observations WHERE source_revision_id='rev1'"
    ).fetchone()[0]
    assert count_rev1 == 3


def test_replace_observations_atomic_on_bad_row(st):
    st.replace_observations("rev1", [_obs_row("天宗")])
    with pytest.raises(AttributeError):
        # Row sai kieu lam loi giua transaction -> rollback toan bo.
        st.replace_observations("rev1", [_obs_row("李慕白"), "not-a-row"])
    # Transaction rollback: khong row moi, row cu nguyen ven.
    rows = st.conn.execute(
        "SELECT ngram FROM observations WHERE source_revision_id='rev1'"
    ).fetchall()
    assert [r[0] for r in rows] == ["天宗"]


# ---- run_discovery (Task 2/3) ----

SRC = (
    "第一章\n\n"
    "李慕白看着前方。\n\n"
    "第二章\n\n"
    "李慕白运转玄天诀。\n\n"
    "紫霄山上玄天宗。\n\n"
)


def _mini_dict_dir(tmp_path: Path) -> Path:
    d = tmp_path / "mini-dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "看着=nhìn về phía trước\n前方=phía trước\n运转=vận chuyển\n"
        "玄天=huyền thiên\n紫=tử\n霄=tiêu\n山=núi\n宗=tông\n诀=quyết\n"
        "第一章=Chương 1\n第二章=Chương 2\n",
        encoding="utf-8",
    )
    return d


@pytest.fixture()
def discovered(tmp_path):
    """Project da import source + discovery da chay; tra (project, st, summary)."""
    dict_dir = _mini_dict_dir(tmp_path)
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
    summary = run_discovery(
        st, source_revision=rev, dictionary=dic, dictionary_revision_id=drev
    )
    yield project, st, summary
    st.close()


def _obs(st, ngram: str) -> dict:
    cur = st.conn.execute("SELECT * FROM observations WHERE ngram=?", (ngram,))
    row = cur.fetchone()
    assert row is not None, f"thieu observation: {ngram}"
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def test_discovery_counts_absolute_and_per_chapter(discovered):
    _, st, summary = discovered
    assert summary.source_revision_id
    # 李慕白: chuong 0 mot lan, chuong 1 mot lan.
    row = _obs(st, "李慕白")
    assert row["total_count"] == 2
    assert json.loads(row["chapters_json"]) == {"0": 1, "1": 1}
    assert row["chapter_count"] == 2
    # Ngram nam trong entry that: khong unknown, khong fragmented.
    row_ok = _obs(st, "看着")
    assert row_ok["is_unknown"] == 0
    assert row_ok["is_single_char_run"] == 0
    assert json.loads(row_ok["chapters_json"]) == {"0": 1}


def test_discovery_flags_fragmented_and_pattern(discovered):
    _, st, _ = discovered
    # 李慕白 khong co entry -> ca 3 ky tu la unknown single -> is_unknown.
    row_name = _obs(st, "李慕白")
    assert row_name["is_unknown"] == 1
    assert "person" in json.loads(row_name["pattern_hits_json"])

    # 紫霄山: moi ky tu co single-char entry -> bi tach thanh 3 entry
    # mot ky tu (fragmented), nhung KHONG unknown.
    row_frag = _obs(st, "紫霄山")
    assert row_frag["is_single_char_run"] == 1
    assert row_frag["is_unknown"] == 0
    assert "place" in json.loads(row_frag["pattern_hits_json"])


def test_discovery_deterministic(discovered, tmp_path):
    project, st, summary = discovered
    rev = st.latest_source_revision()
    drev = summary.dictionary_revision_id
    dic = load_revision_dictionary(project, drev)

    def _snapshot_rows() -> list[dict]:
        cur = st.conn.execute("SELECT * FROM observations ORDER BY ngram")
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]

    first = _snapshot_rows()
    run_discovery(
        st, source_revision=rev, dictionary=dic, dictionary_revision_id=drev
    )
    second = _snapshot_rows()
    assert len(first) == len(second) and len(first) > 0
    for a, b in zip(first, second):
        # Moi cot giong het tru created_at (khong thuoc identity observation).
        a.pop("created_at")
        b.pop("created_at")
        assert a == b


def test_discovery_does_not_touch_engine(tmp_path):
    """Fingerprint load TRUOC discovery — phat hien duoc mutation neu co."""
    dict_dir = _mini_dict_dir(tmp_path)
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
        before = load_revision_dictionary(project, drev)
        run_discovery(
            st, source_revision=rev, dictionary=before, dictionary_revision_id=drev
        )
        after = load_revision_dictionary(project, drev)
    finally:
        st.close()
    # Trie khong nap observation: fingerprint + so entry khong doi.
    assert before.fingerprint == after.fingerprint
    assert before.entry_count == after.entry_count
