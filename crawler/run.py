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

Examples:
    # Crawl all chapters from truyenqq
    python -m crawler.run truyenqq "https://truyenqq.vn/doc-convert-..../12992985-0/"

    # Crawl max 5 chapters for testing
    python -m crawler.run truyenqq "https://truyenqq.vn/doc-convert-..../12992985-0/" --max 5

    # Resume from chapter 100
    python -m crawler.run truyenqq "https://truyenqq.vn/doc-convert-..../XXXXX-99/" --start 99

    # Cross-source append: crawl from metruyencv, save to metruyenchu's data dir
    python -m crawler.run metruyencv "https://metruyencv.xyz/truyen/..../chuong-696/" --start 695 --dest metruyenchu
"""
import argparse
import sys

from .truyenqq import TruyenQQCrawler
from .metruyenchu import MetruyenchuCrawler
from .metruyencv import MetruyencvCrawler

CRAWLERS = {
    "truyenqq": TruyenQQCrawler,
    "metruyenchu": MetruyenchuCrawler,
    "metruyencv": MetruyencvCrawler,
}


def main():
    parser = argparse.ArgumentParser(description="Story crawler CLI")
    parser.add_argument("site", choices=CRAWLERS.keys(), help="Target site")
    parser.add_argument("url", help="Starting chapter URL")
    parser.add_argument("--start", type=int, default=0, help="Starting chapter index (default: 0)")
    parser.add_argument("--max", type=int, default=0, help="Max chapters to crawl, 0=unlimited (default: 0)")
    parser.add_argument("--dest", type=str, default=None, help="Destination directory name (for cross-source append)")

    args = parser.parse_args()
    crawler = CRAWLERS[args.site](dest_dir=args.dest)
    crawler.crawl(args.url, start_index=args.start, max_chapters=args.max)


if __name__ == "__main__":
    main()
