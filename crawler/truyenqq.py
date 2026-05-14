import re
from urllib.parse import urljoin

from .base import BaseCrawler, logger

BASE_URL = "https://truyenqq.vn/"


class TruyenQQCrawler(BaseCrawler):
    """Crawler for truyenqq.vn doc-convert (text novel) pages."""

    BASE_URL = BASE_URL

    def __init__(self, dest_dir: str | None = None):
        super().__init__(site_name="truyenqq", dest_dir=dest_dir)

    NOISE_PATTERNS = [
        re.compile(r"^Ng.+i đăng:"),           # "Nguoi dang: <user>"
        re.compile(r"^Bạn đang đọc truyện"),    # Site attribution
        re.compile(r"\.com\.vn$|\.com$|\.net$"), # Domain names
    ]

    def _extract_chapter(self, soup) -> dict:
        """Extract chapter title and paragraphs from a chapter page."""
        # Title from h2
        h2 = soup.find("h2")
        title = h2.get_text(strip=True) if h2 else "Unknown"

        # Content from #noidungchap
        noidung = soup.find(id="noidungchap")
        if not noidung:
            raise ValueError("Could not find #noidungchap")

        # Remove recommendation divs before extracting text
        for div in noidung.find_all("div"):
            div.decompose()

        text = noidung.get_text(separator="\n").strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        # Strip noise lines from start and end
        while lines and any(p.search(lines[0]) for p in self.NOISE_PATTERNS):
            lines.pop(0)
        while lines and any(p.search(lines[-1]) for p in self.NOISE_PATTERNS):
            lines.pop()

        return {"title": title, "paragraphs": lines}

    def _extract_story_title(self, soup) -> str | None:
        """Extract the story title from the page header."""
        title_node = soup.select_one(
            "body > div.page-container > div.page-content-wrapper > div > div > div > "
            "div.portlet.box.blue-soft > div.portlet-title > div > h1"
        ) or soup.select_one("div.caption > h1.read")

        if not title_node:
            return None

        title = title_node.get_text(" ", strip=True)
        return re.sub(r"^Đọc truyện\s+", "", title).strip()

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

