import abc
import json
import os
import time
import random
import logging
import threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

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
        self.parallel_delay = (1.0, 2.0)
        self._thread_local = threading.local()
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

    def _get_thread_session(self) -> requests.Session:
        """Create or return a thread-local requests.Session."""
        if not hasattr(self._thread_local, "session"):
            s = requests.Session()
            s.headers.update(self.session.headers)
            self._thread_local.session = s
        return self._thread_local.session

    def fetch_parallel(self, url: str, retries: int = 3) -> BeautifulSoup | None:
        """Thread-safe fetch. Returns None on 404 (chapter not found)."""
        session = self._get_thread_session()
        for attempt in range(1, retries + 1):
            try:
                time.sleep(random.uniform(*self.parallel_delay))
                resp = session.get(url, timeout=15)
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                return BeautifulSoup(resp.text, "html.parser")
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    return None
                if attempt == retries:
                    raise
                logger.warning(f"Attempt {attempt}/{retries} failed for {url}: {e}")
                time.sleep(2 ** attempt)
            except requests.RequestException as e:
                if attempt == retries:
                    raise
                logger.warning(f"Attempt {attempt}/{retries} failed for {url}: {e}")
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

    def _predict_urls(self, start_url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]] | None:
        """Override in subclass to predict URLs without fetching. Returns None if not possible."""
        return None

    def crawl_parallel(self, start_url: str, start_index: int = 0, max_chapters: int = 0, workers: int = 3) -> list[dict]:
        """Crawl with parallel fetch when URL prediction is available."""
        slug = self._extract_slug(start_url)
        predicted = self._predict_urls(start_url, start_index, max_chapters)

        if predicted:
            logger.info(f"Predicted {len(predicted)} URLs, fetching with {workers} workers")
            return self._parallel_fetch(predicted, slug, workers)
        else:
            logger.info("No URL prediction available, using sequential crawl with reduced delay")
            old_delay = self.delay
            self.delay = (1.0, 1.5)
            try:
                return self.crawl(start_url, start_index=start_index, max_chapters=max_chapters)
            finally:
                self.delay = old_delay

    def _parallel_fetch(self, url_list: list[tuple[int, str]], slug: str, workers: int) -> list[dict]:
        """Fetch chapters in parallel using ThreadPoolExecutor."""
        results: dict[int, dict] = {}
        story_title = None
        failed = 0

        def worker(idx: int, url: str) -> tuple[dict | None, str | None]:
            soup = self.fetch_parallel(url)
            if soup is None:
                return None, None
            chapter = self._extract_chapter(soup)
            chapter["index"] = idx
            title = self._extract_story_title(soup)
            return chapter, title

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(worker, idx, url): idx for idx, url in url_list}

            for f in as_completed(futures):
                idx = futures[f]
                try:
                    chapter, title = f.result()
                    if chapter is None:
                        failed += 1
                    else:
                        results[idx] = chapter
                        if title and not story_title:
                            story_title = title
                        logger.info(f"  Ch {idx + 1}: {chapter['title']} ({len(chapter['paragraphs'])} para)")
                except Exception as e:
                    failed += 1
                    logger.error(f"  Ch {idx + 1} failed: {e}")

        if failed:
            logger.warning(f"{failed} chapters failed or not found (404)")

        if not results:
            logger.error("No chapters fetched successfully, skipping save")
            return []

        sorted_chapters = sorted(results.values(), key=lambda x: x["index"])
        self._save_chapters(sorted_chapters, slug, story_title)
        return self._rebuild_index(slug)

    def _save_chapters(self, chapters: list[dict], slug: str, story_title: str | None) -> None:
        """Sort chapters and save as volumes + index."""
        vol_num = self._get_next_vol_num(slug)
        buffer = []

        for ch in chapters:
            buffer.append(ch)
            if len(buffer) >= self.CHAPTERS_PER_VOL:
                self.save_volume(buffer, vol_num, slug)
                logger.info(f"Saved vol {vol_num} ({len(buffer)} chapters)")
                vol_num += 1
                buffer = []

        if buffer:
            self.save_volume(buffer, vol_num, slug)
            logger.info(f"Saved vol {vol_num} ({len(buffer)} chapters)")

        all_index = self._rebuild_index(slug)
        if all_index:
            self.save_index(all_index, slug)
        if story_title:
            out = self.output_dir(slug)
            self.save_json({"story_title": story_title}, out / "metadata.json")

        logger.info(f"Total: {len(chapters)} chapters saved")

    @abc.abstractmethod
    def crawl(self, start_url: str, **kwargs) -> list[dict]:
        """Crawl a story starting from the given URL. Returns list of chapter dicts."""
        ...
