import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseCrawler, logger

BASE_URL = "https://truyenfullmoi.com/"


class TruyenfullmoiCrawler(BaseCrawler):
    """Crawler for truyenfullmoi.com chapter pages.

    Key difference: non-existent chapters redirect to homepage (not 404).
    Detected by checking #chapter-c presence in soup.
    """

    BASE_URL = BASE_URL

    def __init__(self, dest_dir: str | None = None):
        super().__init__(site_name="truyenfullmoi", dest_dir=dest_dir)

    def _extract_chapter(self, soup) -> dict:
        """Extract chapter title and paragraphs from a chapter page."""
        title_el = soup.select_one(".chapter-title") or soup.find("h2")
        title = title_el.get_text(strip=True) if title_el else "Unknown"
        title = re.sub(r"^Chương\s+\d+[:.]\s*", "", title).strip() or title

        content = soup.select_one("#chapter-c")
        if not content:
            raise ValueError("Could not find #chapter-c")

        for tag in content.find_all(["script", "ins", "iframe", "div"]):
            tag.decompose()

        text = content.get_text(separator="\n").strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        return {"title": title, "paragraphs": lines}

    def _extract_story_title(self, soup) -> str | None:
        """Extract the story title from the story page."""
        title_node = soup.select_one("h3.title") or soup.select_one("h1")
        return title_node.get_text(strip=True) if title_node else None

    def _next_chapter_url(self, soup) -> str | None:
        """Find the next chapter link from #next_chap."""
        a = soup.select_one("#next_chap")
        if not a:
            return None
        href = a.get("href", "")
        if not href:
            return None
        next_url = urljoin(BASE_URL, href)
        # If next points to homepage, end of story
        if next_url.rstrip("/") == BASE_URL.rstrip("/"):
            return None
        return next_url

    def _extract_slug(self, url: str) -> str:
        """Extract story slug from URL, stripping .NNN suffix.

        Story page: /ho-hoa-cao-thu-tai-do-thi.148
        Chapter page: /ho-hoa-cao-thu-tai-do-thi/chuong-1.html
        """
        match = re.search(r"truyenfullmoi\.com/([^/]+)/chuong-", url)
        if match:
            return match.group(1)
        match = re.search(r"truyenfullmoi\.com/([^.?/]+)", url)
        if match:
            return match.group(1)
        return "unknown"

    def _predict_urls(self, start_url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]] | None:
        """Predict URLs: /{slug}/chuong-{N}.html"""
        slug = self._extract_slug(start_url)
        match = re.search(r"chuong-(\d+)", start_url)
        if not match:
            return None

        start_ch = int(match.group(1))
        limit = max_chapters if max_chapters > 0 else 2000
        urls = []

        for i in range(limit):
            ch_num = start_ch + i
            url = f"{BASE_URL}{slug}/chuong-{ch_num}.html"
            urls.append((start_index + i, url))

        return urls

    def fetch_parallel(self, url: str, retries: int = 3) -> BeautifulSoup | None:
        """Override to detect homepage redirect via missing #chapter-c."""
        soup = super().fetch_parallel(url, retries)
        if soup is not None and not soup.find(id="chapter-c"):
            logger.info(f"Not a chapter page (redirect?): {url}")
            return None
        return soup
