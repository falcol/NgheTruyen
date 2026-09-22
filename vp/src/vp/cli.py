"""Command line for the vietphrase.app file translator."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from vp.dicts import (
    find_local_dict_dir,
    load_local_engine,
    load_manifest_engine,
    read_custom,
    read_overlay,
)
from vp.filetrans import translate_file
from vp.ner_model import scan_file
from vp.novel_scan import scan_file as novel_scan_file
from vp.textutil import decode_source


def _default_output(src: Path) -> Path:
    if src.suffix.lower() == ".txt":
        return src.with_name(src.stem + ".vi.txt")
    return src.with_name(src.name + ".vi.txt")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vp",
        description="Dịch file truyện Trung → Việt theo tab File của vietphrase.app.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    file_cmd = sub.add_parser("file", help="Dịch một file .txt")
    file_cmd.add_argument("input", type=Path, help="File tiếng Trung")
    file_cmd.add_argument("-o", "--output", type=Path, help="File tiếng Việt. Mặc định: <tên>.vi.txt")
    file_cmd.add_argument(
        "--mode",
        choices=("vietphrase", "hanviet"),
        default="vietphrase",
        help="vietphrase hoặc hanviet. Mặc định: vietphrase",
    )
    file_cmd.add_argument("--luat-nhan", type=int, choices=(0, 1, 2, 3), default=2)
    file_cmd.add_argument("--no-simplified", action="store_true", help="Giữ phồn thể, không đổi sang giản thể")
    file_cmd.add_argument("--custom", type=Path, help="Từ riêng zh=vi, ưu tiên 999")
    file_cmd.add_argument("--overlay", type=Path, help="Glossary tên đã duyệt, zh=vi")
    file_cmd.add_argument("--dict", choices=("local", "manifest"), default="local")
    file_cmd.add_argument("--dict-dir", help="Thư mục từ điển local. Mặc định: crawler/vietphrase/dicts")
    file_cmd.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "vp-dicts",
        help="Nơi lưu từ điển tải từ manifest",
    )
    file_cmd.add_argument("--refresh-dict", action="store_true", help="Tải lại từ điển manifest")
    file_cmd.add_argument(
        "--deep-scan",
        action="store_true",
        help="Một lệnh: quét tên trên GPU rồi dịch luôn bằng các tên đã duyệt",
    )
    file_cmd.add_argument(
        "--encoding",
        choices=("auto", "utf-8", "gbk", "big5"),
        default="auto",
    )
    scan_cmd = sub.add_parser(
        "scan",
        help="Quét Novel Scan và ghi file cần xem cùng file bỏ, để sửa rồi dùng --overlay",
    )
    scan_cmd.add_argument("input", type=Path, help="File tiếng Trung")
    scan_cmd.add_argument("--dict-dir", help="Thư mục từ điển local. Mặc định: crawler/vietphrase/dicts")
    scan_cmd.add_argument(
        "--cache-dir",
        type=Path,
        default=Path.home() / ".cache" / "vp-dicts",
        help="Nơi lưu model Novel Scan",
    )
    scan_cmd.add_argument("--refresh", action="store_true", help="Tải lại script và model Novel Scan")
    scan_cmd.add_argument(
        "--encoding",
        choices=("auto", "utf-8", "gbk", "big5"),
        default="auto",
    )
    return parser


def _progress(done: int, total: int) -> None:
    print(f"Đoạn {done}/{total}", file=sys.stderr, flush=True)


def _ner_progress(done: int, total: int) -> None:
    print(f"Quét sâu NER · đoạn {done}/{total}", file=sys.stderr, flush=True)


def _write_ner_sidecar(dest: Path, found_names) -> None:
    approved = [item for item in found_names if item.status == "approved" and item.vi]
    pending = [item for item in found_names if item.status != "approved"]
    if not approved and not pending:
        return
    if dest.name.endswith(".vi.txt"):
        path = dest.with_name(dest.name[: -len(".vi.txt")] + ".ner.txt")
    else:
        path = dest.with_name(dest.stem + ".ner.txt")
    lines = [f"{item.zh}={item.vi}" for item in approved]
    if pending:
        lines.append("# chờ duyệt")
        lines.extend(f"# {item.zh}\t{item.category}\t{item.count}" for item in pending)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Đã ghi {path}", file=sys.stderr)


def translate_path(args: argparse.Namespace) -> int:
    src: Path = args.input
    if not src.is_file():
        print(f"Không thấy file: {src}", file=sys.stderr)
        return 1
    if args.custom and not args.custom.is_file():
        print(f"Không thấy từ riêng: {args.custom}", file=sys.stderr)
        return 1
    if args.overlay and not args.overlay.is_file():
        print(f"Không thấy overlay: {args.overlay}", file=sys.stderr)
        return 1
    custom = read_custom(args.custom) if args.custom else None
    overlay = read_overlay(args.overlay) if args.overlay else None
    simplified = not args.no_simplified
    print("Đang nạp từ điển...", file=sys.stderr, flush=True)
    try:
        if args.dict == "manifest":
            engine = load_manifest_engine(
                cache_dir=args.cache_dir,
                simplified=simplified,
                luat_nhan=args.luat_nhan,
                custom=custom,
                refresh=args.refresh_dict,
            )
        else:
            engine = load_local_engine(
                find_local_dict_dir(args.dict_dir),
                simplified=simplified,
                luat_nhan=args.luat_nhan,
                custom=custom,
            )
    except (OSError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    data = src.read_bytes()
    try:
        text = decode_source(data, args.encoding)
    except (UnicodeDecodeError, LookupError, ValueError) as exc:
        print(f"Không đọc được file: {exc}", file=sys.stderr)
        return 1
    found_names = []
    if args.deep_scan:
        try:
            found_names, stats = scan_file(
                text,
                engine,
                args.cache_dir,
                refresh=args.refresh_dict,
                require_gpu=True,
                on_progress=_ner_progress,
            )
        except (OSError, RuntimeError, ValueError) as exc:
            print(f"Quét sâu NER thất bại: {exc}", file=sys.stderr)
            return 1
        if args.mode == "vietphrase":
            approved = [(item.zh, item.vi, 30) for item in found_names if item.status == "approved" and item.vi]
            overlay = (overlay or []) + approved
        print(
            f"NER sâu: {stats.approved} tên duyệt · {stats.pending} đang chờ · {stats.entities} entity",
            file=sys.stderr,
        )
    output = translate_file(
        text,
        engine,
        mode=args.mode,
        overlay=overlay,
        on_progress=_progress,
    )
    dest = args.output
    if dest is None:
        dest = _default_output(src)
    if str(dest) == "-":
        sys.stdout.write(output)
        if output and not output.endswith("\n"):
            sys.stdout.write("\n")
        return 0
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    tmp.write_text(output, encoding="utf-8")
    tmp.replace(dest)
    print(f"Đã ghi {dest}", file=sys.stderr)
    if found_names:
        _write_ner_sidecar(dest, found_names)
    return 0


def scan_path(args: argparse.Namespace) -> int:
    src: Path = args.input
    if not src.is_file():
        print(f"Không thấy file: {src}", file=sys.stderr)
        return 1
    try:
        review_path, reject_path, review_count, reject_count = novel_scan_file(
            src,
            encoding=args.encoding,
            dict_dir=args.dict_dir,
            cache_dir=args.cache_dir,
            refresh=args.refresh,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"Novel Scan thất bại: {exc}", file=sys.stderr)
        return 1
    print(f"Đã ghi {review_path} ({review_count} cần xem)", file=sys.stderr)
    print(f"Đã ghi {reject_path} ({reject_count} bỏ)", file=sys.stderr)
    print("Sửa cột tiếng Việt trong file cần xem, rồi dịch bằng --overlay file đó.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.cmd == "file":
        return translate_path(args)
    if args.cmd == "scan":
        return scan_path(args)
    parser.error("lệnh không hỗ trợ")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
