"""truyenc.net crawler. Zero-based index i corresponds to chuong-(i + 1)."""

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler, _HTML_PARSER, logger
from .tor_proxy import TorProxyMixin


class TruyencCrawler(TorProxyMixin, BaseCrawler):
    BASE_URL = "https://truyenc.net/"
    IMAGE_PLACEHOLDER = "*Chương này có nội dung ảnh"

    def __init__(self, dest_dir: str | None = None):
        super().__init__(site_name="truyenc", dest_dir=dest_dir)

    def _build_session(self):
        session = super()._build_session()
        if not self._tor_enabled:
            raise RuntimeError("Tor SOCKS proxy is unavailable")
        return session

    def _save_cookies(self):
        pass

    def _request(self, url, session, delay_range, retries, allow_404, referer=None):
        for attempt in range(1, retries + 1):
            try:
                self._rate_limit(delay_range)
                resp = session.get(url, timeout=25, headers=self._pick_headers(referer))
                if resp.status_code == 404:
                    if allow_404:
                        return None
                    resp.raise_for_status()
                soup = BeautifulSoup(resp.text, _HTML_PARSER)
                article = soup.select_one("article.reader-content")
                blocked = resp.status_code in (403, 429, 503) or resp.headers.get("cf-mitigated") or not article or not article.get_text(strip=True)
                if blocked:
                    logger.warning("Attempt %s/%s %s: HTTP %s, cf-mitigated=%s, bytes=%s, content-type=%s", attempt, retries, url, resp.status_code, resp.headers.get("cf-mitigated"), len(resp.content), resp.headers.get("content-type"))
                    if resp.status_code in (403, 429, 503):
                        self._on_rate_limited()
                    else:
                        self._rotate_tor_circuit()
                    if attempt == retries:
                        raise requests.RequestException(f"Chapter unavailable after {retries} attempts: {url}")
                    wait = self._parse_retry_after(resp)
                    time.sleep(wait if wait is not None else min(60.0, 5.0 * (2 ** attempt)) if resp.status_code in (403, 429, 503) else 2 ** attempt)
                    continue
                resp.raise_for_status()
                self._on_success()
                return soup
            except requests.RequestException as exc:
                if attempt == retries:
                    raise
                logger.warning("Attempt %s/%s failed for %s: %s", attempt, retries, url, exc)
                self._rotate_tor_circuit()
                time.sleep(2 ** attempt)
        return None

    def _extract_slug(self, url):
        match = re.search(r"/truyen/([^/]+)/chuong-\d+", url)
        if not match:
            raise ValueError(f"Invalid chapter URL: {url}")
        return match.group(1)

    def _extract_chapter(self, soup):
        article = soup.select_one("article.reader-content")
        header = article.find_previous_sibling("header") if article else None
        title = header.select_one("h1") if header else None
        if not article or not title:
            raise ValueError("Missing chapter title or body")
        paragraphs = [line.strip() for line in article.get_text("\n").splitlines() if line.strip()]
        if not paragraphs:
            raise ValueError("Empty chapter body")
        if article.get_text(strip=True).startswith(self.IMAGE_PLACEHOLDER):
            paragraphs = []
        return {"title": re.sub(r"^(Chương\s+\d+:\s*)(?:Chương\s+\d+:\s*)+", r"\1", title.get_text(" ", strip=True), flags=re.I), "paragraphs": paragraphs}

    def _save_image_chapters(self, slug):
        out = self.output_dir(slug)
        numbers = set()
        for path in sorted(out.glob("vol-*.json*")):
            logical = path.with_suffix("") if path.suffix == ".gz" else path
            for chapter in self._read_json_any(logical)["chapters"]:
                if not chapter["paragraphs"]:
                    numbers.add(chapter["index"] + 1)
        with open(out / "image_chapters.json", "w", encoding="utf-8") as f:
            json.dump(sorted(numbers), f)

    def save_volume(self, vol_chapters, vol_num, story_slug):
        super().save_volume(vol_chapters, vol_num, story_slug)
        self._save_image_chapters(story_slug)

    def _extract_story_title(self, soup):
        article = soup.select_one("article.reader-content")
        header = article.find_previous_sibling("header") if article else None
        title = header.select_one("p span") if header else None
        return title.get_text(strip=True) if title else None

    def _next_chapter_url(self, soup):
        link = soup.select_one('a[title^="Chương sau"][href]')
        return urljoin(self.BASE_URL, link["href"]) if link else None

    def _chapter_url(self, url, index):
        self._extract_slug(url)
        return re.sub(r"chuong-\d+(?=/?(?:\?|$))", f"chuong-{index + 1}", url)

    def crawl(self, start_url, start_index=0, max_chapters=0):
        slug = self._extract_slug(start_url)
        self._save_image_chapters(slug)
        progress = self._load_progress(slug)
        if progress and start_index > progress.get("next_index", 0):
            self._cleanup_progress(slug)
        return super().crawl(self._chapter_url(start_url, start_index), start_index, max_chapters)

    def crawl_parallel(self, start_url, start_index=0, max_chapters=0, workers=3):
        self.parallel_delay = (1.0, 2.0)
        self.warmup()
        slug = self._extract_slug(start_url)
        self._save_image_chapters(slug)
        saved_index = self._rebuild_index(slug)
        existing = {item["index"] for item in saved_index}
        if existing and not max_chapters and existing == set(range(max(existing) + 1)):
            last = self.fetch_parallel(self._chapter_url(start_url, max(existing)))
            if last is not None and not self._next_chapter_url(last):
                self.save_index(saved_index, slug)
                return saved_index
        story_title = None
        vol_num = self._get_next_vol_num(slug)
        buffer = []
        count = 0
        index = start_index
        done = False
        with ThreadPoolExecutor(max_workers=max(1, min(workers, 3))) as pool:
            while not done and (not max_chapters or count < max_chapters):
                size = min(max(1, min(workers, 3)), max_chapters - count) if max_chapters else max(1, min(workers, 3))
                indices = list(range(index, index + size))
                futures = {i: pool.submit(self.fetch_parallel, self._chapter_url(start_url, i)) for i in indices if i not in existing}
                for i in indices:
                    if i in existing:
                        continue
                    soup = futures[i].result()
                    if soup is None:
                        done = True
                        break
                    chapter = self._extract_chapter(soup)
                    chapter["index"] = i
                    buffer.append(chapter)
                    story_title = story_title or self._extract_story_title(soup)
                    logger.info("  Ch %s: %s (%s paragraphs)", i + 1, chapter["title"], len(chapter["paragraphs"]))
                    if len(buffer) == self.CHAPTERS_PER_VOL:
                        self.save_volume(buffer, vol_num, slug)
                        self._bump_vol_cache(slug)
                        vol_num += 1
                        buffer = []
                    if not self._next_chapter_url(soup):
                        done = True
                        break
                count += size
                index += size
        if buffer:
            self.save_volume(buffer, vol_num, slug)
        result = self._rebuild_index(slug)
        if result:
            self.save_index(result, slug)
        if story_title:
            self.save_json({"story_title": story_title}, self.output_dir(slug) / "metadata.json")
        self._save_cookies()
        return result
