#!/usr/bin/env python3
"""Scan a crawled story dir (vol-*.json.gz) for leftover convert artifacts.

  python -m crawler.vietphrase.check_vi_convert \\
    crawler/data/xtruyen/manh-nhat-tu-tien-hoc-sinh-tieu-hoc
"""
from __future__ import annotations

import gzip
import json
import re
import sys
from pathlib import Path

# (id, pattern, allow_if) — allow_if substring means hit is OK (not counted as fail)
CHECKS: list[tuple[str, str, str | None]] = [
    ("da_da", r"đã đã", None),
    ("bi_bi", r"bị bị", "phòng bị bị"),
    ("doat_da", r"đã bị đoạt đã", None),
    ("tong_cua", r"Tông cửa", None),
    ("may_trang", r"mây trang", None),
    ("hieu_rong", r"Hiểu rồng", None),
    ("hau_duc_may", r"[Hh]ầu đức mây", None),
]


def iter_chapters(story: Path):
    for vol in sorted(story.glob("vol-*.json.gz")):
        with gzip.open(vol, "rt", encoding="utf-8") as f:
            data = json.load(f)
        for ch in data.get("chapters") or []:
            yield ch


def scan(story: Path) -> int:
    compiled = [(cid, re.compile(pat), ok) for cid, pat, ok in CHECKS]
    counts = {cid: 0 for cid, _, _ in CHECKS}
    samples: dict[str, list[str]] = {cid: [] for cid, _, _ in CHECKS}
    nch = 0
    for ch in iter_chapters(story):
        nch += 1
        title = ch.get("title") or ""
        blob = title + "\n" + "\n".join(ch.get("paragraphs") or [])
        idx = ch.get("index")
        for cid, rx, ok in compiled:
            for m in rx.finditer(blob):
                if ok and ok in blob[max(0, m.start() - 12) : m.end() + 12]:
                    continue
                counts[cid] += 1
                if len(samples[cid]) < 3:
                    ctx = blob[max(0, m.start() - 24) : m.end() + 32].replace("\n", " ")
                    samples[cid].append(f"[{idx}] …{ctx}…")
    print(f"story={story} chapters={nch}")
    bad = 0
    for cid, n in counts.items():
        print(f"  {n:5}  {cid}")
        for s in samples[cid]:
            print(f"         {s}")
        if n:
            bad += 1
    return 1 if bad else 0


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m crawler.vietphrase.check_vi_convert STORY_DIR", file=sys.stderr)
        return 2
    story = Path(sys.argv[1])
    if not story.is_dir():
        print(f"not a dir: {story}", file=sys.stderr)
        return 2
    return scan(story)


if __name__ == "__main__":
    raise SystemExit(main())
