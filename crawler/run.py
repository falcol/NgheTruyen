#!/usr/bin/env python3
"""CLI entry point for crawlers.

Usage:
    python -m crawler.run <site> <chapter-url> [--start INDEX] [--max COUNT] [--dest DIR]

Sites:
    truyenqq     - truyenqq.vn
    metruyenchu  - metruyenchu.com.vn
    metruyencv   - metruyencv.xyz

Options:
    --start INDEX   Starting chapter index (default: 0)
    --max COUNT     Max chapters to crawl, 0=unlimited (default: 0)
    --dest DIR      Destination directory name for cross-source append
                    (e.g. --dest metruyenchu to write into metruyenchu's data dir)
    --parallel      Use parallel crawling with URL prediction
    --workers N     Number of parallel workers (default: 3)

Examples:
    # Crawl all chapters from truyenqq
    python -m crawler.run truyenqq "https://truyenqq.vn/doc-convert-..../12992985-0/"

    # Crawl max 5 chapters for testing
    python -m crawler.run truyenqq "https://truyenqq.vn/doc-convert-..../12992985-0/" --max 5

    # Resume from chapter 100
    python -m crawler.run truyenqq "https://truyenqq.vn/doc-convert-..../XXXXX-99/" --start 99

    # Cross-source append: crawl from metruyencv, save to metruyenchu's data dir
    python -m crawler.run metruyencv "https://metruyencv.xyz/truyen/..../chuong-696/" --start 695 --dest metruyenchu

    # Parallel crawl with 5 workers
    python -m crawler.run truyenqq "https://truyenqq.vn/doc-convert-..../12992985-0/" --parallel --workers 5
"""
import argparse
import sys
import time

from .truyenqq import TruyenQQCrawler
from .metruyenchu import MetruyenchuCrawler
from .metruyencv import MetruyencvCrawler
from .truyenfullmoi import TruyenfullmoiCrawler

CRAWLERS = {
    "truyenqq": TruyenQQCrawler,
    "metruyenchu": MetruyenchuCrawler,
    "metruyencv": MetruyencvCrawler,
    "truyenfullmoi": TruyenfullmoiCrawler,
}

# Preset for --aggressive: maximize throughput, accept higher 429 risk.
# Adaptive multiplier in BaseCrawler will auto-throttle if server pushes back.
AGGRESSIVE_WORKERS = 8
AGGRESSIVE_PARALLEL_DELAY = (0.3, 0.7)


def format_duration(seconds: float) -> str:
    """Human-friendly duration: '1h 23m 45s' or '5m 12s' or '42.3s'."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    mins, secs = divmod(int(seconds), 60)
    if mins < 60:
        return f"{mins}m {secs}s"
    hrs, mins = divmod(mins, 60)
    return f"{hrs}h {mins}m {secs}s"


def main():
    parser = argparse.ArgumentParser(description="Story crawler CLI")
    parser.add_argument("site", choices=CRAWLERS.keys(), help="Target site")
    parser.add_argument("url", help="Starting chapter URL")
    parser.add_argument("--start", type=int, default=0, help="Starting chapter index (default: 0)")
    parser.add_argument("--max", type=int, default=0, help="Max chapters to crawl, 0=unlimited (default: 0)")
    parser.add_argument("--dest", type=str, default=None, help="Destination directory name (for cross-source append)")
    parser.add_argument("--parallel", action="store_true", help="Use parallel crawling with URL prediction")
    parser.add_argument("--workers", type=int, default=3, help="Number of parallel workers (default: 3)")
    parser.add_argument(
        "--aggressive",
        action="store_true",
        help=f"Maximize speed: --workers {AGGRESSIVE_WORKERS} + parallel_delay {AGGRESSIVE_PARALLEL_DELAY}. "
             "Higher 429 risk; adaptive throttle will auto-recover.",
    )

    args = parser.parse_args()
    crawler = CRAWLERS[args.site](dest_dir=args.dest)

    # Apply aggressive preset (overrides --workers if explicitly set, by design)
    if args.aggressive:
        if not args.parallel:
            print("[run] --aggressive implies --parallel, enabling.", file=sys.stderr)
            args.parallel = True
        crawler.parallel_delay = AGGRESSIVE_PARALLEL_DELAY
        args.workers = AGGRESSIVE_WORKERS
        print(
            f"[run] Aggressive mode: workers={args.workers}, "
            f"parallel_delay={AGGRESSIVE_PARALLEL_DELAY}",
            file=sys.stderr,
        )

    start = time.monotonic()
    result: list = []
    try:
        if args.parallel:
            result = crawler.crawl_parallel(
                args.url, start_index=args.start, max_chapters=args.max, workers=args.workers
            )
        else:
            result = crawler.crawl(args.url, start_index=args.start, max_chapters=args.max)
    finally:
        elapsed = time.monotonic() - start
        n_total = len(result) if result else 0
        rate = n_total / elapsed if elapsed > 0 and n_total else 0
        summary = f"\n[run] Total time: {format_duration(elapsed)}"
        if n_total:
            summary += f"  |  {n_total} chapters indexed  |  {rate:.2f} ch/s"
        print(summary, file=sys.stderr)


if __name__ == "__main__":
    main()
