#!/usr/bin/env python3
"""Compress existing .json files in data/ to .json.gz (minified).

Usage:
    python -m crawler.compress              # Dry run: show what would change
    python -m crawler.compress --apply      # Actually compress + delete originals
    python -m crawler.compress --apply --keep-json  # Compress but keep originals

Skips _progress.json (left as plain JSON since it changes often).
"""
import argparse
import gzip
import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
SKIP_NAMES = {"_progress.json"}


def find_targets() -> list[Path]:
    """All .json files under data/ (excluding _progress.json and already-gzipped)."""
    targets = []
    if not DATA_DIR.exists():
        return targets
    for p in DATA_DIR.rglob("*.json"):
        if p.name in SKIP_NAMES:
            continue
        if p.with_name(p.name + ".gz").exists():
            continue  # Already compressed
        targets.append(p)
    return targets


def compress_file(path: Path) -> tuple[int, int]:
    """Compress a single .json file. Returns (orig_size, gz_size)."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    gz_path = path.with_name(path.name + ".gz")
    with gzip.open(gz_path, "wt", encoding="utf-8", compresslevel=9) as f:
        f.write(text)
    return path.stat().st_size, gz_path.stat().st_size


def fmt_size(n: int) -> str:
    for unit in ["B", "K", "M", "G"]:
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}T"


def main():
    parser = argparse.ArgumentParser(description="Compress data/*.json -> .json.gz")
    parser.add_argument("--apply", action="store_true", help="Actually do it (default: dry-run)")
    parser.add_argument("--keep-json", action="store_true", help="Keep original .json after compression")
    args = parser.parse_args()

    targets = find_targets()
    if not targets:
        print("No .json files to compress.")
        return

    print(f"Found {len(targets)} .json files\n")

    total_orig = 0
    total_gz = 0

    for path in targets:
        if args.apply:
            orig, gz = compress_file(path)
            total_orig += orig
            total_gz += gz
            ratio = gz / orig * 100
            rel = path.relative_to(DATA_DIR)
            print(f"  {rel}  {fmt_size(orig)} -> {fmt_size(gz)} ({ratio:.0f}%)")
            if not args.keep_json:
                path.unlink()
        else:
            orig = path.stat().st_size
            total_orig += orig
            rel = path.relative_to(DATA_DIR)
            print(f"  [dry] {rel}  ({fmt_size(orig)})")

    print()
    if args.apply:
        saved = total_orig - total_gz
        ratio = total_gz / total_orig * 100 if total_orig else 0
        action = "kept originals" if args.keep_json else "deleted originals"
        print(f"Total: {fmt_size(total_orig)} -> {fmt_size(total_gz)} ({ratio:.0f}%, saved {fmt_size(saved)}, {action})")
    else:
        print(f"Total to compress: {fmt_size(total_orig)}")
        print("Run with --apply to actually compress.")


if __name__ == "__main__":
    main()
