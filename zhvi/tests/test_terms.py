"""Tests cho learning/terms.py + learning/explain.py (story 3.5)."""
from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from zhvi.cli import app
from zhvi.config import resolve_config
from zhvi.learning.candidate import (
    build_candidates,
    entry_layer,
    trie_entries,
)
from zhvi.learning.discovery import run_discovery
from zhvi.learning.evidence import evaluate_candidates
from zhvi.learning.explain import explain_text
from zhvi.learning.promotion import revoke_book_auto, run_promotion
from zhvi.learning.terms import TermsError, accept_term, list_terms, reject_term
from zhvi.pipeline import TranslateRequest, translate_project
from zhvi.project import create_project
from zhvi.revision import ensure_active_revision, load_revision_dictionary
from zhvi.state import State

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


def _learned(tmp_path):
    """Translate (baseline) + discovery + candidates + evidence."""
    dict_dir = _dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
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


def _feedback_actions(st):
    return [
        r[0]
        for r in st.conn.execute("SELECT action FROM feedback_events").fetchall()
    ]


def test_list_terms_candidates_with_evidence(tmp_path):
    """AC 1: list hien candidate + evidence groups + status."""
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    terms = list_terms(st, book_id=project.book_id)
    by_source = {t["source"]: t for t in terms}
    assert "李慕白" in by_source
    entry = by_source["李慕白"]
    assert entry["status"] == "candidate"
    assert set(entry["evidence"]) == {
        "strength", "stability", "benefit", "risk", "scope", "regression",
    }
    assert entry["target"] == "lý mộ bạch"
    # filter status
    promoted = list_terms(st, book_id=project.book_id, status="book_auto")
    assert promoted == []
    run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg, dictionary_revision_id=drev
    )
    promoted = list_terms(st, book_id=project.book_id, status="book_auto")
    assert any(t["source"] == "李慕白" for t in promoted)


def test_accept_term_creates_manual_entry(tmp_path):
    """AC 1: accept tao manual entry — manual thang auto tu do."""
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    active_before = st.active_revision_id("book", project.book_id)

    revision, target = accept_term(
        st, project=project, dict_dir=dict_dir, cfg=cfg, source="李慕白"
    )
    assert target == "lý mộ bạch"


    assert revision != active_before
    # glossary.manual.tsv co dong moi (user-directed append)
    manual = (project.root / "glossary.manual.tsv").read_text(encoding="utf-8")
    assert "李慕白=lý mộ bạch" in manual
    # revision moi active; manifest co layer manual:book voi entry
    assert st.active_revision_id("book", project.book_id) == revision
    dic = load_revision_dictionary(project, revision)
    entries = trie_entries(dic, "李慕白")
    assert any(entry_layer(e) >= 6 for e in entries)  # BOOK_MANUAL thang auto
    # event accepted actor user + status
    events = st.promotion_events_for(project.book_id, source="李慕白")
    assert [e.event_type for e in events][-1] == "accepted"
    assert events[-1].actor == "user"
    assert events[-1].revision_id == revision
    assert _candidate(st, "李慕白")["status"] == "accepted"
    assert "terms_accept" in _feedback_actions(st)


def test_accept_term_edges(tmp_path):
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    with pytest.raises(TermsError):
        accept_term(st, project=project, dict_dir=dict_dir, cfg=cfg, source="khong_co_key")
    # double-accept: lan 2 guard manual-entry bats (bundle da chua entry)
    accept_term(st, project=project, dict_dir=dict_dir, cfg=cfg, source="李慕白")
    with pytest.raises(TermsError):
        accept_term(st, project=project, dict_dir=dict_dir, cfg=cfg, source="李慕白")
    manual_lines = [
        ln for ln in (project.root / "glossary.manual.tsv")
        .read_text(encoding="utf-8").splitlines() if ln.startswith("李慕白=")
    ]
    assert len(manual_lines) == 1
    # unresolved: chen observation unknown khong co target
    st.conn.execute(
        "INSERT OR REPLACE INTO term_candidates "
        "(id, book_id, source, proposed_target, kind, status, provenance_json, "
        "dictionary_revision_id, eligible_auto) "
        "VALUES('cand-unk', ?, '未知语', '', 'term', 'unresolved', '{}', ?, 0)",
        (project.book_id, drev),
    )
    st.conn.commit()
    with pytest.raises(TermsError):
        accept_term(st, project=project, dict_dir=dict_dir, cfg=cfg, source="未知语")


def test_reject_term_user_event(tmp_path):
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    reject_term(st, book_id=project.book_id, source="李慕白")
    events = st.promotion_events_for(project.book_id, source="李慕白")
    assert [e.event_type for e in events] == ["rejected"]
    assert events[0].actor == "user"
    assert _candidate(st, "李慕白")["status"] == "rejected"
    assert "terms_reject" in _feedback_actions(st)

    # book_auto phai di revoke, khong reject
    run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg,
        dictionary_revision_id=drev,
    )
    revoke_book_auto(st, project=project, dict_dir=dict_dir, source="慕白")
    st.conn.execute(
        "UPDATE term_candidates SET status='book_auto' WHERE source='李慕白'"
    )
    st.conn.commit()
    with pytest.raises(TermsError):
        reject_term(st, book_id=project.book_id, source="李慕白")


# ---- Task 3: explain ----

def test_explain_text_spans_layers_candidates_affected(tmp_path):
    """AC 2: explain hien segmentation + provenance (layer/revision) +
    candidate lien quan + affected blocks."""
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    s = run_promotion(
        st, project=project, dict_dir=dict_dir, cfg=cfg, dictionary_revision_id=drev
    )
    assert s.promoted >= 1

    payload = explain_text(
        st, project=project, dict_dir=dict_dir, cfg=cfg, text="李慕白看着前方。"
    )
    assert payload["revision"] == st.active_revision_id("book", project.book_id)
    spans = {sp["source"]: sp for sp in payload["spans"]}
    assert "李慕白" in spans
    # span promoted co layer BOOK_AUTO trong entries cua no
    libai = spans["李慕白"]
    assert any(e["layer"] == 2 for e in libai["entries"])  # BOOK_AUTO
    assert libai["target"]
    # span manual (QualityOverrides -> GLOBAL_MANUAL=4)
    assert "看着" in spans
    assert any(e["layer"] == 4 for e in spans["看着"]["entries"])
    # unknown spans: text deu match — rong
    assert payload["unknown_spans"] == []
    # candidate lien quan
    cand_sources = {c["source"] for c in payload["candidates"]}
    assert "李慕白" in cand_sources
    # affected blocks chua span sources
    assert payload["affected_blocks"]
    # AC 3: usage audit
    assert "terms_explain" in _feedback_actions(st)


def test_explain_text_unknown_and_empty(tmp_path):
    st, project, dict_dir, cfg, drev = _learned(tmp_path)
    payload = explain_text(
        st, project=project, dict_dir=dict_dir, cfg=cfg, text="未知语 xyz"
    )
    assert payload["spans"] == []
    unk = [u["text"] for u in payload["unknown_spans"]]
    # renderer tach unknown run thanh tung ky tu don
    assert "".join(unk) == "未知语"
    empty = explain_text(
        st, project=project, dict_dir=dict_dir, cfg=cfg, text=""
    )
    assert empty["spans"] == [] and empty["unknown_spans"] == []


# ---- Task 4: CLI ----

def test_cli_terms_and_explain(tmp_path):
    """AC 1-3: terms list/accept/revoke + explain qua CLI; full vong
    list -> accept -> translate refresh doi output dung cho."""
    dict_dir = _dict_dir(tmp_path)
    src = tmp_path / "truyen.txt"
    src.write_text(SRC, encoding="utf-8")
    project = create_project(tmp_path / "proj")
    out1 = tmp_path / "v1.txt"
    runner = CliRunner()
    # baseline translate
    r0 = runner.invoke(app, [
        "translate", str(src), "-o", str(out1), "-p", str(project.root),
        "--dict-dir", str(dict_dir), "--json",
    ])
    assert r0.exit_code == 0, r0.output
    # learn sinh candidates
    rl = runner.invoke(app, [
        "learn", "-p", str(project.root), "--dict-dir", str(dict_dir),
    ])
    assert rl.exit_code == 0, rl.output

    rlist = runner.invoke(app, [
        "terms", "list", "-p", str(project.root),
    ])
    assert rlist.exit_code == 0, rlist.output
    listed = json.loads(rlist.output)
    assert any(t["source"] == "李慕白" for t in listed)

    # doi target de output thay doi khi accept (join-con target trung render)
    st = State(project.db_path)
    st.conn.execute(
        "UPDATE term_candidates SET proposed_target='Lý Mộ Bạch Đại Hiệp' "
        "WHERE source='李慕白'"
    )
    st.conn.commit()
    st.close()

    racc = runner.invoke(app, [
        "terms", "accept", "李慕白", "-p", str(project.root),
        "--dict-dir", str(dict_dir),
    ])
    assert racc.exit_code == 0, racc.output
    acc = json.loads(racc.output)
    assert acc["source"] == "李慕白"
    assert "Lý Mộ Bạch Đại Hiệp" in (
        project.root / "glossary.manual.tsv"
    ).read_text(encoding="utf-8")

    # translate refresh -> manual thang, output doi dung cho
    out2 = tmp_path / "v2.txt"
    rt = runner.invoke(app, [
        "translate", str(src), "-o", str(out2), "-p", str(project.root),
        "--dict-dir", str(dict_dir), "--refresh-revision", "--json",
    ])
    assert rt.exit_code == 0, rt.output
    text2 = out2.read_text(encoding="utf-8")
    assert "Lý Mộ Bạch Đại Hiệp" in text2

    rexp = runner.invoke(app, [
        "explain", "李慕白看着前方。", "-p", str(project.root),
        "--dict-dir", str(dict_dir),
    ])
    assert rexp.exit_code == 0, rexp.output
    payload = json.loads(rexp.output)
    spans = {s["source"]: s for s in payload["spans"]}
    assert "李慕白" in spans
    assert any(e["layer"] == 6 for e in spans["李慕白"]["entries"])  # BOOK_MANUAL

    # reject + revoke: learn lai de promote con lai (慕白/李慕), roi revoke 慕白
    rl2 = runner.invoke(app, [
        "learn", "-p", str(project.root), "--dict-dir", str(dict_dir),
    ])
    assert rl2.exit_code == 0, rl2.output
    rrej = runner.invoke(app, [
        "terms", "reject", "李慕", "-p", str(project.root),
    ])
    assert rrej.exit_code == 0, rrej.output
    rrev = runner.invoke(app, [
        "terms", "revoke", "慕白", "-p", str(project.root),
        "--dict-dir", str(dict_dir),
    ])
    assert rrev.exit_code == 0, rrev.output
    rev_payload = json.loads(rrev.output)
    # revoke that su: revision moi + event actor user + key roi BOOK_AUTO
    st2 = State(project.db_path)
    try:
        assert rev_payload["revision"] != acc["revision"]
        ev = st2.promotion_events_for(project.book_id, source="慕白")
        assert ev and ev[-1].event_type == "revoked" and ev[-1].actor == "user"
        dic2 = load_revision_dictionary(project, rev_payload["revision"])
        assert not any(
            entry_layer(e) == 2 for e in trie_entries(dic2, "慕白")
        )  # BOOK_AUTO
        actions = [
            r[0] for r in st2.conn.execute(
                "SELECT action FROM feedback_events"
            ).fetchall()
        ]
        assert "terms_list" in actions and "terms_revoke" in actions
    finally:
        st2.close()


def test_explain_no_source_revision_note(tmp_path):
    """AC 2: project chua import source — affected_blocks rong kem note."""
    dict_dir = _dict_dir(tmp_path)
    project = create_project(tmp_path / "proj")
    st = State(project.db_path)
    cfg = resolve_config(project.root)
    payload = explain_text(
        st, project=project, dict_dir=dict_dir, cfg=cfg, text="李慕白"
    )
    assert payload["affected_blocks"] == []
    assert payload["affected_note"] == "no_source_revision"
