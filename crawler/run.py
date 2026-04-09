#!/usr/bin/env python3
"""CLI entry point for crawlers.

Usage:
    python -m crawler.run truyenqq <chapter-url> [--start INDEX] [--max COUNT]

Examples:
    # Crawl all chapters starting from chapter 1
    python -m crawler.run truyenqq "https://truyenqq.vn/doc-convert-that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/12992985-0/"

    # Crawl max 5 chapters for testing
    python -m crawler.run truyenqq "https://truyenqq.vn/doc-convert-..../12992985-0/" --max 5

    # Resume from chapter 100
    python -m crawler.run truyenqq "https://truyenqq.vn/doc-convert-..../XXXXX-99/" --start 99
"""
import argparse
import sys

from .truyenqq import TruyenQQCrawler

CRAWLERS = {
    "truyenqq": TruyenQQCrawler,
}


def main():
    parser = argparse.ArgumentParser(description="Story crawler CLI")
    parser.add_argument("site", choices=CRAWLERS.keys(), help="Target site")
    parser.add_argument("url", help="Starting chapter URL")
    parser.add_argument("--start", type=int, default=0, help="Starting chapter index (default: 0)")
    parser.add_argument("--max", type=int, default=0, help="Max chapters to crawl, 0=unlimited (default: 0)")

    args = parser.parse_args()
    crawler = CRAWLERS[args.site]()
    crawler.crawl(args.url, start_index=args.start, max_chapters=args.max)


if __name__ == "__main__":
    main()
