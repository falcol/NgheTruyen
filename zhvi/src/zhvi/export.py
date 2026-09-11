"""Atomic export (thiet ke muc 30/32).

Chi export khi moi block COMMITTED, count/order khop source. Dung lai TXT tu
structural nodes + final_text cua translatable nodes — khong noi chuoi tuy tien.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import PARSER_VERSION, PIPELINE_VERSION, QA_VERSION, SEGMENTER_VERSION
from .fsutil import atomic_write as fsutil_atomic_write
from .document import Document
from .project import Project, default_output_path
from .state import RunRow, State


class ExportFailure(RuntimeError):
    pass


class IntegrityFailure(RuntimeError):
    """code: duplicate_ids | missing_blocks | newline_mismatch | integrity."""

    def __init__(self, message: str, *, code: str = "integrity") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ExportResult:
    path: Path
    sha256: str
    manifest_path: Path


def build_output(doc: Document, blocks_by_id: dict[str, dict]) -> str:
    """Rebuild toan bo document: node nao co block committed -> thay final_text."""
    out: list[str] = []
    for node in doc.nodes:
        if not node.is_translatable:
            out.append(node.raw_text)
            continue
        block = blocks_by_id.get(node_block_id(node))
        if block is None or block["final_text"] is None:
            raise ExportFailure(f"Block thieu/khong commit: {node_block_id(node)}")
        out.append(node.prefix + block["final_text"] + node.suffix)
    return "".join(out)


def node_block_id(node) -> str:
    """segment_id = chapter_ordinal + block_ordinal trong chapter (muc 8)."""
    return f"c{node.chapter_id}b{node.ordinal}"


def verify_output(doc: Document, output: str, blocks_by_id: dict[str, dict]) -> None:
    """Hard checks truoc khi publish (muc 30): block khong thieu/nhan doi/reorder."""
    src_nodes = doc.translatable_nodes()
    expected_ids = [node_block_id(n) for n in src_nodes]
    if len(expected_ids) != len(set(expected_ids)):
        raise IntegrityFailure(
            "Block ID trung lap — loi danh danh", code="duplicate_ids"
        )
    missing = [bid for bid in expected_ids if bid not in blocks_by_id or blocks_by_id[bid]["final_text"] is None]
    if missing:
        raise IntegrityFailure(
            f"Thieu {len(missing)} block committed, dau: {missing[:3]}",
            code="missing_blocks",
        )
    if output.count("\n") != doc.normalized_text.count("\n"):
        raise IntegrityFailure(
            "So newline khong khop — co the mat/reorder dong",
            code="newline_mismatch",
        )


def atomic_write(destination: Path, content: bytes) -> str:
    """Temp cung filesystem, fsync, os.replace, fsync dir (muc 30).
    Story 2.4: thuc the dung lai o fsutil (kem ownership guard)."""
    return fsutil_atomic_write(destination, content)


def write_manifest(project: Project, run: RunRow, output: Path, digest: str, report: dict) -> Path:
    manifest = {
        "tool_version": PIPELINE_VERSION,
        "schema_versions": {"parser": PARSER_VERSION, "segmenter": SEGMENTER_VERSION, "qa": QA_VERSION},
        "source": json.loads(run.resolved_config_json).get("_source", {}),
        "run_id": run.id,
        "fingerprint": run.fingerprint,
        "dictionary_revision": run.dictionary_revision_id,
        "resolved_config": run.resolved_config,
        "output": {"path": str(output), "sha256": digest},
        "totals": {
            "blocks": report.get("blocks"),
            "vp_ratio": report.get("vp_ratio"),
            "warnings": report.get("warnings"),
            "elapsed_s": report.get("elapsed_s"),
        },
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    path = project.runs_dir / run.id / "manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def export_run(
    project: Project,
    *,
    output: Path | None = None,
    run_id: str | None = None,
    replace_existing: bool = False,
    source_text: str | None = None,
    doc: Document | None = None,
) -> ExportResult:
    """Export RUN_ID (mac dinh: run hoan tat gan nhat) -> TXT atomic."""
    st = State(project.db_path)
    if run_id is not None:
        run = st.get_run(run_id)
    else:
        run = st.latest_run()
        if run is None:
            raise ExportFailure("Chua co run nao")
    if run.status not in ("completed", "exported"):
        raise ExportFailure(f"Run {run.id[:8]} chua hoan tat (status={run.status})")

    if doc is None:
        rev = st.conn.execute(
            "SELECT * FROM source_revisions WHERE id=?", (run.source_revision_id,)
        ).fetchone()
        if rev is None:
            raise IntegrityFailure("Source revision mat trong DB")
        from .document import parse_document

        text = source_text if source_text is not None else Path(rev[4]).read_text(encoding=rev[2])
        doc = parse_document(text)

    blocks = st.committed_blocks(run.id)
    content = build_output(doc, blocks)
    verify_output(doc, content, blocks)
    data = content.encode("utf-8")

    dest = output or default_output_path(project, None)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() and not replace_existing:
            existing = dest.read_bytes()
            if hashlib.sha256(existing).hexdigest() == hashlib.sha256(data).hexdigest():
                digest = hashlib.sha256(data).hexdigest()
            else:
                raise ExportFailure(
                    f"Output da ton tai va khac noi dung: {dest} — dung --replace de ghi de"
                )
        else:
            digest = atomic_write(dest, data)
    except OSError as e:
        raise ExportFailure(f"Ghi output that bai ({dest}): {e}") from e

    report = {"blocks": len(blocks)}
    manifest_path = write_manifest(project, run, dest, digest, report)
    if run.status != "exported":
        st.set_run_status(run.id, "exported")
    return ExportResult(path=dest, sha256=digest, manifest_path=manifest_path)
