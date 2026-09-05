"""Terms review lifecycle cho nguoi dung (story 3.5, AD-2/AD-5/AD-8).

list/accept/reject cho candidate; revoke nam o promotion.revoke_book_auto
(3.4). Accept la lenh NGUOI DUNG (actor user): append glossary.manual.tsv —
file human-owned nen KHONG di qua atomic_write (guard chan may ghi); day la
thi hanh y nguoi, khong phai learner tu quyet (AD-5). Revision moi publish
qua publish_revision (manual layer hash doi — AD-15).
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from zhvi.config import Config
from zhvi.learning.candidate import entry_layer, trie_entries
from zhvi.learning.promotion import current_auto_entries, promotion_event
from zhvi.pipeline import resolve_global_glossary
from zhvi.project import Project
from zhvi.revision import load_revision_dictionary, publish_revision
from zhvi.state import State, cursor_dicts, utc_now
from zhvi.vietphrase.layers import Layer

__all__ = [
    "TermsError", "accept_term", "audit_usage", "list_terms", "reject_term",
]


class TermsError(RuntimeError):
    """Terms command that bai (khong co candidate, da manual, ...)."""


def _latest_candidate(state: State, book_id: str, source: str) -> dict | None:
    cur = state.conn.execute(
        "SELECT * FROM term_candidates WHERE book_id=? AND source=? "
        "ORDER BY rowid DESC LIMIT 1",
        (book_id, source),
    )
    rows = cursor_dicts(cur)
    return rows[0] if rows else None


def audit_usage(state: State, *, action: str, candidate_id: str = "") -> None:
    """Usage audit (AC 3): moi lenh terms ghi 1 row feedback_events."""
    with state.conn:
        state.conn.execute(
            "INSERT INTO feedback_events (id, action, segment_id, candidate_id, "
            "entry_id, before_json, after_json, created_at) "
            "VALUES (?, ?, NULL, ?, NULL, '{}', '{}', ?)",
            (uuid.uuid4().hex, action, candidate_id, utc_now()),
        )


def list_terms(
    state: State, *, book_id: str, drev: str | None = None, status: str | None = None
) -> list[dict]:
    """Candidate + evidence + trang thai cho nguoi duyet (AC 1).

    drev mac dinh = cua candidates moi nhat theo rowid; loc status tuy chon.
    """
    if drev is None:
        row = state.conn.execute(
            "SELECT dictionary_revision_id FROM term_candidates WHERE book_id=? "
            "ORDER BY rowid DESC LIMIT 1",
            (book_id,),
        ).fetchone()
        if row is None:
            return []
        drev = row[0]
    event_counts = {
        r[0]: r[1]
        for r in state.conn.execute(
            "SELECT source, COUNT(*) FROM promotion_events WHERE book_id=? "
            "GROUP BY source",
            (book_id,),
        ).fetchall()
    }
    q = "SELECT * FROM term_candidates WHERE book_id=? AND dictionary_revision_id=?"
    args: list = [book_id, drev]
    if status is not None:
        q += " AND status=?"
        args.append(status)
    cur = state.conn.execute(q + " ORDER BY source", args)
    candidates = cursor_dicts(cur)
    ev_map: dict[str, dict[str, dict]] = {}
    cur = state.conn.execute(
        "SELECT candidate_id, group_name, signals_json FROM candidate_evidence "
        "WHERE book_id=? AND dictionary_revision_id=?",
        (book_id, drev),
    )
    for cand_id, group, signals_json in cur.fetchall():
        ev_map.setdefault(cand_id, {})[group] = json.loads(signals_json)
    return [
        {
            "source": c["source"],
            "target": c["proposed_target"],
            "kind": c["kind"],
            "status": c["status"],
            "eligible_auto": c["eligible_auto"],
            "provenance": _parse_json(c["provenance_json"]),
            "evidence": ev_map.get(c["id"], {}),
            "events": event_counts.get(c["source"], 0),
        }
        for c in candidates
    ]


def _parse_json(raw: str) -> dict:
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def accept_term(
    state: State, *, project: Project, dict_dir: Path, cfg: Config, source: str
) -> tuple[str, str]:
    """Accept candidate: tao manual entry trong glossary.manual.tsv (lenh
    user — AD-5) + publish revision moi (manual thang auto tu do).

    Tra (revision id moi active, target da accept).
    """
    book_id = project.book_id
    cand = _latest_candidate(state, book_id, source)
    if cand is None:
        raise TermsError(f"Khong co candidate nao cho {source!r}")
    dic_rev = cand["dictionary_revision_id"]
    if not cand["proposed_target"]:
        raise TermsError(f"Candidate {source!r} unresolved — khong co target de accept")
    target = cand["proposed_target"]

    # Key da co manual entry (bat ky layer manual) — khong accept lap.
    active = state.active_revision_id("book", book_id)
    dic = load_revision_dictionary(project, active)
    entries = trie_entries(dic, source)
    if any(entry_layer(e) >= Layer.GLOBAL_MANUAL for e in entries):
        raise TermsError(f"{source!r} da co manual entry — khong can accept")

    # Append user-directed vao glossary.manual.tsv (human-owned: KHONG qua
    # atomic_write — guard chan; day la thi hanh lenh nguoi dung, AD-5).
    glossary = project.root / "glossary.manual.tsv"
    # Pre-check doc file: retry sau publish fail (StaleActiveError) khong
    # append trung dong (guard bundle-active chua thay doi).
    if glossary.is_file() and any(
        line.split("=", 1)[0] == source
        for line in glossary.read_text(encoding="utf-8").splitlines()
        if "=" in line
    ):
        raise TermsError(f"{source!r} da co dong trong glossary.manual.tsv")
    line = f"{source}={target}\n"
    with glossary.open("a", encoding="utf-8") as f:
        f.write(line)
        f.flush()
        os.fsync(f.fileno())

    autos = current_auto_entries(project, active)
    result = publish_revision(
        dict_dir,
        project,
        autos,
        global_glossary=resolve_global_glossary(cfg),
        patterns=cfg.pattern_rules,
        expected_active=active,
    )

    state.append_promotion_event(
        promotion_event(
            book_id=book_id,
            candidate_id=cand["id"],
            source=source,
            event_type="accepted",
            from_status=cand["status"],
            to_status="accepted",
            drev=dic_rev,
            revision_id=result.revision_id,
            provenance={"target": target, "manual_glossary": str(glossary)},
            actor="user",
        )
    )
    state.update_candidate_status(cand["id"], "accepted")
    audit_usage(state, action="terms_accept", candidate_id=cand["id"])
    return result.revision_id, target


def reject_term(state: State, *, book_id: str, source: str) -> None:
    """Reject candidate (actor user): event audit + status rejected.

    book_auto phai di revoke (3.4) — khong reject.
    """
    cand = _latest_candidate(state, book_id, source)
    if cand is None:
        raise TermsError(f"Khong co candidate nao cho {source!r}")
    if cand["status"] == "book_auto":
        raise TermsError(
            f"{source!r} da book_auto — dung `zhvi terms revoke` de bo entry"
        )
    state.append_promotion_event(
        promotion_event(
            book_id=book_id,
            candidate_id=cand["id"],
            source=source,
            event_type="rejected",
            from_status=cand["status"],
            to_status="rejected",
            drev=cand["dictionary_revision_id"],
            revision_id="",
            provenance={},
            actor="user",
        )
    )
    state.update_candidate_status(cand["id"], "rejected")
    audit_usage(state, action="terms_reject", candidate_id=cand["id"])
