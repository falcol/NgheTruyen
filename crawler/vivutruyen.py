"""Crawler for vivutruyen.com — HTML chapters, AJAX chapter list."""

import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler, logger

BASE_URL = "https://vivutruyen.com/"
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_CHAPTER_URL = re.compile(
    r"vivutruyen\.com/truyen/([^/?#]+)/chuong-(\d+)-"
)
_STORY_ID = re.compile(r"/truyen/([^/?#]+)/(\d+)/\d+")
_CHAP_HREF = re.compile(r"/truyen/([^/?#]+)/chuong-(\d+)-[^\"'#?\s]+")


def _clean_line(text: str) -> str:
    text = _INVISIBLE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


class VivutruyenCrawler(BaseCrawler):
    """Crawl vivutruyen.com from a story URL or a chapter URL.

    The chapter list after page 1 is an AJAX partial
    (X-Requested-With). A normal GET of /truyen/{slug}/{id}/{page}
    returns the homepage, so catalog pages must send that header.
    Chapter body is in div.truyen, split on <br>.
    """

    BASE_URL = BASE_URL
    READING_PAUSE_EVERY_CHUNKS = 0

    def __init__(self, dest_dir: str | None = None):
        super().__init__(site_name="vivutruyen", dest_dir=dest_dir)
        self.delay = (0.5, 1.0)
        self.parallel_delay = (0.35, 0.8)
        self._catalog: list[dict] | None = None

    def _extract_slug(self, url: str) -> str:
        match = _CHAPTER_URL.search(url) or re.search(
            r"vivutruyen\.com/truyen/([^/?#]+)", url
        )
        if match:
            return match.group(1)
        return "unknown"

    def _extract_story_title(self, soup) -> str | None:
        node = soup.select_one("h1.current-book a") or soup.select_one("h1")
        if not node:
            return None
        title = node.get_text(strip=True)
        return title or None

    def _extract_chapter(self, soup) -> dict:
        title_el = soup.select_one("span.current-chapter") or soup.find("h1")
        title = title_el.get_text(strip=True) if title_el else "Unknown"
        title = _clean_line(title) or title

        content = soup.select_one("div.truyen")
        if not content:
            raise ValueError("Could not find div.truyen")

        for tag in content.find_all(["script", "style", "ins", "iframe"]):
            tag.decompose()
        for br in content.find_all("br"):
            br.replace_with("\n")

        lines = []
        for raw in content.get_text("\n").splitlines():
            text = _clean_line(raw)
            if text:
                lines.append(text)
        if lines and lines[0] == title:
            lines.pop(0)
        if not lines:
            raise ValueError(f"Empty content for {title}")
        return {"title": title, "paragraphs": lines}

    def _next_chapter_url(self, soup) -> str | None:
        link = soup.select_one("a.next")
        if not link:
            return None
        href = link.get("href") or ""
        if "chuong-" not in href:
            return None
        return urljoin(BASE_URL, href)

    def _fetch_ajax(self, url: str) -> BeautifulSoup:
        for attempt in range(1, 4):
            try:
                self._rate_limit(self.delay)
                headers = self._pick_headers(referer=BASE_URL)
                headers["X-Requested-With"] = "XMLHttpRequest"
                resp = self.session.get(url, timeout=20, headers=headers)
                if resp.status_code in (429, 503, 403):
                    self._on_rate_limited()
                    if attempt == 3:
                        resp.raise_for_status()
                    time.sleep(min(30.0, 3.0 * attempt))
                    continue
                resp.raise_for_status()
                self._on_success()
                return BeautifulSoup(resp.text, "html.parser")
            except requests.RequestException as e:
                if attempt == 3:
                    raise
                logger.warning(f"List page attempt {attempt}/3 failed for {url}: {e}")
        raise RuntimeError(f"Failed to fetch list page {url}")

    def _chapter_links(self, soup, slug: str) -> list[dict]:
        found: dict[int, str] = {}
        for anchor in soup.find_all("a", href=True):
            href = anchor["href"]
            match = _CHAP_HREF.search(href)
            if not match or match.group(1) != slug:
                continue
            number = int(match.group(2))
            found.setdefault(number, urljoin(BASE_URL, href))
        return [{"num": num, "url": found[num]} for num in sorted(found)]

    def _story_id(self, soup, slug: str) -> str | None:
        for anchor in soup.find_all("a", href=True):
            match = _STORY_ID.search(anchor["href"])
            if match and match.group(1) == slug:
                return match.group(2)
        button = soup.select_one("a.btn-dschuong")
        if button:
            data_url = button.get("data-url") or ""
            parts = data_url.strip("/").split("/")
            if len(parts) >= 2 and parts[0] == slug and parts[1].isdigit():
                return parts[1]
        return None

    def _load_catalog(self, url: str) -> list[dict]:
        if self._catalog is not None:
            return self._catalog
        slug = self._extract_slug(url)
        story_url = urljoin(BASE_URL, f"truyen/{slug}")
        soup = self.fetch(story_url)
        story_id = self._story_id(soup, slug)
        chapters: list[dict] = []
        seen: set[int] = set()
        if story_id:
            page = 1
            while page <= 500:
                list_soup = self._fetch_ajax(
                    urljoin(BASE_URL, f"truyen/{slug}/{story_id}/{page}")
                )
                batch = self._chapter_links(list_soup, slug)
                fresh = [item for item in batch if item["num"] not in seen]
                if not fresh:
                    break
                for item in fresh:
                    seen.add(item["num"])
                chapters.extend(fresh)
                page += 1
        if not chapters:
            chapters = self._chapter_links(soup, slug)
        chapters.sort(key=lambda item: item["num"])
        self._catalog = chapters
        logger.info(f"Catalog: {len(chapters)} chapters for {slug}")
        return chapters

    def _predict_urls(
        self, start_url: str, start_index: int, max_chapters: int
    ) -> list[tuple[int, str]] | None:
        catalog = self._load_catalog(start_url)
        if not catalog:
            logger.warning("No chapters to crawl")
            return []
        match = _CHAPTER_URL.search(start_url)
        if match:
            chapter_no = int(match.group(2))
            start_pos = next(
                (i for i, item in enumerate(catalog) if item["num"] == chapter_no),
                0,
            )
        else:
            start_pos = start_index
        selected = catalog[start_pos:]
        if max_chapters > 0:
            selected = selected[:max_chapters]
        urls = [(item["num"] - 1, item["url"]) for item in selected]
        if urls:
            logger.info(
                f"Predicted {len(urls)} chapter URLs "
                f"(index {urls[0][0]}..{urls[-1][0]})"
            )
        return urls

    def fetch_parallel(self, url: str, retries: int = 3) -> BeautifulSoup | None:
        soup = super().fetch_parallel(url, retries)
        if soup is not None and soup.select_one("div.truyen") is None:
            if _CHAPTER_URL.search(url):
                logger.info(f"Not a chapter page: {url}")
                return None
        return soup
