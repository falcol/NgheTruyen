"""Review (thiet ke muc 17/23) — export/collapse NEEDS_REVIEW blocks.

M2: sau khi invariant gate hard-fail, block duoc ghi qa.invariant_errors;
route/reasons nam o bang route_decisions (stage_block). `export_review`
collapse cac block NEEDS_REVIEW thanh review.jsonl. CLI `zhvi review`
(muc 4) cho nguoi dung xem/sua.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .config import ROUTE_VIETPHRASE
from .document import parse_document
from .export import node_block_id
from .state import State


@dataclass
class ReviewEntry:
    block_id: str
    chapter_ordinal: int
    block_ordinal: int
    source: str
    output: str
    route: str
    reasons: list[str] = field(default_factory=list)
    invariant_errors: list[str] = field(default_factory=list)

    def to_json(self) -> dict:
        return {
            "block_id": self.block_id,
            "chapter_ordinal": self.chapter_ordinal,
            "block_ordinal": self.block_ordinal,
            "source": self.source,
            "output": self.output,
            "route": self.route,
            "reasons": self.reasons,
            "invariant_errors": self.invariant_errors,
        }


def _is_reviewable(qa: dict) -> bool:
    """Block can review khi invariant hard-fail (muc 17/23).

    Story 1.1 (VP-only): khong con engine fallback — review chi den tu
    invariant gate fail.
    """
    return bool(qa.get("invariant_errors"))


class ReviewStore:
    def __init__(self, project: Path) -> None:
        self.project = Path(project)
        self.state = State(self.project / ".zhvi" / "state.sqlite3")

    def _doc_and_blocks(self, run_id: str | None):
        run = self.state.get_run(run_id) if run_id else self.state.latest_run()
        if run is None:
            raise ReviewError("Project chua co run nao")
        rev = self.state.conn.execute(
            "SELECT * FROM source_revisions WHERE id=?", (run.source_revision_id,)
        ).fetchone()
        if rev is None:
            raise ReviewError("Source revision mat trong DB")
        text = Path(rev[4]).read_text(encoding=rev[2])
        doc = parse_document(text)
        return run.id, doc

    def list_review(self, *, run_id: str | None = None) -> list[ReviewEntry]:
        run_id, doc = self._doc_and_blocks(run_id)
        blocks = self.state.committed_blocks(run_id)
        # route/reasons tu bang route_decisions (stage_block ghi vao day,
        # khong phai key trong qa_json)
        routes = {
            row[0]: (row[1], json.loads(row[2]))
            for row in self.state.conn.execute(
                "SELECT r.block_id, r.route, r.reasons_json FROM route_decisions r "
                "JOIN blocks b ON b.id = r.block_id WHERE b.run_id = ?",
                (run_id,),
            ).fetchall()
        }
        # map block_id -> node source
        src_by_id = {}
        for node in doc.translatable_nodes():
            src_by_id[node_block_id(node)] = node.content
        entries: list[ReviewEntry] = []
        for bid, blk in blocks.items():
            qa = json.loads(blk["qa_json"]) if blk.get("qa_json") else {}
            if not _is_reviewable(qa):
                continue
            route, reasons = routes.get(bid, (ROUTE_VIETPHRASE, []))
            entries.append(
                ReviewEntry(
                    block_id=bid,
                    chapter_ordinal=blk["chapter_ordinal"],
                    block_ordinal=blk["block_ordinal"],
                    source=src_by_id.get(bid, ""),
                    output=blk.get("final_text") or "",
                    route=route,
                    reasons=reasons,
                    invariant_errors=qa.get("invariant_errors", []),
                )
            )
        entries.sort(key=lambda e: (e.chapter_ordinal, e.block_ordinal))
        return entries

    def export_review(self, *, run_id: str | None = None, output: Path | None = None) -> Path:
        entries = self.list_review(run_id=run_id)
        run_id, doc = self._doc_and_blocks(run_id)
        if output is None:
            output = self.project / ".zhvi" / "runs" / run_id / "review.jsonl"
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("w", encoding="utf-8") as f:
            for e in entries:
                f.write(json.dumps(e.to_json(), ensure_ascii=False) + "\n")
        return output


class ReviewError(RuntimeError):
    pass
