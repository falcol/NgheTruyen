#!/usr/bin/env python3
"""Overlay zhvi dist VI onto xtruyen manh-nhat JSON from printed Chương 1012.

Align by parse_zh_title_num / parse_local_title_num, never JSON index.
Writes crawler/data then copies dirty vols to web/public/data.

  python3 crawler/overlay_manh_nhat_1012.py
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "zhvi" / "src"))
sys.path.insert(0, str(ROOT))

from crawler.iqiyi import parse_local_title_num, parse_zh_title_num  # noqa: E402
from zhvi.document import CHAPTER_PRESET_RE, MAX_HEADING_CHARS  # noqa: E402

SLUG = "manh-nhat-tu-tien-hoc-sinh-tieu-hoc"
ZH = ROOT / "zhvi/workspace/manh-nhat-from-1012.zh.txt"
VI = ROOT / "zhvi/workspace/manh-nhat-from-1012.zh.vi.txt"
SRC_DIR = ROOT / "crawler/data/xtruyen" / SLUG
WEB_DIR = ROOT / "web/public/data/xtruyen" / SLUG
MIN_NUM = 1012


def read_gz_json(path: Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return json.load(f)


def write_gz_json(path: Path, obj) -> None:
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    path.write_bytes(gzip.compress(raw, compresslevel=6))


def chapters_by_zh_headings(
    zh_text: str, vi_text: str
) -> tuple[dict[int, list[str]], dict[int, str]]:
    zh_lines = zh_text.splitlines()
    vi_lines = vi_text.splitlines()
    if len(zh_lines) != len(vi_lines):
        raise SystemExit(f"line count mismatch zh={len(zh_lines)} vi={len(vi_lines)}")
    out: dict[int, list[str]] = {}
    titles: dict[int, str] = {}
    cur_num: int | None = None
    cur_paras: list[str] = []

    def flush() -> None:
        nonlocal cur_num, cur_paras
        if cur_num is None:
            return
        if cur_num not in out:
            out[cur_num] = cur_paras
        cur_num = None
        cur_paras = []

    for zh, vi in zip(zh_lines, vi_lines):
        if CHAPTER_PRESET_RE.match(zh.strip()) and len(zh.strip()) <= MAX_HEADING_CHARS:
            flush()
            cur_num = parse_zh_title_num(zh)
            cur_paras = []
            if cur_num is not None and cur_num not in titles:
                titles[cur_num] = vi.strip()
            continue
        if cur_num is None:
            continue
        if zh.strip() == "":
            continue
        cur_paras.append(vi)
    flush()
    return out, titles


def main() -> int:
    vi_map, vi_titles = chapters_by_zh_headings(
        ZH.read_text(encoding="utf-8"),
        VI.read_text(encoding="utf-8"),
    )
    print(f"VI chapters from zip={len(vi_map)}")
    vols = sorted(SRC_DIR.glob("vol-*.json.gz"))
    counts: dict[int, int] = defaultdict(int)
    live: list[tuple[Path, dict]] = []
    for vp in vols:
        data = read_gz_json(vp)
        live.append((vp, data))
        for ch in data.get("chapters") or []:
            n = parse_local_title_num(ch.get("title") or "")
            if n:
                counts[n] += 1

    stats = {
        "considered": 0,
        "overlaid": 0,
        "skip_lt": 0,
        "skip_dup": 0,
        "skip_empty": 0,
        "skip_mismatch": 0,
        "skip_no_vi": 0,
        "unchanged": 0,
    }
    dirty: list[Path] = []
    for vp, data in live:
        changed = False
        for ch in data.get("chapters") or []:
            n = parse_local_title_num(ch.get("title") or "")
            if n is None:
                continue
            if n < MIN_NUM:
                stats["skip_lt"] += 1
                continue
            stats["considered"] += 1
            if counts[n] > 1:
                stats["skip_dup"] += 1
                continue
            paras = ch.get("paragraphs") or []
            if not paras:
                stats["skip_empty"] += 1
                continue
            if n not in vi_map:
                stats["skip_no_vi"] += 1
                continue
            vi_paras = vi_map[n]
            if len(vi_paras) != len(paras):
                stats["skip_mismatch"] += 1
                print(f"  mismatch ch.{n} live={len(paras)} vi={len(vi_paras)} {vp.name}")
                continue
            new_title = vi_titles.get(n) or ""
            if vi_paras == paras and (not new_title or new_title == ch.get("title")):
                stats["unchanged"] += 1
                continue
            ch["paragraphs"] = vi_paras
            if new_title:
                ch["title"] = new_title
            changed = True
            stats["overlaid"] += 1
        if changed:
            write_gz_json(vp, data)
            dirty.append(vp)

    WEB_DIR.mkdir(parents=True, exist_ok=True)
    for vp in dirty:
        shutil.copy2(vp, WEB_DIR / vp.name)
    print("stats", stats)
    print(f"wrote {len(dirty)} vols, copied {len(dirty)} to web")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
