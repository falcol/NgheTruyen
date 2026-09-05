"""Explain text cho nguoi duyet (story 3.5, AC 2 / AD-9).

Render text voi dictionary active, tra loi: tung span lay target tu entries
nao (layer), revision nao; span nao unknown; candidate nao lien quan; doi
entry se anh huong block nao. Khong doi state translation — chi ensure
revision active + ghi usage audit (feedback_events).
"""
from __future__ import annotations

from pathlib import Path

from zhvi.config import Config
from zhvi.correction import affected_block_ids
from zhvi.document import parse_document
from zhvi.learning.candidate import entry_layer, trie_entries
from zhvi.learning.terms import audit_usage
from zhvi.pipeline import ensure_book_dictionary
from zhvi.project import Project
from zhvi.state import State, cursor_dicts
from zhvi.vietphrase.loader import to_simplified
from zhvi.vietphrase.lattice import vp_plan

__all__ = ["explain_text"]


def explain_text(
    state: State, *, project: Project, dict_dir: Path, cfg: Config, text: str
) -> dict:
    """Explain segmentation + provenance cho mot doan text (AC 2)."""
    revision_id, dic = ensure_book_dictionary(project, dict_dir, cfg)
    draft = vp_plan(
        dic,
        text,
        beam=cfg.lattice_beam,
        occurrence_prefix="explain",
        collapse_reps=cfg.collapse_repetitions,
    )

    spans: list[dict] = []
    span_sources: list[str] = []
    for sp in draft.spans:
        key = to_simplified(sp.source, dic.trad_simp)
        entries = [
            {"layer": entry_layer(e), "target": e[0]}
            for e in trie_entries(dic, key)
        ]
        spans.append(
            {
                "source": sp.source,
                "target": sp.target,
                "source_start": sp.source_start,
                "source_end": sp.source_end,
                "policy": sp.policy,
                "entry_version_id": sp.entry_version_id,
                "alternatives": list(sp.alternatives),
                "entries": entries,
            }
        )
        span_sources.append(sp.source)

    unknown_spans = [
        {
            "start": u.source_start,
            "end": u.source_end,
            "text": text[u.source_start : u.source_end],
        }
        for u in draft.unknown_spans
    ]

    cur = state.conn.execute(
        "SELECT DISTINCT source FROM term_candidates WHERE book_id=? "
        "ORDER BY source",
        (project.book_id,),
    )
    cand_sources = [r[0] for r in cur.fetchall() if r[0] in text]
    candidates = [
        {
            "source": c["source"],
            "target": c["proposed_target"],
            "status": c["status"],
        }
        for c in _candidate_rows(state, project.book_id, cand_sources)
    ]

    affected: list[str] = []
    affected_note = ""
    rev = state.latest_source_revision()
    if rev is None:
        affected_note = "no_source_revision"
    elif span_sources:
        doc = parse_document(
            Path(rev.snapshot_path).read_text(encoding=rev.encoding),
            chapter_detection=cfg.chapter_detection,
            chapter_regex=cfg.chapter_regex,
        )
        affected = affected_block_ids(doc, set(span_sources), dic.trad_simp)

    audit_usage(state, action="terms_explain")
    return {
        "revision": revision_id,
        "text": text,
        "output": draft.text,
        "spans": spans,
        "unknown_spans": unknown_spans,
        "candidates": candidates,
        "affected_blocks": affected,
        "affected_note": affected_note,
    }


def _candidate_rows(state: State, book_id: str, sources: list[str]) -> list[dict]:
    """Row candidate moi nhat theo rowid cho tung source (moi status)."""
    rows: list[dict] = []
    for source in sources:
        cur = state.conn.execute(
            "SELECT source, proposed_target, status FROM term_candidates "
            "WHERE book_id=? AND source=? ORDER BY rowid DESC LIMIT 1",
            (book_id, source),
        )
        rows.extend(cursor_dicts(cur))
    return rows
