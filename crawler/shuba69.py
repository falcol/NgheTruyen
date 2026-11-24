"""Crawler for the numbered chapters on 69shuba.com."""

import re
import subprocess
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseCrawler, logger


class Shuba69Crawler(BaseCrawler):
    BASE_URL = "https://www.69shuba.com/"
    CHAPTERS_PER_VOL = 10
    READING_PAUSE_EVERY_CHUNKS = 0

    def __init__(self, dest_dir=None):
        super().__init__(site_name="shuba69", dest_dir=dest_dir)
        self._story_title = None
        self.parallel_delay = (4.0, 6.0)

    def warmup(self):
        pass

    def _request(self, url, session, delay_range, retries, allow_404, referer=None):
        for attempt in range(retries):
            self._rate_limit(delay_range)
            result = subprocess.run(
                ["curl", "-sS", "-L", "--socks5-hostname", "127.0.0.1:9050",
                 "--max-time", "25", "-w", "\n%{http_code}",
                 "-H", "User-Agent: Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                 "-H", f"Referer: {referer or self.BASE_URL}", url],
                capture_output=True, check=True,
            )
            body, status = result.stdout.rsplit(b"\n", 1)
            if status == b"404" and allow_404:
                return None
            if status == b"200":
                return BeautifulSoup(body.decode("gb18030", errors="replace"), "html.parser")
            if status != b"429" or attempt + 1 == retries:
                raise ValueError(f"HTTP {status.decode(errors='replace')} for {url}")
            logger.warning("HTTP 429: waiting 60 seconds before retry")
            time.sleep(60)

    def _extract_slug(self, url):
        match = re.search(r"/(?:book|txt)/(\d+)(?:/|$)", url)
        if not match:
            raise ValueError(f"Invalid 69shuba book URL: {url}")
        return match.group(1)

    def _extract_story_title(self, soup):
        return self._story_title

    def _extract_chapter(self, soup):
        content = soup.select_one("div.txtnav")
        title = content.select_one("h1") if content else None
        if not content or not title:
            raise ValueError("Missing chapter title or content")
        title_text = title.get_text(strip=True)
        for tag in content.select("h1, .txtinfo, #txtright, .contentadv, script, style, ins"):
            tag.decompose()
        paragraphs = [line.strip() for line in content.get_text("\n").splitlines()]
        paragraphs = [line for line in paragraphs if line and line != title_text and line not in ("(本章完)", "（本章完）")]
        if sum(map(len, paragraphs)) < 80:
            raise ValueError(f"Chapter content too short: {title_text}")
        return {"title": title_text, "paragraphs": paragraphs}

    def _next_chapter_url(self, soup):
        return None

    def _predict_urls(self, start_url, start_index, max_chapters):
        book_id = self._extract_slug(start_url)
        soup = self.fetch(urljoin(self.BASE_URL, f"book/{book_id}/"))
        heading = soup.select_one("#catalog h1")
        if heading:
            self._story_title = heading.get_text(strip=True).removesuffix("最新章节")
        chapters = {}
        for link in soup.select("#catalog a[href]"):
            match = re.match(r"第(\d+)章", link.get_text(strip=True))
            href = urljoin(self.BASE_URL, link["href"])
            if match and re.search(rf"/txt/{book_id}/\d+/?$", href):
                index = int(match.group(1)) - 1
                if index in chapters:
                    raise ValueError(f"Duplicate chapter number: {index + 1}")
                chapters[index] = href
        if not chapters:
            raise ValueError("No numbered chapters in catalog")
        selected = [(index, chapters[index]) for index in sorted(chapters) if index >= start_index]
        if max_chapters:
            selected = selected[:max_chapters]
        logger.info(f"Catalog: {len(chapters)} numbered chapters")
        return selected

    def crawl(self, start_url, start_index=0, max_chapters=0):
        return self.crawl_parallel(start_url, start_index, max_chapters)

    def crawl_parallel(self, start_url, start_index=0, max_chapters=0, workers=1):
        return super().crawl_parallel(start_url, start_index, max_chapters, workers=1)
