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

    def __init__(self, site_name: str, delay: tuple[float, float] = (2.0, 4.0), dest_dir: str | None = None):
        self.site_name = site_name
        self.dest_dir = dest_dir
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
        if self.dest_dir:
            path = DATA_DIR / self.dest_dir / story_slug
        else:
            path = DATA_DIR / self.site_name / story_slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, data: dict | list, filepath: Path) -> None:
        """Save data as JSON with UTF-8 encoding."""
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved: {filepath}")

    CHAPTERS_PER_VOL = 50

    def save_volume(self, vol_chapters: list[dict], vol_num: int, story_slug: str) -> None:
        """Save a single volume file."""
        out = self.output_dir(story_slug)
        ch_first = vol_chapters[0]["index"] + 1
        ch_last = vol_chapters[-1]["index"] + 1
        vol_data = {
            "volume": vol_num,
            "chapterRange": [ch_first, ch_last],
            "chapters": vol_chapters,
        }
        filename = f"vol-{vol_num:03d}-ch{ch_first:03d}-{ch_last:03d}.json"
        self.save_json(vol_data, out / filename)

    def save_index(self, index_meta: list[dict], story_slug: str) -> None:
        """Save chapters index file."""
        out = self.output_dir(story_slug)
        self.save_json(index_meta, out / "chapters_index.json")

    def _save_progress(self, progress: dict, story_slug: str) -> None:
        out = self.output_dir(story_slug)
        with open(out / "_progress.json", "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

    def _load_progress(self, story_slug: str) -> dict | None:
        path = self.output_dir(story_slug) / "_progress.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _cleanup_progress(self, story_slug: str) -> None:
        path = self.output_dir(story_slug) / "_progress.json"
        if path.exists():
            path.unlink()

    def _get_next_vol_num(self, story_slug: str) -> int:
        out = self.output_dir(story_slug)
        if not out.exists():
            return 1
        max_vol = 0
        for f in out.glob("vol-*.json"):
            parts = f.name.split("-")
            if len(parts) >= 2 and parts[0] == "vol":
                try:
                    max_vol = max(max_vol, int(parts[1]))
                except ValueError:
                    pass
        return max_vol + 1

    def _rebuild_index(self, story_slug: str) -> list[dict]:
        out = self.output_dir(story_slug)
        if not out.exists():
            return []
        # Use dict keyed by index for dedup (later vols overwrite earlier)
        index_map: dict[int, dict] = {}
        for vol_file in sorted(out.glob("vol-*.json")):
            with open(vol_file, "r", encoding="utf-8") as f:
                vol_data = json.load(f)
            for ch in vol_data.get("chapters", []):
                index_map[ch["index"]] = {"index": ch["index"], "title": ch["title"]}
        index = sorted(index_map.values(), key=lambda x: x["index"])
        return index

    @abc.abstractmethod
    def crawl(self, start_url: str, **kwargs) -> list[dict]:
        """Crawl a story starting from the given URL. Returns list of chapter dicts."""
        ...
