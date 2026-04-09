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
