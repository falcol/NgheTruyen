"""Crawler for uukanshu.cc — one book page lists every chapter."""

import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseCrawler, logger
from .tor_proxy import TorProxyMixin

BASE_URL = "https://uukanshu.cc/"
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_BOOK_URL = re.compile(r"uukanshu\.cc/book/(\d+)")
_CHAPTER_HREF = re.compile(r"/book/(\d+)/(\d+)\.html")
_DONE = re.compile(r"^\(?本章完\)?$")


def _clean_line(text: str) -> str:
    text = _INVISIBLE.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


class UukanshuCrawler(TorProxyMixin, BaseCrawler):
    """Crawl uukanshu.cc from a book URL or a chapter URL.

    The book page lists every chapter in `dd` links. Chapter ids are not
    sequential, so the catalog is scraped once. Body text is `div.readcotent`.
    Routes through Tor SOCKS :9050. A 429 rotates that thread's circuit.
    """

    BASE_URL = BASE_URL
    READING_PAUSE_EVERY_CHUNKS = 0

    def __init__(self, dest_dir: str | None = None):
        super().__init__(site_name="uukanshu", dest_dir=dest_dir)
        self.delay = (0.8, 1.4)
        self.parallel_delay = (0.6, 1.1)
        self._catalog: list[dict] | None = None
        self._story_title: str | None = None

    def _pick_headers(self, referer: str | None = None) -> dict[str, str]:
        headers = super()._pick_headers(referer)
        headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
        return headers

    def _book_id(self, url: str) -> str:
        match = _BOOK_URL.search(url)
        if not match:
            raise ValueError(f"Not an uukanshu book URL: {url}")
        return match.group(1)

    def _extract_slug(self, url: str) -> str:
        return self._book_id(url)

    def _extract_story_title(self, soup) -> str | None:
        if self._story_title:
            return self._story_title
        node = soup.select_one("h1")
        if not node:
            return None
        title = _clean_line(node.get_text(" ", strip=True))
        if title.startswith("第") and "章" in title[:8]:
            return None
        return title or None

    def _extract_chapter(self, soup) -> dict:
        title_el = soup.select_one("h1")
        title = _clean_line(title_el.get_text(" ", strip=True)) if title_el else ""
        content = soup.select_one("div.readcotent")
        if content is None:
            raise ValueError("Could not find div.readcotent")
        for tag in content.find_all(["script", "style", "ins", "iframe"]):
            tag.decompose()
        for br in content.find_all("br"):
            br.replace_with("\n")
        lines = []
        for raw in content.get_text("\n").splitlines():
            text = _clean_line(raw)
            if not text or _DONE.match(text):
                continue
            if text == title:
                continue
            lines.append(text)
        if not lines:
            raise ValueError(f"Empty content for {title or 'chapter'}")
        return {"title": title or lines[0], "paragraphs": lines}

    def _next_chapter_url(self, soup) -> str | None:
        for link in soup.find_all("a", href=True):
            if "下一" not in link.get_text(strip=True):
                continue
            href = link["href"]
            if _CHAPTER_HREF.search(href):
                return urljoin(BASE_URL, href)
        return None

    def _load_catalog(self, url: str) -> list[dict]:
        if self._catalog is not None:
            return self._catalog
        book_id = self._book_id(url)
        soup = self.fetch(urljoin(BASE_URL, f"book/{book_id}/"))
        heading = soup.find("h1")
        if heading:
            self._story_title = _clean_line(heading.get_text(" ", strip=True)) or None
        chapters = []
        seen: set[str] = set()
        for item in soup.find_all("dd"):
            link = item.find("a", href=True)
            if not link:
                continue
            href = link["href"]
            match = _CHAPTER_HREF.search(href)
            if not match or match.group(1) != book_id:
                continue
            full = urljoin(BASE_URL, href)
            if full in seen:
                continue
            seen.add(full)
            chapters.append({
                "url": full,
                "title": _clean_line(link.get_text(" ", strip=True)),
            })
        self._catalog = chapters
        logger.info(f"Catalog: {len(chapters)} chapters for book {book_id}")
        return chapters

    def _predict_urls(
        self, start_url: str, start_index: int, max_chapters: int
    ) -> list[tuple[int, str]] | None:
        catalog = self._load_catalog(start_url)
        if not catalog:
            logger.warning("No chapters to crawl")
            return []
        start_pos = 0
        match = _CHAPTER_HREF.search(start_url)
        if match:
            chapter_id = match.group(2)
            start_pos = next(
                (i for i, item in enumerate(catalog) if item["url"].endswith(f"/{chapter_id}.html")),
                0,
            )
        elif start_index:
            start_pos = start_index
        selected = catalog[start_pos:]
        if max_chapters > 0:
            selected = selected[:max_chapters]
        urls = [(start_pos + offset, item["url"]) for offset, item in enumerate(selected)]
        if urls:
            logger.info(
                f"Predicted {len(urls)} chapter URLs (index {urls[0][0]}..{urls[-1][0]})"
            )
        return urls

    def fetch_parallel(self, url: str, retries: int = 3) -> BeautifulSoup | None:
        soup = super().fetch_parallel(url, retries)
        if soup is not None and _CHAPTER_HREF.search(url) and soup.select_one("div.readcotent") is None:
            logger.info(f"Not a chapter page: {url}")
            return None
        return soup
