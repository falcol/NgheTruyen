"""Book -> registry evidence submitter (story 4.2, AD-17).

Book project GUI evidence bat bien vao registry; khong mutate global
candidate/revision truc tiep (data-model 'Phan quyen nguon chan thai').
Registry nhan EvidenceRecord thuan du lieu — module nay la cau noi mot
chieu book State -> registry, khong import nguoc.
"""
from __future__ import annotations

from pathlib import Path

from zhvi.registry import (
    EvidenceRecord,
    ingest_evidence,
    resolve_registry_dir,
)
from zhvi.state import State, cursor_dicts


def build_evidence_records(state: State) -> list[EvidenceRecord]:
    """Map candidate_evidence rows + active source revision cua book thanh
    payload gui registry.

    occurrence_span = group_name: evidence book la aggregate theo 6 nhom
    tin hieu (khong co per-text-span) — identity deterministic, moi
    (candidate, book, source_revision) toi da 6 records.
    """
    src = state.latest_source_revision()
    if src is None:
        return []
    cands = {
        r["id"]: r
        for r in cursor_dicts(
            state.conn.execute(
                "SELECT id, source, proposed_target FROM term_candidates"
            )
        )
    }
    rows = cursor_dicts(state.conn.execute("SELECT * FROM candidate_evidence"))
    return [
        EvidenceRecord(
            book_id=row["book_id"],
            source_revision_id=src.id,
            candidate_id=row["candidate_id"],
            occurrence_span=row["group_name"],
            dictionary_revision_id=row["dictionary_revision_id"],
            group_name=row["group_name"],
            signals_json=row["signals_json"],
            score=row["score"],
            source_created_at=src.created_at,
            source=cands.get(row["candidate_id"], {}).get("source", ""),
            target=cands.get(row["candidate_id"], {}).get("proposed_target", ""),
        )
        for row in rows
    ]


def submit_book_evidence(state: State, dict_dir: Path | str) -> dict:
    """Convenience: build + ingest vao registry cua dict_dir.
    Tra {submitted, inserted, books} cho caller/test."""
    records = build_evidence_records(state)
    result = ingest_evidence(resolve_registry_dir(dict_dir), records)
    result["books"] = len({r.book_id for r in records})
    return result
