import re
from urllib.parse import urljoin

from .base import BaseCrawler, logger

BASE_URL = "https://metruyencv.xyz/"


class MetruyencvCrawler(BaseCrawler):
    """Crawler for metruyencv.xyz chapter pages."""

    BASE_URL = BASE_URL

    def __init__(self, dest_dir: str | None = None):
        super().__init__(site_name="metruyencv", dest_dir=dest_dir)

    def _extract_chapter(self, soup) -> dict:
        """Extract chapter title and paragraphs from a chapter page."""
        # Title from breadcrumb active li
        active_li = soup.select_one("div.c-breadcrumb-wrapper li.active")
        title = active_li.get_text(strip=True) if active_li else "Unknown"
        title = re.sub(r"^Chương\s+\d+[:.]\s*", "", title).strip() or title

        content = soup.select_one("div.reading-content")
        if not content:
            raise ValueError("Could not find div.reading-content")

        text = content.get_text(separator="\n").strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # First line is usually "Chương X: title" - skip it
        if lines and re.match(r"^Chương\s+\d+", lines[0]):
            lines = lines[1:]

        return {"title": title, "paragraphs": lines}

    def _extract_story_title(self, soup) -> str | None:
        """Extract the story title from breadcrumb."""
        bc = soup.select_one("div.c-breadcrumb-wrapper")
        if not bc:
            return None
        a = bc.find("a")
        return a.get_text(strip=True) if a else None

    def _next_chapter_url(self, soup) -> str | None:
        """Find the next chapter link from div.nav-next."""
        nav_next = soup.select_one("div.nav-next")
        if not nav_next:
            return None
        a = nav_next.find("a")
        if not a:
            return None
        href = a.get("href", "")
        if not href:
            return None
        return urljoin(BASE_URL, href)

    def _extract_slug(self, url: str) -> str:
        """Extract story slug from URL: /truyen/{slug}/chuong-..."""
        match = re.search(r"metruyencv\.xyz/truyen/(.+?)/chuong-", url)
        if match:
            return match.group(1)
        # Fallback: try without chuong-
        match = re.search(r"metruyencv\.xyz/truyen/(.+?)/", url)
        return match.group(1) if match else "unknown"

    def _predict_urls(self, start_url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]] | None:
        """Predict URLs for metruyencv: /truyen/{slug}/chuong-{N}/"""
        slug = self._extract_slug(start_url)
        match = re.search(r"chuong-(\d+)", start_url)
        if not match:
            return None

        start_ch = int(match.group(1))
        limit = max_chapters if max_chapters > 0 else 2000
        urls = []

        for i in range(limit):
            ch_num = start_ch + i
            url = f"{BASE_URL}truyen/{slug}/chuong-{ch_num}/"
            urls.append((start_index + i, url))

        return urls

