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
            ch_first = chapters[vol_start]["index"] + 1
            ch_last = chapters[vol_end - 1]["index"] + 1
            vol_data = {
                "volume": vol_num,
                "chapterRange": [ch_first, ch_last],
                "chapters": chapters[vol_start:vol_end],
            }
            filename = f"vol-{vol_num:03d}-ch{ch_first:03d}-{ch_last:03d}.json"
            self.save_json(vol_data, out / filename)

    @abc.abstractmethod
    def crawl(self, start_url: str, **kwargs) -> list[dict]:
        """Crawl a story starting from the given URL. Returns list of chapter dicts."""
        ...
