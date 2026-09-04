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
from .config import Config
from .project import Project, ProjectError, create_project, open_project, workspace_for
from .review import ReviewError, ReviewStore
from .snapshot import SnapshotError, import_snapshot

if TYPE_CHECKING:  # annotation-only — pipeline keo engines nang o import-time
    from .pipeline import PipelineResult

app = typer.Typer(
    name="zhvi",
    help="CLI dich truyen Trung -> Viet (VietPhrase-first, co state, resumable).",
    no_args_is_help=True,
)
err_console = Console(stderr=True)

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
            rev = st.latest_source_revision()
            if rev is None:
                _fail(EXIT_STATE, "Project chua co source — chay `zhvi import` truoc.")
            text = Path(rev.snapshot_path).read_text(encoding=rev.encoding)
    except (ProjectError, OSError, SnapshotError) as e:
        _fail(EXIT_INPUT, str(e))
    doc = parse_document(text)
    rep = inspect_document(doc)
    print(json.dumps(rep.__dict__, ensure_ascii=False, indent=2))


@app.command()
def translate(
    file: Path = typer.Argument(None, help="TXT nguon (happy path 1 lenh)."),
    output: Path = typer.Option(None, "-o", "--output"),
    project: Path = typer.Option(None, "--project", "-p"),
    style: str = typer.Option("convert-qt", "--style"),
    encoding: str = typer.Option("utf-8", "--encoding"),
    dict_dir: str = typer.Option(None, "--dict-dir"),
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


@app.command()
def status(
    project: Path = typer.Option(..., "--project", "-p"),
    require_complete: bool = typer.Option(False, "--require-complete"),
) -> None:
    """Tien do run, route, cache, lloi, review."""
    from .state import State

    try:
        p = open_project(project)
        st = State(p.db_path)
        info = st.status_info()
    except (ProjectError, OSError) as e:
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
    if project is not None and cfg_dict_dir is None:
        try:
            cfg_dict_dir = open_project(project).config().dict_dir
        except ProjectError:
            pass
    ok = run_doctor(err_console, Config(dict_dir=cfg_dict_dir or "crawler/vietphrase/dicts"))
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
