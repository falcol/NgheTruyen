"""zhvi CLI (thiet ke muc 3/4). Typer app; log o stderr, JSON o stdout."""
from __future__ import annotations

import json
import sys
from difflib import SequenceMatcher, unified_diff
from pathlib import Path
from typing import TYPE_CHECKING

import typer
from rich.console import Console

from . import __version__
from .config import Config, resolve_config
from .correction import affected_block_ids, diff_revisions, rollback_revision
from .document import parse_document
from .learning.candidate import build_candidates
from .learning.discovery import run_discovery
from .learning.evidence import evaluate_candidates
from .learning.explain import explain_text
from .learning.promotion import PromotionError, revoke_book_auto, run_promotion
from .learning.terms import (
    TermsError,
    accept_term,
    audit_usage,
    list_terms,
    reject_term,
)
from .pipeline import ensure_book_dictionary, resolve_dict_dir
from .project import (
    Project,
    ProjectError,
    create_project,
    open_project,
    project_lock,
    workspace_for,
)
from .projection import reconcile_project
from .revision import (
    StaleActiveError,
    gc_orphan_revisions,
    load_revision_dictionary,
)
from .review import ReviewError, ReviewStore
from .snapshot import SnapshotError, import_snapshot
from .state import State

if TYPE_CHECKING:  # annotation-only — pipeline keo engines nang o import-time
    from .pipeline import PipelineResult

app = typer.Typer(
    name="zhvi",
    help="CLI dich truyen Trung -> Viet (VietPhrase-first, co state, resumable).",
    no_args_is_help=True,
)
err_console = Console(stderr=True)

dict_app = typer.Typer(help="Vong loi dictionary revision (gc; diff/rollback o story 2.5).")
app.add_typer(dict_app, name="dict")


@dict_app.command("gc")
def dict_gc(
    project: Path = typer.Option(..., "--project", "-p"),
) -> None:
    """Don dir tam (.tmp-*) va bundle orphan (rename ma chua commit DB)."""
    try:
        removed = gc_orphan_revisions(open_project(project))
    except (ProjectError, OSError) as e:
        _fail(EXIT_STATE, str(e))
    print(json.dumps({"removed": removed}, ensure_ascii=False))


@dict_app.command("diff")
def dict_diff(
    rev_a: str = typer.Argument(..., help="Revision A (id)."),
    rev_b: str = typer.Argument(..., help="Revision B (id)."),
    project: Path = typer.Option(..., "--project", "-p"),
) -> None:
    """Diff 2 revision: entry them/mat/doi + affected keys va affected blocks
    (source index cua run cuoi — story 2.5)."""
    try:
        proj = open_project(project)
        payload = diff_revisions(proj, rev_a, rev_b)
        payload["affected_blocks"] = _affected_blocks_for_diff(proj, rev_b, payload)
    except (ProjectError, OSError) as e:
        _fail(EXIT_STATE, str(e))
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def _affected_blocks_for_diff(proj: Project, rev_b: str, payload: dict) -> list[str]:
    """Affected blocks tinh tren source cua run cuoi cung project (trace/source
    index — AC 2.5); chua co run -> danh sach rong."""
    keys = set(payload.get("affected_keys") or [])
    if not keys:
        return []
    st = State(proj.db_path)
    try:
        rev = st.latest_source_revision()
    finally:
        st.close()
    if rev is None:
        return []
    doc = parse_document(Path(rev.snapshot_path).read_text(encoding=rev.encoding))
    trad = load_revision_dictionary(proj, rev_b).trad_simp
    return affected_block_ids(doc, keys, trad)


@dict_app.command("rollback")
def dict_rollback(
    rev: str = typer.Argument(..., help="Revision an toan can active lai."),
    project: Path = typer.Option(..., "--project", "-p"),
) -> None:
    """CAS active pointer ve revision an toan — khong sua revision cu (AD-12)."""
    try:
        rollback_revision(open_project(project), rev)
    except StaleActiveError as e:
        _fail(EXIT_RUN_FAILED, str(e))
    except (ProjectError, OSError, RuntimeError) as e:
        _fail(EXIT_STATE, str(e))
    print(json.dumps({"active": rev}, ensure_ascii=False))


# ---- terms (story 3.5) ----

terms_app = typer.Typer(help="Candidate/auto entry lifecycle cua truyen.")
app.add_typer(terms_app, name="terms")


def _terms_state(project: Path):
    p = open_project(project)
    return p, State(p.db_path)


@terms_app.command("list")
def terms_list(
    project: Path = typer.Option(..., "--project", "-p"),
    dict_dir: str = typer.Option(None, "--dict-dir"),
    status: str = typer.Option(None, "--status", help="Loc theo trang thai."),
) -> None:
    """Hien candidate + evidence + trang thai (story 3.5)."""
    try:
        p, st = _terms_state(project)
        try:
            terms = list_terms(st, book_id=p.book_id, status=status)
            # Usage audit read-only — khong can project lock (AD-13 chi buoc
            # cho mutation).
            audit_usage(st, action="terms_list")
        finally:
            st.close()
    except ProjectError as e:
        _fail(EXIT_STATE, str(e))
    except Exception as e:  # noqa: BLE001 — controller bat fatal
        _fail(EXIT_RUN_FAILED, f"{type(e).__name__}: {e}")
    print(json.dumps(terms, ensure_ascii=False, indent=2))


@terms_app.command("accept")
def terms_accept(
    source: str = typer.Argument(..., help="Candidate source key (NFC gian the)."),
    project: Path = typer.Option(..., "--project", "-p"),
    dict_dir: str = typer.Option(None, "--dict-dir"),
) -> None:
    """Accept candidate: tao manual entry (manual thang auto tu do)."""
    try:
        p, st = _terms_state(project)
        try:
            cfg = resolve_config(p.root, dict_dir=dict_dir)
            with project_lock(p):
                revision, target = accept_term(
                    st,
                    project=p,
                    dict_dir=resolve_dict_dir(cfg),
                    cfg=cfg,
                    source=source,
                )
        finally:
            st.close()
    except typer.Exit:
        raise
    except StaleActiveError as e:
        _fail(EXIT_RUN_FAILED, str(e))
    except (TermsError, PromotionError) as e:
        _fail(EXIT_STATE, str(e))
    except (ProjectError, OSError) as e:
        _fail(EXIT_STATE, str(e))
    except Exception as e:  # noqa: BLE001 — controller bat fatal
        _fail(EXIT_RUN_FAILED, f"{type(e).__name__}: {e}")
    print(
        json.dumps(
            {
                "source": source,
                "target": target,
                "status": "accepted",
                "revision": revision,
                "manual_glossary": str(p.root / "glossary.manual.tsv"),
            },
            ensure_ascii=False,
        )
    )


@terms_app.command("reject")
def terms_reject(
    source: str = typer.Argument(...),
    project: Path = typer.Option(..., "--project", "-p"),
) -> None:
    """Reject candidate: ghi audit event, status rejected."""
    try:
        p, st = _terms_state(project)
        try:
            with project_lock(p):
                reject_term(st, book_id=p.book_id, source=source)
        finally:
            st.close()
    except typer.Exit:
        raise
    except TermsError as e:
        _fail(EXIT_STATE, str(e))
    except ProjectError as e:
        _fail(EXIT_STATE, str(e))
    except Exception as e:  # noqa: BLE001 — controller bat fatal
        _fail(EXIT_RUN_FAILED, f"{type(e).__name__}: {e}")
    print(json.dumps({"source": source, "status": "rejected"}, ensure_ascii=False))


@terms_app.command("revoke")
def terms_revoke(
    source: str = typer.Argument(...),
    project: Path = typer.Option(..., "--project", "-p"),
    dict_dir: str = typer.Option(None, "--dict-dir"),
) -> None:
    """Bo book-auto entry khoi active revision (revision moi, AD-12)."""
    try:
        p, st = _terms_state(project)
        try:
            cfg = resolve_config(p.root, dict_dir=dict_dir)
            with project_lock(p):
                revision = revoke_book_auto(
                    st,
                    project=p,
                    dict_dir=resolve_dict_dir(cfg),
                    source=source,
                    actor="user",
                )
                audit_usage(st, action="terms_revoke")
        finally:
            st.close()
    except typer.Exit:
        raise
    except StaleActiveError as e:
        _fail(EXIT_RUN_FAILED, str(e))
    except PromotionError as e:
        _fail(EXIT_STATE, str(e))
    except (ProjectError, OSError) as e:
        _fail(EXIT_STATE, str(e))
    except Exception as e:  # noqa: BLE001 — controller bat fatal
        _fail(EXIT_RUN_FAILED, f"{type(e).__name__}: {e}")
    print(
        json.dumps(
            {"source": source, "status": "revoked", "revision": revision},
            ensure_ascii=False,
        )
    )


@app.command()
def explain(
    text: str = typer.Argument(..., help="Doan text ZH can explain."),
    project: Path = typer.Option(..., "--project", "-p"),
    dict_dir: str = typer.Option(None, "--dict-dir"),
) -> None:
    """Explain segmentation + provenance tung span (story 3.5)."""
    try:
        p, st = _terms_state(project)
        try:
            cfg = resolve_config(p.root, dict_dir=dict_dir)
            payload = explain_text(
                st,
                project=p,
                dict_dir=resolve_dict_dir(cfg),
                cfg=cfg,
                text=text,
            )
        finally:
            st.close()
    except typer.Exit:
        raise
    except ProjectError as e:
        _fail(EXIT_STATE, str(e))
    except Exception as e:  # noqa: BLE001 — controller bat fatal
        _fail(EXIT_RUN_FAILED, f"{type(e).__name__}: {e}")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


# Exit codes (muc 34)
EXIT_OK = 0
EXIT_USAGE = 2
EXIT_INPUT = 3
EXIT_PREFLIGHT = 4
EXIT_STATE = 5
EXIT_RUN_FAILED = 6
EXIT_REVIEW = 7
EXIT_EXPORT = 8
EXIT_INTEGRITY = 9
EXIT_INTERRUPT = 130


def _fail(code: int, message: str) -> None:
    err_console.print(f"[red]error:[/red] {message}")
    raise typer.Exit(code=code)


def _load_project(project_dir: Path | None, source: Path | None) -> Project:
    if project_dir is not None:
        return open_project(project_dir)
    if source is not None:
        ws = workspace_for(source)
        if ws.exists():
            return open_project(ws)
        return create_project(ws)
    raise typer.Exit(code=EXIT_USAGE)


@app.callback()
def _main(
    version: bool = typer.Option(False, "--version", "-V", help="In phien ban va thoat."),
) -> None:
    if version:
        print(f"zhvi {__version__}")
        raise typer.Exit(EXIT_OK)


@app.command()
def init(
    project: Path = typer.Argument(..., help="Thu muc project (se tao .zhvi/ ben trong)."),
) -> None:
    """Tao project moi cho mot truyen."""
    p = create_project(project)
    err_console.print(f"Da tao project: {p.root}")


@app.command()
def import_(
    file: Path = typer.Argument(..., help="File TXT nguon (zh)."),
    project: Path = typer.Option(None, "--project", "-p"),
    encoding: str = typer.Option("utf-8", "--encoding"),
    as_source: bool = typer.Option(False, "--update", help="Nhan la source cua project."),
) -> None:
    """Snapshot an toàn file TXT vao project."""
    try:
        p = _load_project(project, file)
        rev = import_snapshot(p, file, encoding=encoding)
    except (ProjectError, SnapshotError) as e:
        _fail(EXIT_INPUT, str(e))
    # Ghi row source_revisions ngay luc import (story 3.1: discover doc
    # source revision da import tu DB, khong phai sau translate). AD-13:
    # ghi book state duoi cung project lock nhu translate/discover.
    st = State(p.db_path)
    try:
        with project_lock(p):
            st.upsert_source_revision(
                rev.id,
                rev.content_hash,
                rev.encoding,
                rev.byte_size,
                str(rev.snapshot_path),
            )
    finally:
        st.close()
    print(json.dumps({"source_revision": rev.id, "byte_size": rev.byte_size, "encoding": rev.encoding}))


@app.command()
def inspect(
    project: Path = typer.Option(None, "--project", "-p"),
    source: Path = typer.Option(None, "--source", help="TXT truc tiep (khong can project)."),
    sample: int = typer.Option(200, "--sample", help="Ki tra ky nuong dau/cuoi."),
) -> None:
    """Bao cao cau truc document (muc 7)."""
    from .document import inspect_document, parse_document

    try:
        if source is not None:
            text = source.read_text(encoding="utf-8")
        else:
            if project is None:
                _fail(EXIT_USAGE, "Can --project hoac --source")
            p = open_project(project)
            from .state import State

            st = State(p.db_path)
            rev = _require_latest_source(st)
            text = Path(rev.snapshot_path).read_text(encoding=rev.encoding)
    except (ProjectError, OSError, SnapshotError) as e:
        _fail(EXIT_INPUT, str(e))
    doc = parse_document(text)
    rep = inspect_document(doc)
    print(json.dumps(rep.__dict__, ensure_ascii=False, indent=2))


@app.command()
def discover(
    project: Path = typer.Option(..., "--project", "-p"),
    dict_dir: str = typer.Option(None, "--dict-dir"),
) -> None:
    """Discovery toan truyen: thu n-gram observation vao book SQLite (story 3.1)."""
    try:
        p, st, rev, cfg, drev, dic = _learn_context(project, dict_dir)
        try:
            # AD-13: mot writer cho book state — dung chung lock translate.
            with project_lock(p):
                summary = run_discovery(
                    st,
                    source_revision=rev,
                    dictionary=dic,
                    dictionary_revision_id=drev,
                )
        finally:
            st.close()
    except typer.Exit:
        raise
    except ProjectError as e:
        _fail(EXIT_STATE, str(e))
    except Exception as e:  # noqa: BLE001 — controller bat fatal
        _fail(EXIT_RUN_FAILED, f"{type(e).__name__}: {e}")
    print(json.dumps(summary.to_json(), ensure_ascii=False, indent=2))


@app.command()
def learn(
    project: Path = typer.Option(..., "--project", "-p"),
    dict_dir: str = typer.Option(None, "--dict-dir"),
) -> None:
    """Hoc theo truyen: discovery -> candidate builder (AD-4; story 3.2).

    Discovery idempotent (replace-not-append) nen chay lai an toan.
    Composite mo rong dan theo epic 3 (evaluate/promotion o story sau).
    """
    try:
        p, st, rev, cfg, drev, dic = _learn_context(project, dict_dir)
        try:
            with project_lock(p):
                disc = run_discovery(
                    st,
                    source_revision=rev,
                    dictionary=dic,
                    dictionary_revision_id=drev,
                )
                cand = build_candidates(
                    st,
                    book_id=p.book_id,
                    dictionary=dic,
                    dictionary_revision_id=drev,
                    source_revision_id=rev.id,
                    min_occurrences=cfg.learning.min_name_occurrences,
                )
                ev = evaluate_candidates(
                    st,
                    book_id=p.book_id,
                    dictionary=dic,
                    dictionary_revision_id=drev,
                )
                promo = None
                if cfg.learning.enabled and cfg.learning.auto_scope == "book":
                    promo = run_promotion(
                        st,
                        project=p,
                        dict_dir=resolve_dict_dir(cfg),
                        cfg=cfg,
                        dictionary_revision_id=drev,
                    )
        finally:
            st.close()
    except typer.Exit:
        raise
    except StaleActiveError as e:
        _fail(EXIT_RUN_FAILED, str(e))
    except ProjectError as e:
        _fail(EXIT_STATE, str(e))
    except Exception as e:  # noqa: BLE001 — controller bat fatal
        _fail(EXIT_RUN_FAILED, f"{type(e).__name__}: {e}")
    print(
        json.dumps(
            {
                "discovery": disc.to_json(),
                "candidates": cand.to_json(),
                "evidence": ev.to_json(),
                "promotion": promo.to_json() if promo else None,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


@app.command()
def translate(
    file: Path = typer.Argument(None, help="TXT nguon (happy path 1 lenh)."),
    output: Path = typer.Option(None, "-o", "--output"),
    project: Path = typer.Option(None, "--project", "-p"),
    style: str = typer.Option("convert-qt", "--style"),
    encoding: str = typer.Option("utf-8", "--encoding"),
    dict_dir: str = typer.Option(None, "--dict-dir"),
    refresh_revision: bool = typer.Option(
        False, "--refresh-revision",
        help="Correction (story 2.5): glossary doi -> revision moi + dich lai affected blocks.",
    ),
    json_out: bool = typer.Option(False, "--json", help="Bao cao JSON tren stdout."),
) -> None:
    """Happy path: snapshot -> parse -> VP -> checkpoint -> atomic export."""
    from .pipeline import TranslateRequest, translate_project

    try:
        if file is None and project is None:
            _fail(EXIT_USAGE, "Can file TXT hoac --project")
        p = _load_project(project, file)
        req = TranslateRequest(
            source=file,
            output=output,
            style=style,
            encoding=encoding,
            dict_dir=dict_dir,
            refresh_revision=refresh_revision,
        )
        result = translate_project(p, req)
    except typer.Exit:
        raise
    except ProjectError as e:
        _fail(EXIT_STATE, str(e))
    except SnapshotError as e:
        _fail(EXIT_INPUT, str(e))
    except Exception as e:  # noqa: BLE001 — controller bat fatal, dich exit code
        from .export import ExportFailure, IntegrityFailure
        from .pipeline import RunFailure

        if isinstance(e, ExportFailure):
            _fail(EXIT_EXPORT, str(e))
        if isinstance(e, IntegrityFailure):
            _fail(EXIT_INTEGRITY, str(e))
        if isinstance(e, RunFailure):
            _fail(EXIT_RUN_FAILED, str(e))
        _fail(EXIT_RUN_FAILED, f"{type(e).__name__}: {e}")
    if json_out:
        print(json.dumps(result.report, ensure_ascii=False, indent=2))
    else:
        err_console.print(_summary_line(result))
    raise typer.Exit(code=result.exit_code)


def _summary_line(result: "PipelineResult") -> str:
    r = result.report
    return (
        f"run {r['run_id'][:8]} | {r['blocks']} blocks | VP {r['vp_ratio']:.0%} | "
        f"warnings {r['warnings']} | {r['elapsed_s']:.1f}s | output {r['output']}"
    )


def _require_latest_source(st: State):
    """Guard dung chung (story 3.1): chua co source revision thi fail som."""
    rev = st.latest_source_revision()
    if rev is None:
        _fail(EXIT_STATE, "Project chua co source — chay `zhvi import` truoc.")
    return rev


def _learn_context(project: Path, dict_dir: str | None):
    """Preamble chung discover/learn (review 3.2): guard som + dictionary active.

    Caller lo dong State (st.close) va project_lock.
    """
    p = open_project(project)
    st = State(p.db_path)
    rev = _require_latest_source(st)
    cfg = resolve_config(p.root, dict_dir=dict_dir)
    dict_dir_resolved = resolve_dict_dir(cfg)
    # AD-4: LEARN chi DOC dictionary active (phase-3 chung translate).
    drev, dic = ensure_book_dictionary(p, dict_dir_resolved, cfg)
    return p, st, rev, cfg, drev, dic


@app.command()
def status(
    project: Path = typer.Option(..., "--project", "-p"),
    require_complete: bool = typer.Option(False, "--require-complete"),
) -> None:
    """Tien do run, route, cache, lloi, review."""
    try:
        p = open_project(project)
        # Story 2.4: reconciler startup — bundle thieu/hash sai la fatal.
        reconcile_project(p)
        st = State(p.db_path)
        info = st.status_info()
    except (ProjectError, OSError, RuntimeError) as e:
        _fail(EXIT_STATE, str(e))
    print(json.dumps(info, ensure_ascii=False, indent=2))
    if require_complete and info.get("status") != "exported":
        raise typer.Exit(code=EXIT_REVIEW)


@app.command()
def export(
    project: Path = typer.Option(..., "--project", "-p"),
    output: Path = typer.Option(None, "-o", "--output"),
    run: str = typer.Option(None, "--run", help="Run ID cu the (mac dinh: run hoan tat gan nhat)."),
    replace_existing: bool = typer.Option(False, "--replace", help="Cho phep ghi de output da ton tai."),
) -> None:
    """Dung lai TXT tu mot run da COMMITTED day du."""
    from .export import ExportFailure, IntegrityFailure, export_run

    try:
        p = open_project(project)
        out = export_run(p, output=output, run_id=run, replace_existing=replace_existing)
    except (ProjectError, SnapshotError) as e:
        _fail(EXIT_STATE, str(e))
    except ExportFailure as e:
        _fail(EXIT_EXPORT, str(e))
    except IntegrityFailure as e:
        _fail(EXIT_INTEGRITY, str(e))
    print(json.dumps({"output": str(out.path), "sha256": out.sha256}))


@app.command()
def doctor(
    project: Path = typer.Option(None, "--project", "-p"),
    dict_dir: str = typer.Option(None, "--dict-dir"),
) -> None:
    """Kiem tra tu dien, SQLite/disk, smoke test convert."""
    from .doctor import run_doctor

    cfg_dict_dir = dict_dir
    proj = None
    if project is not None:
        try:
            proj = open_project(project)
            cfg_dict_dir = cfg_dict_dir or proj.config().dict_dir
        except ProjectError:
            pass
    ok = run_doctor(err_console, Config(dict_dir=cfg_dict_dir or "crawler/vietphrase/dicts"), project=proj)
    raise typer.Exit(code=EXIT_OK if ok else EXIT_PREFLIGHT)


@app.command()
def review(
    project: Path = typer.Option(..., "--project", "-p"),
    run: str = typer.Option(None, "--run", help="Run ID cu the (mac dinh: run moi nhat)."),
    output: Path = typer.Option(None, "--output", "-o", help="File review.jsonl (mac dinh: .zhvi/runs/<run>/review.jsonl)."),
    list_only: bool = typer.Option(False, "--list", help="In ds block can review ra stdout (JSON)."),
) -> None:
    """Xem/xuat cac block can review (muc 4/23)."""
    try:
        store = ReviewStore(project)
        if list_only:
            entries = store.list_review(run_id=run)
            print(json.dumps({"count": len(entries), "entries": [e.to_json() for e in entries]},
                             ensure_ascii=False, indent=2))
        else:
            out = store.export_review(run_id=run, output=output)
            print(json.dumps({"output": str(out)}, ensure_ascii=False))
    except (ReviewError, ProjectError, OSError) as e:
        _fail(EXIT_STATE, str(e))


@app.command()
def compare(
    output: Path = typer.Argument(..., help="File output can so sanh."),
    expect: Path = typer.Argument(..., help="File chuan (reference)."),
) -> None:
    """Do gan output voi chuan: similarity ratio + so dong doi (VP-first metric)."""
    try:
        a = expect.read_text(encoding="utf-8")
        b = output.read_text(encoding="utf-8")
    except OSError as e:
        _fail(EXIT_INPUT, str(e))
    ratio = SequenceMatcher(None, a, b, autojunk=False).ratio()
    la, lb = a.splitlines(), b.splitlines()
    changed = sum(
        1
        for line in unified_diff(la, lb, lineterm="", n=0)
        if line[:1] in "+-" and line[:3] not in ("+++", "---")
    )
    print(json.dumps({
        "similarity": round(ratio, 4),
        "expect_lines": len(la),
        "output_lines": len(lb),
        "changed_lines": changed,
    }, ensure_ascii=False))


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(EXIT_INTERRUPT)


if __name__ == "__main__":
    main()
