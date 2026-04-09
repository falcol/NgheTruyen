# TruyenQQ Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python crawler to extract all chapters from truyenqq.vn and save as chunked JSON files for a personal reading/TTS web app.

**Architecture:** Extensible crawler folder with a `BaseCrawler` abstract class for shared logic (HTTP, rate limiting, JSON output) and site-specific subclasses. TruyenQQ crawler navigates sequentially via "Sau" (Next) links, extracts text from `#noidungchap`, and saves chunked by volume (50 chapters/file) with paragraph arrays for TTS.

**Tech Stack:** Python 3.12, requests, BeautifulSoup4

---

## Probe Results (verified)

| Item | Value |
|---|---|
| Content selector | `#noidungchap` |
| Chapter title | `h2` (second `h1` has story title) |
| Navigation | `a` with text "Sau" → next chapter href |
| First chapter URL | `/doc-convert-that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/12992985-0/` |
| Total chapters | ~387 |
| Content format | Text with `<br/>` line breaks |
| Noise line | First line "Nguoi dang: ..." → strip |
| Rate limit | 2-3s delay between requests |

## File Structure

```
crawler/
├── base.py              # BaseCrawler ABC — HTTP session, rate limit, JSON save, retry
├── truyenqq.py          # TruyenQQCrawler(BaseCrawler) — parse #noidungchap, follow "Sau"
├── run.py               # CLI entry point: python run.py truyenqq <story-url> [--start N]
├── requirements.txt     # requests, beautifulsoup4
└── data/                # Output directory (gitignored)
    └── .gitkeep
```

---

### Task 1: Project scaffolding

**Files:**
- Create: `crawler/requirements.txt`
- Create: `crawler/data/.gitkeep`
- Create: `.gitignore`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p crawler/data
```

- [ ] **Step 2: Write requirements.txt**

Create `crawler/requirements.txt`:
```
requests>=2.31.0
beautifulsoup4>=4.12.0
```

- [ ] **Step 3: Write .gitignore**

Create `.gitignore` at project root:
```
crawler/data/*
!crawler/data/.gitkeep
__pycache__/
*.pyc
.env
```

- [ ] **Step 4: Create data/.gitkeep**

```bash
touch crawler/data/.gitkeep
```

- [ ] **Step 5: Install dependencies**

```bash
pip3 install -r crawler/requirements.txt --break-system-packages
```

- [ ] **Step 6: Commit**

```bash
git add crawler/requirements.txt crawler/data/.gitkeep .gitignore
git commit -m "chore: scaffold crawler project structure"
```

---

### Task 2: BaseCrawler — shared crawler logic

**Files:**
- Create: `crawler/base.py`

- [ ] **Step 1: Write BaseCrawler class**

Create `crawler/base.py` with:

```python
import abc
import json
import os
import time
import random
import logging
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"


class BaseCrawler(abc.ABC):
    """Base class for all site crawlers."""

    def __init__(self, site_name: str, delay: tuple[float, float] = (2.0, 4.0)):
        self.site_name = site_name
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "vi-VN,vi;q=0.9",
        })

    def fetch(self, url: str, retries: int = 3) -> BeautifulSoup:
        """Fetch URL with retry and rate limiting. Returns parsed soup."""
        for attempt in range(1, retries + 1):
            try:
                time.sleep(random.uniform(*self.delay))
                resp = self.session.get(url, timeout=15)
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "html.parser")
            except requests.RequestException as e:
                logger.warning(f"Attempt {attempt}/{retries} failed for {url}: {e}")
                if attempt == retries:
                    raise
                time.sleep(2 ** attempt)

    def output_dir(self, story_slug: str) -> Path:
        """Return and create output directory for a story."""
        path = DATA_DIR / self.site_name / story_slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, data: dict | list, filepath: Path) -> None:
        """Save data as JSON with UTF-8 encoding."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved: {filepath}")

    def save_volumes(self, chapters: list[dict], story_slug: str, chapters_per_vol: int = 50) -> None:
        """Save chapters chunked into volume files."""
        out = self.output_dir(story_slug)

        # Save full index
        index = [{"index": c["index"], "title": c["title"]} for c in chapters]
        self.save_json(index, out / "chapters_index.json")

        # Save volumes
        for vol_start in range(0, len(chapters), chapters_per_vol):
            vol_end = min(vol_start + chapters_per_vol, len(chapters))
            vol_num = vol_start // chapters_per_vol + 1
            vol_data = {
                "volume": vol_num,
                "chapterRange": [vol_start + 1, vol_end],
                "chapters": chapters[vol_start:vol_end],
            }
            filename = f"vol-{vol_num:03d}-ch{vol_start+1:03d}-{vol_end:03d}.json"
            self.save_json(vol_data, out / filename)

    @abc.abstractmethod
    def crawl(self, start_url: str, **kwargs) -> list[dict]:
        """Crawl a story starting from the given URL. Returns list of chapter dicts."""
        ...
```

- [ ] **Step 2: Verify syntax**

```bash
cd /home/falcol/NgheTruyen && python3 -c "from crawler.base import BaseCrawler; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add crawler/base.py
git commit -m "feat: add BaseCrawler with HTTP session, retry, and volume-chunked JSON output"
```

---

### Task 3: TruyenQQCrawler — site-specific logic

**Files:**
- Create: `crawler/truyenqq.py`

- [ ] **Step 1: Write TruyenQQCrawler**

Create `crawler/truyenqq.py`:

```python
import re
from urllib.parse import urljoin

from .base import BaseCrawler, logger

BASE_URL = "https://truyenqq.vn/"


class TruyenQQCrawler(BaseCrawler):
    """Crawler for truyenqq.vn doc-convert (text novel) pages."""

    def __init__(self):
        super().__init__(site_name="truyenqq")

    def _extract_chapter(self, soup) -> dict:
        """Extract chapter title and paragraphs from a chapter page."""
        # Title from h2
        h2 = soup.find("h2")
        title = h2.get_text(strip=True) if h2 else "Unknown"

        # Content from #noidungchap
        noidung = soup.find(id="noidungchap")
        if not noidung:
            raise ValueError("Could not find #noidungchap")

        text = noidung.get_text(separator="\n").strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # Strip noise: first line "Nguoi dang: ..." and trailing recommendation lines
        if lines and re.match(r"^Ng.+i đăng:", lines[0]):
            lines = lines[1:]

        return {"title": title, "paragraphs": lines}

    def _next_chapter_url(self, soup) -> str | None:
        """Find the 'Sau' (Next) navigation link."""
        for a in soup.find_all("a"):
            if a.get_text(strip=True) == "Sau":
                href = a.get("href", "")
                if href:
                    return urljoin(BASE_URL, href)
        return None

    def _extract_slug(self, url: str) -> str:
        """Extract story slug from URL for output directory naming."""
        # URL: .../doc-convert-<slug>-<storyID>/<chapterID>-<index>/
        match = re.search(r"doc-convert-(.+?)/", url)
        return match.group(1) if match else "unknown"

    def crawl(self, start_url: str, start_index: int = 0, max_chapters: int = 0) -> list[dict]:
        """
        Crawl all chapters starting from start_url by following 'Sau' links.

        Args:
            start_url: URL of the first chapter to crawl.
            start_index: Starting chapter index number (default 0).
            max_chapters: Max chapters to crawl, 0 = unlimited.
        """
        slug = self._extract_slug(start_url)
        chapters = []
        url = start_url
        index = start_index

        logger.info(f"Starting crawl: {slug}")
        logger.info(f"First URL: {url}")

        while url:
            logger.info(f"Crawling chapter {index + 1}: {url}")

            try:
                soup = self.fetch(url)
                chapter = self._extract_chapter(soup)
                chapter["index"] = index
                chapters.append(chapter)
                logger.info(f"  -> {chapter['title']} ({len(chapter['paragraphs'])} paragraphs)")
            except Exception as e:
                logger.error(f"Failed to crawl {url}: {e}")
                break

            if max_chapters and len(chapters) >= max_chapters:
                logger.info(f"Reached max_chapters limit ({max_chapters})")
                break

            url = self._next_chapter_url(soup)
            index += 1

        logger.info(f"Crawl complete: {len(chapters)} chapters")
        self.save_volumes(chapters, slug)
        return chapters
```

- [ ] **Step 2: Create `crawler/__init__.py`**

Create `crawler/__init__.py`:

```python
```

(Empty file — makes `crawler` a package for relative imports.)

- [ ] **Step 3: Verify import**

```bash
cd /home/falcol/NgheTruyen && python3 -c "from crawler.truyenqq import TruyenQQCrawler; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add crawler/__init__.py crawler/truyenqq.py
git commit -m "feat: add TruyenQQCrawler — parse #noidungchap, follow Sau links"
```

---

### Task 4: CLI entry point

**Files:**
- Create: `crawler/run.py`

- [ ] **Step 1: Write run.py**

Create `crawler/run.py`:

```python
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
```

- [ ] **Step 2: Verify CLI help**

```bash
cd /home/falcol/NgheTruyen && python3 -m crawler.run --help
```

Expected: Shows usage with `site`, `url`, `--start`, `--max` arguments.

- [ ] **Step 3: Commit**

```bash
git add crawler/run.py
git commit -m "feat: add CLI entry point for crawler"
```

---

### Task 5: Smoke test — crawl 3 chapters

- [ ] **Step 1: Run crawler on first 3 chapters**

```bash
cd /home/falcol/NgheTruyen && python3 -m crawler.run truyenqq \
  "https://truyenqq.vn/doc-convert-that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/12992985-0/" \
  --max 3
```

Expected output:
- Logs showing 3 chapters crawled with titles and paragraph counts
- `crawler/data/truyenqq/that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/chapters_index.json`
- `crawler/data/truyenqq/that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/vol-001-ch001-003.json`

- [ ] **Step 2: Verify JSON output**

```bash
python3 -c "
import json
with open('crawler/data/truyenqq/that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/vol-001-ch001-003.json') as f:
    data = json.load(f)
print(f'Volume: {data[\"volume\"]}')
print(f'Chapters: {len(data[\"chapters\"])}')
for ch in data['chapters']:
    print(f'  [{ch[\"index\"]}] {ch[\"title\"]} — {len(ch[\"paragraphs\"])} paragraphs')
    print(f'       First: {ch[\"paragraphs\"][0][:80]}')
"
```

Expected: 3 chapters with Vietnamese text paragraphs, no "Nguoi dang" noise line.

- [ ] **Step 3: Fix any issues found, then commit**

```bash
git add crawler/
git commit -m "test: verify crawler works on first 3 chapters"
```

---

### Task 6: Full crawl (run after verification)

- [ ] **Step 1: Run full crawl**

```bash
cd /home/falcol/NgheTruyen && python3 -m crawler.run truyenqq \
  "https://truyenqq.vn/doc-convert-that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/12992985-0/"
```

Expected: ~387 chapters crawled, ~8 volume files created.

**Note:** This will take ~15-20 minutes with 2-3s delay between requests.
