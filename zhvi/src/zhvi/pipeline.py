"""Core orchestration M1 — VP-only (thiet ke muc 9/37 ban don gian hoa).

translate_project: preflight -> snapshot -> parse -> freeze glossary ->
fingerprint -> resume/create run -> VP lattice tung block -> commit SQLite ->
atomic export -> bao cao. Khong goi model. Ctrl-C lan 1: checkpoint + PAUSED.
"""
from __future__ import annotations

import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from .config import (
    PARSER_VERSION,
    QA_VERSION,
    ROUTE_VIETPHRASE,
    SEGMENTER_VERSION,
    Config,
    resolve_config,
)
from .document import parse_document
from .export import ExportResult, export_run
from .fingerprint import block_source_hash, build_run_fingerprint, glossary_file_hash
from .project import Project, create_project, project_lock, workspace_for
from .qa import sanitize_source
from .quality.invariants import run_invariants
from .snapshot import SourceRevision, import_snapshot
from .state import State
from .vietphrase.lattice import vp_plan
from .vietphrase.loader import dict_files_fingerprint, load_dictionary


class RunFailure(RuntimeError):
    pass


class PreflightFailure(RuntimeError):
    pass


@dataclass
class TranslateRequest:
    source: Path | None = None
    output: Path | None = None
    style: str = "convert-qt"
    encoding: str = "utf-8"
    dict_dir: str | None = None


@dataclass
class PipelineResult:
    run_id: str
    exit_code: int
    report: dict = field(default_factory=dict)
    output: ExportResult | None = None


def _resolve_dict_dir(cfg: Config) -> Path:
    p = Path(cfg.dict_dir)
    if not p.is_absolute():
        # duong dan tu repo: tim tu cwd hoac tu vi tri goi len
        for base in (Path.cwd(), Path(__file__).resolve().parents[3]):
            cand = base / cfg.dict_dir
            if cand.is_dir():
                p = cand
                break
    if not p.is_dir():
        raise PreflightFailure(f"Khong tim thay thu muc tu dien: {cfg.dict_dir}")
    return p


def _resolve_global_glossary(cfg: Config) -> Path | None:
    """Glossary chuan toan cuc (~/.config/zhvi/), tuy chon. Rong -> bo qua."""
    raw = cfg.global_glossary.strip()
    if not raw:
        return None
    p = Path(raw).expanduser()
    return p if p.is_file() else None


def _freeze_glossary(project: Project) -> tuple[str, Path]:
    """Snapshot glossary.manual.tsv bat bien cho run (muc 1 nguyen tac 4)."""
    src = project.manual_glossary
    h = glossary_file_hash(src)
    dest = project.dictionaries_dir / f"{h}.tsv"
    if not dest.exists() and src.is_file():
        tmp = dest.with_suffix(".tmp")
        shutil.copyfile(src, tmp)
        tmp.replace(dest)
    return h, dest


def translate_project(project: Project, request: TranslateRequest) -> PipelineResult:
    cfg = resolve_config(project.root, dict_dir=request.dict_dir)
    cfg = resolve_dict_overrides(cfg, request)
    dict_dir = _resolve_dict_dir(cfg)

    with project_lock(project):
        return _translate_locked(project, request, cfg, dict_dir)


def resolve_dict_overrides(cfg: Config, request: TranslateRequest) -> Config:
    from dataclasses import replace

    overrides: dict = {}
    if request.style and request.style != cfg.style:
        overrides["style"] = request.style
    if request.encoding and request.encoding != cfg.encoding:
        overrides["encoding"] = request.encoding
    return replace(cfg, **overrides) if overrides else cfg


def _translate_locked(
    project: Project, request: TranslateRequest, cfg: Config, dict_dir: Path
) -> PipelineResult:
    t0 = time.monotonic()

    # 1. snapshot
    if request.source is None:
        raise RunFailure("Thieu file source")
    rev: SourceRevision = import_snapshot(project, request.source, encoding=cfg.encoding)

    # 2. parse
    text = Path(rev.snapshot_path).read_text(encoding=rev.encoding)
    doc = parse_document(text, chapter_detection=cfg.chapter_detection, chapter_regex=cfg.chapter_regex)

    # 3. dictionary + glossary freeze
    glossary_hash, _ = _freeze_glossary(project)
    global_glossary = _resolve_global_glossary(cfg)
    dict_fp = dict_files_fingerprint(dict_dir, project.manual_glossary, global_glossary, cfg.pattern_rules)
    cache_path = project.cache_dir / f"dict-{dict_fp[:16]}.pkl"
    dic = load_dictionary(
        dict_dir,
        manual_glossary=project.manual_glossary,
        global_glossary=global_glossary,
        cache_path=cache_path,
        patterns=cfg.pattern_rules,
    )

    # 4. fingerprint + run
    fingerprint = build_run_fingerprint(
        source_revision_hash=rev.id,
        encoding=rev.encoding,
        dictionary_fingerprint=dict_fp,
        book_glossary_hash=glossary_hash,
        cfg=cfg,
    )
    st = State(project.db_path)
    st.upsert_source_revision(rev.id, rev.content_hash, rev.encoding, rev.byte_size, str(rev.snapshot_path))
    done = st.find_completed_run(fingerprint)
    if done is not None:
        # no-op: cung fingerprint da hoan thanh (muc 3.1)
        out = request.output or (project.dist_dir / "book.vi.txt")
        if out.exists():
            return PipelineResult(
                run_id=done.id,
                exit_code=0,
                report={
                    "run_id": done.id,
                    "noop": True,
                    "blocks": st.block_count(done.id, "committed"),
                    "vp_ratio": 1.0,
                    "warnings": 0,
                    "elapsed_s": 0.0,
                    "output": str(out),
                },
            )
    run, created = st.resume_or_create(
        run_id=uuid.uuid4().hex,
        fingerprint=fingerprint,
        source_revision_id=rev.id,
        dictionary_revision_id=dict_fp,
        resolved_config={**cfg.to_dict(), "_source": {"path": str(request.source), "revision": rev.id}},
    )

    # 5. VP plan tung block -> invariant gate -> stage_block (VP-only, story 1.1)
    committed = st.committed_blocks(run.id)
    nodes = doc.translatable_nodes()
    total = len(nodes)
    n_committed = len(committed)
    n_warnings = 0
    from .progress import Progress

    prog = Progress(total)
    try:
        for i, node in enumerate(nodes):
            bid = f"c{node.chapter_id}b{node.ordinal}"
            src_hash = block_source_hash(node.content)
            vp_input, qa_rules = (
                sanitize_source(node.content) if cfg.qa_strip_junk else (node.content, [])
            )
            prev = committed.get(bid)
            if prev and prev["source_hash"] == src_hash:
                continue  # tai dung block da commit trong run (muc 3.1 resume)
            # Block cache theo AD-11: source block hash + dictionary revision +
            # parser/segmenter/QA version + config anh huong preprocessing.
            cache_key = block_source_hash(
                f"{src_hash}\x1f{dict_fp}\x1f{PARSER_VERSION}\x1f{SEGMENTER_VERSION}"
                f"\x1f{QA_VERSION}\x1f{int(cfg.collapse_repetitions)}\x1f{int(cfg.qa_strip_junk)}"
            )
            cached = st.cache_lookup(cache_key)
            if cached is not None:
                draft_text = cached["final_text"]
                qa = cached["qa"]
                n_warnings += len(qa.get("warnings", ()))
                st.stage_block(
                    run_id=run.id, block_id=bid, chapter_ordinal=node.chapter_id,
                    block_ordinal=i, source_start=node.char_start, source_end=node.char_end,
                    source_hash=src_hash, final_text=draft_text, qa=qa,
                    route=ROUTE_VIETPHRASE, reasons=["CACHE_HIT"], features={},
                    router_version="none",
                    attempt={"id": uuid.uuid4().hex, "engine": "cache", "input_hash": src_hash,
                             "status": "ok", "duration_ms": 0},
                    cache_key=cache_key,
                )
                n_committed += 1
                prog.update(i + 1, n_committed, n_warnings)
                continue
            draft = vp_plan(
                dic,
                vp_input,
                beam=cfg.lattice_beam,
                occurrence_prefix=bid,
                collapse_reps=cfg.collapse_repetitions,
            )

            # VP-only (story 1.1): moi block di direct VP, khong router/agent.
            n_warnings += len(draft.warnings) + len(qa_rules)

            final_text = draft.text
            attempt = {
                "id": uuid.uuid4().hex,
                "engine": "vietphrase-lattice",
                "input_hash": src_hash,
                "status": "ok",
            }

            # Invariant gate (hard checks). No qi: cjk_allowlist rong.
            inv = run_invariants(source=vp_input, output=final_text, block_id=bid)
            if not inv.ok:
                # Khong con engine fallback -> giu VP draft, ghi NEEDS_REVIEW.
                n_warnings += len(inv.errors)
                attempt["status"] = "failed"
                attempt["error"] = f"INVARIANT:{','.join(inv.errors)}"

            qa = {
                "unknown_spans": len(draft.unknown_spans),
                "single_char_ratio": round(draft.single_char_ratio, 4),
                "lattice_margin": round(draft.lattice_margin, 4),
                "lattice_entropy": round(draft.lattice_entropy, 4),
                "coverage": round(draft.coverage, 4),
                "warnings": [*qa_rules, *draft.warnings],
                "invariant_errors": list(inv.errors),
            }
            st.stage_block(
                run_id=run.id,
                block_id=bid,
                chapter_ordinal=node.chapter_id,
                block_ordinal=i,
                source_start=node.char_start,
                source_end=node.char_end,
                source_hash=src_hash,
                final_text=final_text,
                qa=qa,
                route=ROUTE_VIETPHRASE,
                reasons=[*qa_rules, *draft.warnings],
                features={},
                router_version="none",
                attempt=attempt,
                cache_key=cache_key,
            )
            n_committed += 1
            prog.update(i + 1, n_committed, n_warnings)
    except KeyboardInterrupt:
        prog.finish()
        st.set_run_status(run.id, "paused")
        # Dem tu DB (route_decisions) — dung cho block staged truoc interrupt.
        routes = st.route_counts(run.id)
        vp_ratio = routes.get(ROUTE_VIETPHRASE, 0) / total if total else 1.0
        st.close()
        return PipelineResult(
            run_id=run.id,
            exit_code=130,
            report={"run_id": run.id, "paused": True, "blocks": n_committed,
                    "vp_ratio": round(vp_ratio, 4), "warnings": n_warnings,
                    "elapsed_s": time.monotonic() - t0, "output": None,
                    "routes": routes},
        )

    # 6. export
    st.set_run_status(run.id, "completed")
    out_path = request.output or (project.dist_dir / "book.vi.txt")
    result = export_run(
        project,
        output=out_path,
        run_id=run.id,
        replace_existing=True,
        source_text=text,
        doc=doc,
    )
    # Metric routes tu DB: block cache-hit / nap lai tu run interrupted cung
    # co row route_decisions — dem local trong loop se bo sot chung.
    routes = st.route_counts(run.id)
    st.close()
    elapsed = time.monotonic() - t0
    vp_ratio = routes.get(ROUTE_VIETPHRASE, 0) / total if total else 1.0
    report = {
        "run_id": run.id,
        "noop": False,
        "blocks": total,
        "vp_ratio": round(vp_ratio, 4),
        "warnings": n_warnings,
        "elapsed_s": round(elapsed, 2),
        "chars_per_s": round(len(text) / elapsed) if elapsed > 0 else None,
        "output": str(result.path),
        "sha256": result.sha256,
        "routes": routes,
    }
    return PipelineResult(run_id=run.id, exit_code=0, report=report, output=result)


def ensure_project_for_source(source: Path, project: Path | None) -> Project:
    if project is not None:
        return create_project(project)
    return create_project(workspace_for(source))
