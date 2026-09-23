#!/usr/bin/env python3
"""Retranslate only gt05 lines whose Chinese contains the given keys, then overlay.

Full `vp file` walks every chunk of the book. A glossary or engine fix that
only applies where a known string appears does not need that.

  python3 crawler/patch_manh_nhat_gt05.py 好几个省 几个省
  python3 crawler/patch_manh_nhat_gt05.py --dry-run 好几个省
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "vp" / "src"))
sys.path.insert(0, str(ROOT))

from vp.dicts import find_local_dict_dir, load_local_engine, read_overlay  # noqa: E402
from vp.filetrans import translate_file  # noqa: E402

ZH = ROOT / "zhvi/workspace/manh-nhat-from-1012.zh.txt"
VI = ROOT / "zhvi/workspace/manh-nhat-from-1012.zh.vi.gt05.txt"
OVERLAY = ROOT / "zhvi/workspace/manh-nhat-from-1012.novel-review.gt05.txt"


def _one_line(text: str) -> str:
    lines = text.splitlines()
    if len(lines) != 1:
        raise SystemExit(f"một dòng Trung ra {len(lines)} dòng Việt, dừng để khỏi lệch file")
    return lines[0]


def main() -> int:
    parser = argparse.ArgumentParser(description="Vá dòng gt05 chứa cụm Trung đã sửa, rồi đổ web.")
    parser.add_argument("needles", nargs="+", help="Cụm tiếng Trung vừa đổi nghĩa")
    parser.add_argument("--dry-run", action="store_true", help="In câu đổi, không ghi file và không đổ web")
    parser.add_argument("--no-web", action="store_true", help="Ghi gt05, không đổ reader")
    args = parser.parse_args()
    needles = [item for item in args.needles if item]
    if not needles:
        print("Thiếu cụm tiếng Trung", file=sys.stderr)
        return 1

    zh_lines = ZH.read_text(encoding="utf-8").splitlines()
    vi_lines = VI.read_text(encoding="utf-8").splitlines()
    if len(zh_lines) != len(vi_lines):
        print(f"Lệch số dòng zh={len(zh_lines)} vi={len(vi_lines)}", file=sys.stderr)
        return 1
    hits = [i for i, line in enumerate(zh_lines) if any(needle in line for needle in needles)]
    if not hits:
        print("Không có dòng nào chứa cụm này", file=sys.stderr)
        return 1

    print(f"Nạp từ điển, {len(hits)} dòng...", file=sys.stderr, flush=True)
    engine = load_local_engine(find_local_dict_dir(None), simplified=True, luat_nhan=2)
    overlay = read_overlay(OVERLAY) if OVERLAY.is_file() else None
    changed: list[int] = []
    for index in hits:
        new = _one_line(translate_file(zh_lines[index], engine, overlay=overlay))
        if new != vi_lines[index]:
            vi_lines[index] = new
            changed.append(index)

    print(f"Dòng chứa cụm: {len(hits)}. Dòng đổi chữ: {len(changed)}.", file=sys.stderr)
    for index in changed:
        print(f"L{index + 1} {vi_lines[index][:180]}", file=sys.stderr)
    if args.dry_run or not changed:
        return 0

    tmp = VI.with_name(VI.name + ".tmp")
    tmp.write_text("\n".join(vi_lines) + "\n", encoding="utf-8")
    tmp.replace(VI)
    print(f"Đã ghi {VI}", file=sys.stderr)
    if args.no_web:
        return 0

    import crawler.overlay_manh_nhat_1012 as overlay_mod

    overlay_mod.VI = VI
    return overlay_mod.main()


if __name__ == "__main__":
    raise SystemExit(main())
