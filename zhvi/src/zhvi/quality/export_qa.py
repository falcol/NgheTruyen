"""Document-level QA truoc export (story 5.1, CAP-7).

QA chi pass hoac chan — khong sua output_text. Fail -> caller dat
needs_dictionary_fix, khong goi export_run.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from zhvi.document import Document
from zhvi.export import IntegrityFailure, verify_output
from zhvi.project import Project
from zhvi.projection import read_bundle_entries
from zhvi.quality.chapter_audit import entity_alias_consistency
from zhvi.quality.invariants import CJK_RE
from zhvi.state import State
from zhvi.vietphrase.layers import Layer

PLACEHOLDER_MARKERS = ("__ZHVI", "\ufffc")
REPEATED_RE = re.compile(r"(\S{2,})\1")


class QaFailure(RuntimeError):
    """Export bi chan boi structural QA."""


@dataclass
class ExportQaResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)


def run_export_qa(
    doc: Document,
    output_text: str,
    blocks_by_id: dict[str, dict],
    *,
    entity_targets: dict[str, set[str]] | None = None,
) -> ExportQaResult:
    """Kiem document-level. Khong mutate output_text."""
    errors: list[str] = []
    try:
        verify_output(doc, output_text, blocks_by_id)
    except IntegrityFailure as e:
        errors.append(getattr(e, "code", None) or "integrity")
    if any(m in output_text for m in PLACEHOLDER_MARKERS):
        errors.append("placeholder")
    if CJK_RE.search(output_text):
        errors.append("leftover_cjk")
    if REPEATED_RE.search(output_text):
        errors.append("repeated_artifact")
    if entity_targets:
        blocks = [
            {"block_id": bid, "output": b.get("final_text") or ""}
            for bid, b in blocks_by_id.items()
        ]
        findings = entity_alias_consistency(0, blocks, entity_targets=entity_targets)
        if findings:
            errors.append("entity_drift")
    return ExportQaResult(ok=not errors, errors=errors)


def _parse_qa(block: dict) -> dict:
    raw = block.get("qa_json") or block.get("qa") or "{}"
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}


def collect_block_metrics(blocks_by_id: dict[str, dict]) -> dict:
    n = 0
    cov = 0.0
    unknown = 0
    single = 0.0
    for block in blocks_by_id.values():
        qa = _parse_qa(block)
        n += 1
        cov += float(qa.get("coverage") or 0.0)
        unknown += int(qa.get("unknown_spans") or 0)
        single += float(qa.get("single_char_ratio") or 0.0)
    return {
        "coverage_spans": round(cov / n, 4) if n else 1.0,
        "unknown_spans": unknown,
        "single_char_ratio": round(single / n, 4) if n else 0.0,
        "fragmentation": round(single / n, 4) if n else 0.0,
    }


def build_run_report(
    *,
    state: State,
    project: Project,
    run_id: str,
    dictionary_revision_id: str,
    source_len: int,
    elapsed_s: float,
    sha256: str | None,
    output: str | None,
    qa: ExportQaResult | None,
    extra: dict | None = None,
    output_chars: int = 0,
) -> dict:
    """Metric roi, khong quality score (AC 5.1 #2)."""
    blocks = state.committed_blocks(run_id)
    metrics = collect_block_metrics(blocks)
    src_chars = source_len
    coverage_chars = round(output_chars / src_chars, 4) if src_chars else 1.0
    cur = state.conn.execute(
        "SELECT status, COUNT(*) FROM term_candidates WHERE book_id=? "
        "GROUP BY status",
        (project.book_id,),
    )
    candidates = {row[0]: row[1] for row in cur.fetchall()}
    auto_n = 0
    try:
        auto_n = sum(
            1
            for parts in read_bundle_entries(project, dictionary_revision_id)
            if len(parts) >= 4 and parts[0] == str(int(Layer.BOOK_AUTO))
        )
    except (OSError, RuntimeError):
        auto_n = 0
    regression = "fail" if qa is not None and not qa.ok else (
        "pass" if sha256 else "n/a"
    )
    report = {
        "run_id": run_id,
        "dictionary_revision_id": dictionary_revision_id,
        "coverage_chars": coverage_chars,
        "coverage_spans": metrics["coverage_spans"],
        "unknown_spans": metrics["unknown_spans"],
        "single_char_ratio": metrics["single_char_ratio"],
        "fragmentation": metrics["fragmentation"],
        "candidates": candidates,
        "auto_entries": auto_n,
        "affected_blocks": [],
        "regression": regression,
        "sha256": sha256,
        "elapsed_s": round(elapsed_s, 2),
        "chars_per_s": round(src_chars / elapsed_s) if elapsed_s > 0 else None,
        "output": output,
    }
    if qa is not None:
        report["qa"] = {"ok": qa.ok, "errors": qa.errors}
    if extra:
        report.update(extra)
    return report
