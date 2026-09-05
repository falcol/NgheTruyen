"""Tests cho learning/promotion.py + bang promotion_events (story 3.4)."""
from __future__ import annotations

import json

import pytest

from zhvi.config import resolve_config
from zhvi.correction import diff_revisions
from zhvi.learning.candidate import build_candidates
from zhvi.learning.discovery import run_discovery
from zhvi.learning.evidence import evaluate_candidates
from zhvi.learning.promotion import PromotionError, run_promotion, revoke_book_auto
from zhvi.pipeline import TranslateRequest, translate_project
from zhvi.project import create_project
from zhvi.revision import ensure_active_revision, load_revision_dictionary
from zhvi.state import PromotionEventRow, State


@pytest.fixture()
def st(tmp_path):
    s = State(tmp_path / "state.sqlite3")
    yield s
    s.close()


# ---- Task 1: migration v7 + promotion_events ----

def _ev_row(event_type: str, **over) -> PromotionEventRow:
    fields = {
        "id": f"ev-{event_type}",
        "book_id": "book-1",
        "candidate_id": "cand-1",
        "source": "李慕白",
        "event_type": event_type,
        "from_status": "candidate",
        "to_status": "book_auto",
        "actor": "system",
        "dictionary_revision_id": "drev1",
        "revision_id": "rev-new",
        "provenance_json": '{"gates": []}',
    }
    fields.update(over)
    return PromotionEventRow(**fields)


def test_schema_v7_has_promotion_events(st):
    tables = {
        r[0]
        for r in st.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert "promotion_events" in tables
    version = st.conn.execute(
        "SELECT value FROM meta WHERE key='schema_version'"
    ).fetchone()[0]
    assert int(version) == 7


def test_append_promotion_event_append_only(st):
    """AC 1: event ghi append-only — khong replace scope nhu candidates/evidence."""
    st.append_promotion_event(_ev_row("promoted"))
    st.append_promotion_event(
        _ev_row("rejected", id="ev-rej", to_status="rejected", revision_id="")
    )
    rows = st.promotion_events_for("book-1")
    assert [r.event_type for r in rows] == ["promoted", "rejected"]
    first = rows[0]
    assert first.from_status == "candidate"
    assert first.to_status == "book_auto"
    assert first.actor == "system"
    assert first.created_at  # timestamp luon co
    assert json.loads(first.provenance_json) == {"gates": []}


def test_promotion_events_filter_by_source_and_book(st):
    st.append_promotion_event(_ev_row("promoted"))
    st.append_promotion_event(
        _ev_row("promoted", id="ev-2", book_id="book-2", source="未知语")
    )
    only = st.promotion_events_for("book-1", source="李慕白")
    assert len(only) == 1
    assert only[0].source == "李慕白"
    assert st.promotion_events_for("book-9") == []


# ---- Task 2: gates + run_promotion + isolation + revoke ----

# 李慕白 xuat hien 6 lan / 3 chuong (compound tu PhienAm singles — benefit
# reduces_single_char); 看着前 chua manual prefix (risk manual_conflict).
SRC = (
    "第一章\n\n"
    "李慕白看着前方。\n\n"
    "第二章\n\n"
    "李慕白运转玄天诀。李慕白笑。\n\n"
    "第三章\n\n"
    "李慕白望着紫霄山。李慕白走。李慕白停。\n\n"
)


def _dict_dir(tmp_path):
    d = tmp_path / "mini-dicts"
    d.mkdir()
    (d / "QualityOverrides.txt").write_text(
        "看着=nhìn về phía trước\n前方=phía trước\n前=trước\n运转=vận chuyển\n"
        "玄天=huyền thiên\n紫=tử\n霄=tiêu\n山=núi\n诀=quyết\n望着=nhìn về\n"
        "笑=cười\n走=đi\n停=dừng\n第一章=Chương 1\n第二章=Chương 2\n第三章=Chương 3\n",
        encoding="utf-8",
    )
    (d / "ChinesePhienAmWords.txt").write_text(
        "李=lý\n慕=mộ\n白=bạch\n", encoding="utf-8"
    )
    return d


def _learned(tmp_path, src_text=SRC):
    """Project co baseline run (translate) + discovery/candidates/evidence."""
    dict_dir = _dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(src_text, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    res = translate_project(
        project, TranslateRequest(source=src, dict_dir=str(dict_dir))
    )
    assert res.exit_code == 0, res.report
    st = State(project.db_path)
    rev = st.latest_source_revision()
    cfg = resolve_config(project.root)
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
    evaluate_candidates(st, book_id=project.book_id, dictionary=dic, dictionary_revision_id=drev)
    return st, project, dict_dir, cfg, drev


def _candidate(st, source):
    cur = st.conn.execute(
        "SELECT * FROM term_candidates WHERE source=?", (source,)
    )
    cols = [d[0] for d in cur.description]
    rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    return rows[-1]


def _groups(st, candidate_id):
    cur = st.conn.execute(
        "SELECT group_name, signals_json FROM candidate_evidence WHERE candidate_id=?",
        (candidate_id,),
    )
    return {g: json.loads(sj) for g, sj in cur.fetchall()}


def test_promotion_promotes_passing_candidate(tmp_path):
    """AC 2: candidate du gates -> book_auto + glossary.auto.tsv qua revision
    builder; chi anh huong truyen do (dict_dir khong bi ghi)."""
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    cand = _candidate(st, "李慕白")
    assert cand["eligible_auto"] == 1

    summary = run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg, dictionary_revision_id=drev
    )

    assert summary.promoted >= 1
    assert summary.revision_after != summary.revision_before
    # entry xuat hien trong active revision moi + projection
    assert st.active_revision_id("book", project.book_id) == summary.revision_after
    proj_file = project.root / "glossary.auto.tsv"
    assert "李慕白=lý mộ bạch" in proj_file.read_text(encoding="utf-8")
    # dict_dir khong co projection global (scope book)
    assert not (dict_dir / "AutoVietPhrase.txt").exists()
    # candidate status + event promoted
    cand2 = _candidate(st, "李慕白")
    assert cand2["status"] == "book_auto"
    events = st.promotion_events_for(project.book_id, source="李慕白")
    assert [e.event_type for e in events] == ["promoted"]
    assert events[0].from_status == "candidate"
    assert events[0].to_status == "book_auto"
    assert events[0].revision_id == summary.revision_after


def test_promotion_idempotent_no_duplicate_events(tmp_path):
    """AC 1: chay promotion 2 lan cung state — khong nhan doi event."""
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    s1 = run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg, dictionary_revision_id=drev
    )
    s2 = run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg, dictionary_revision_id=drev
    )
    assert s1.revision_after == s2.revision_after  # content-addressed
    assert s2.promoted == 0 and s2.skipped >= 1
    events = st.promotion_events_for(project.book_id, source="李慕白")
    assert len(events) == 1


def test_promotion_gate_fail_rejects_score_cannot_compensate(tmp_path):
    """AC 2: gate fail MOT muc la reject — diem cao khong bu.

    Candidate 看着前: manual conflict (risk) — du strength cao van reject."""
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    rev = st.latest_source_revision()
    st.conn.execute(
        "INSERT OR REPLACE INTO observations "
        "(id, source_revision_id, dictionary_revision_id, ngram, ngram_original, "
        "length, total_count, chapter_count, chapters_json, left_contexts_json, "
        "right_contexts_json, left_entropy, right_entropy, min_pmi, "
        "is_single_char_run, is_unknown, alt_segmentation, repetition_unstable, "
        "pattern_hits_json, created_at) "
        "VALUES('id-kzz',?,?, '看着前','看着前',3,6,3,'{\"0\":6}','{}','{}',"
        "1.0,1.0,9.0,1,1,0,0,'[]','2026-01-01')",
        (rev.id, drev),
    )
    st.conn.commit()
    from zhvi.learning.candidate import MIN_OCCURRENCES

    dic = load_revision_dictionary(project, drev)
    build_candidates(
        st, book_id=project.book_id, dictionary=dic,
        dictionary_revision_id=drev, source_revision_id=rev.id,
        min_occurrences=MIN_OCCURRENCES,
    )
    evaluate_candidates(
        st, book_id=project.book_id, dictionary=dic, dictionary_revision_id=drev
    )
    cand = _candidate(st, "看着前")
    groups = _groups(st, cand["id"])
    assert groups["risk"]["manual_conflict"] == 1  # fixture dung that

    before = st.active_revision_id("book", project.book_id)
    summary = run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg, dictionary_revision_id=drev
    )
    # 看着前 bi reject du strength cao; khong bao gio len book_auto
    events = st.promotion_events_for(project.book_id, source="看着前")
    assert [e.event_type for e in events] == ["rejected"]
    failed = json.loads(events[0].provenance_json)["gates"]
    assert any(g["name"] == "no_manual_conflict" and not g["passed"] for g in failed)
    # Diem cao khong bu: cac gate CON LAI deu pass — reject chi vi 1 gate.
    assert all(g["passed"] for g in failed if g["name"] != "no_manual_conflict")
    assert _candidate(st, "看着前")["status"] == "rejected"
    proj_file = project.root / "glossary.auto.tsv"
    if summary.revision_after != before:
        assert "看着前" not in proj_file.read_text(encoding="utf-8")


def test_promotion_isolation_changes_only_affected_blocks(tmp_path):
    """AC 3: block thay doi dung tap block chua candidate.

    De target khac render hien tai (builder join-con target thuong trung
    voi render singles vi renderer space-separator) de isolation co thay
    doi that de kiem chung."""
    from pathlib import Path

    from zhvi.correction import affected_block_ids
    from zhvi.document import parse_document

    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    cand = _candidate(st, "李慕白")
    # Doi target candidate (id content-addressed theo key — evidence van map).
    st.conn.execute(
        "UPDATE term_candidates SET proposed_target='Lý Mộ Bạch Đại Hiệp' WHERE id=?",
        (cand["id"],),
    )
    st.conn.commit()

    summary = run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg, dictionary_revision_id=drev
    )
    assert summary.promoted >= 1
    assert summary.changed_blocks, "phai co block doi khi target khac render cu"

    rev = st.latest_source_revision()
    doc = parse_document(
        Path(rev.snapshot_path).read_text(encoding=rev.encoding)
    )
    dic_new = load_revision_dictionary(project, summary.revision_after)
    affected = affected_block_ids(doc, {"李慕白"}, dic_new.trad_simp)
    assert set(summary.changed_blocks) <= set(affected)
    # Moi block chua key deu doi (target moi xuat hien trong render)
    assert set(summary.changed_blocks) == set(affected)


def test_promotion_populates_regression_evidence(tmp_path):
    """Regression evidence (deferred 3.3) duoc populate that sau promotion."""
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg, dictionary_revision_id=drev
    )
    cand = _candidate(st, "李慕白")
    groups = _groups(st, cand["id"])
    reg = groups["regression"]
    assert "deferred" not in reg
    assert reg["isolation_pass"] == 1
    assert isinstance(reg["changed_blocks"], int)


def test_revoke_book_auto_builds_new_revision_only_affected(tmp_path):
    """AC 4: revoke -> revision moi chi bo key; chi affected blocks doi."""
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    s1 = run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg, dictionary_revision_id=drev
    )
    assert s1.promoted >= 1

    new_rev = revoke_book_auto(st, project=project, dict_dir=dict_dir, source="李慕白")
    assert new_rev != s1.revision_after
    assert st.active_revision_id("book", project.book_id) == new_rev

    diff = diff_revisions(project, s1.revision_after, new_rev)
    assert diff["removed"] == ["李慕白"]
    assert diff["added"] == []
    # projection khong con entry
    proj_file = project.root / "glossary.auto.tsv"
    assert "李慕白" not in proj_file.read_text(encoding="utf-8")
    # event + status
    events = st.promotion_events_for(project.book_id, source="李慕白")
    assert [e.event_type for e in events] == ["promoted", "revoked"]
    assert events[1].revision_id == new_rev
    assert _candidate(st, "李慕白")["status"] == "revoked"
    diff = diff_revisions(project, s1.revision_after, new_rev)
    assert diff["changed"] == []  # chi remove key, khong doi entry khac
    assert diff["affected_keys"] == ["李慕白"]
    with pytest.raises(PromotionError):
        revoke_book_auto(st, project=project, dict_dir=dict_dir, source="李慕白")


def test_promotion_no_baseline_still_runs_invariants(tmp_path, monkeypatch):
    """HIGH (review 3.4): chua translate lan nao — invariant VAN phai chay
    tren block render (AD-20), khong duoc promote voi 0 lan check."""
    import zhvi.learning.promotion as promo_mod

    from zhvi.snapshot import import_snapshot

    calls: list[str] = []
    real = promo_mod.run_invariants

    def _spy(*, source, output, block_id):
        calls.append(block_id)
        return real(source=source, output=output, block_id=block_id)

    monkeypatch.setattr(promo_mod, "run_invariants", _spy)

    dict_dir = _dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    rev = import_snapshot(project, src)
    st = State(project.db_path)
    st.upsert_source_revision(
        rev.id, rev.content_hash, rev.encoding, rev.byte_size, str(rev.snapshot_path)
    )
    cfg = resolve_config(project.root)
    drev = ensure_active_revision(dict_dir, project)
    dic = load_revision_dictionary(project, drev)
    run_discovery(st, source_revision=rev, dictionary=dic, dictionary_revision_id=drev)
    build_candidates(
        st, book_id=project.book_id, dictionary=dic,
        dictionary_revision_id=drev, source_revision_id=rev.id,
    )
    evaluate_candidates(
        st, book_id=project.book_id, dictionary=dic, dictionary_revision_id=drev
    )

    summary = run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg, dictionary_revision_id=drev
    )
    assert summary.promoted >= 1
    assert calls, "invariant phai chay cho block khong co baseline"
    groups = _groups(st, _candidate(st, "李慕白")["id"])
    assert groups["regression"]["structural_invariant_pass"] == 1


def test_promotion_rerun_after_rebuild_no_duplicate_rejected(tmp_path):
    """MED (review 3.4): composite learn lai cung drev — replace_candidates
    reset status 'candidate' nhung event log phai chan rejected lap lai."""
    from zhvi.learning.candidate import MIN_OCCURRENCES
    from zhvi.snapshot import import_snapshot

    dict_dir = _dict_dir(tmp_path)
    # PhienAm rong -> khong compound candidate nao pass gates; chi 看着前
    # (observation gia, manual conflict) duoc danh gia va reject.
    (dict_dir / "ChinesePhienAmWords.txt").write_text("", encoding="utf-8")
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    rev = import_snapshot(project, src)
    st = State(project.db_path)
    st.upsert_source_revision(
        rev.id, rev.content_hash, rev.encoding, rev.byte_size, str(rev.snapshot_path)
    )
    cfg = resolve_config(project.root)
    drev = ensure_active_revision(dict_dir, project)
    dic = load_revision_dictionary(project, drev)
    run_discovery(st, source_revision=rev, dictionary=dic, dictionary_revision_id=drev)
    st.conn.execute(
        "INSERT OR REPLACE INTO observations "
        "(id, source_revision_id, dictionary_revision_id, ngram, ngram_original, "
        "length, total_count, chapter_count, chapters_json, left_contexts_json, "
        "right_contexts_json, left_entropy, right_entropy, min_pmi, "
        "is_single_char_run, is_unknown, alt_segmentation, repetition_unstable, "
        "pattern_hits_json, created_at) "
        "VALUES('id-kzz',?,?, '看着前','看着前',3,6,3,'{\"0\":6}','{}','{}',"
        "1.0,1.0,9.0,1,1,0,0,'[]','2026-01-01')",
        (rev.id, drev),
    )
    st.conn.commit()

    def _learn_once():
        dic2 = load_revision_dictionary(project, drev)
        build_candidates(
            st, book_id=project.book_id, dictionary=dic2,
            dictionary_revision_id=drev, source_revision_id=rev.id,
            min_occurrences=MIN_OCCURRENCES,
        )
        evaluate_candidates(
            st, book_id=project.book_id, dictionary=dic2, dictionary_revision_id=drev
        )
        return run_promotion(
            st, project=project, dict_dir=dict_dir, cfg=cfg,
            dictionary_revision_id=drev,
        )

    s1 = _learn_once()
    assert s1.rejected >= 1 and s1.promoted == 0
    s2 = _learn_once()  # composite learn lai: status bi reset nhung...
    events = st.promotion_events_for(project.book_id, source="看着前")
    assert [e.event_type for e in events] == ["rejected"]  # khong nhan doi
    assert s2.skipped >= 1
