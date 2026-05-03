import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseCrawler, logger

BASE_URL = "https://metruyenchu.com.vn/"
CHAPTER_LIST_API = "https://metruyenchu.com.vn/get/listchap/"


class MetruyenchuCrawler(BaseCrawler):
    """Crawler for metruyenchu.com.vn chapter pages."""

    def __init__(self, dest_dir: str | None = None):
        super().__init__(site_name="metruyenchu", dest_dir=dest_dir)
        self._api_headers = {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/html",
            "Referer": BASE_URL,
        }

    def _extract_chapter(self, soup) -> dict:
        """Extract chapter title and paragraphs from a chapter page."""
        h2 = soup.find("h2")
        title = h2.get_text(strip=True) if h2 else "Unknown"

        truyen = soup.select_one("div.vung-doc > div.truyen")
        if not truyen:
            raise ValueError("Could not find div.truyen content")

        text = truyen.get_text(separator="\n").strip()
        lines = [line.strip() for line in text.split("\n") if line.strip()]

        return {"title": title, "paragraphs": lines}

    def _extract_story_title(self, soup) -> str | None:
        """Extract the story title from <h1>."""
        h1 = soup.find("h1")
        return h1.get_text(strip=True) if h1 else None

    def _next_chapter_url(self, soup) -> str | None:
        """Find the next chapter link from #gotochap navigation."""
        gotochap = soup.find(id="gotochap")
        if not gotochap:
            return None

        next_link = gotochap.find("a", class_="next")
        if not next_link:
            return None

        href = next_link.get("href", "")
        if not href or href == "#" or "disabled" in next_link.get("class", []):
            return None

        return urljoin(BASE_URL, href)

    def _extract_slug(self, url: str) -> str:
        """Extract story slug from URL: /{slug}/chuong-{num}-{id}"""
        match = re.search(r"metruyenchu\.com\.vn/(.+?)/chuong-", url)
        return match.group(1) if match else "unknown"

    def _get_story_id(self, slug: str) -> int | None:
        """Fetch story page and extract story_id from onclick='page(ID,N)'."""
        resp = self.session.get(
            f"{BASE_URL}{slug}",
            headers={"Accept": "text/html"},
            timeout=15,
        )
        resp.raise_for_status()
        match = re.search(r"page\((\d+),\s*\d+\)", resp.text)
        return int(match.group(1)) if match else None

    def _fetch_chapter_list(self, story_id: int, max_chapters: int = 0) -> list[str]:
        """Fetch all chapter URLs via AJAX pagination API."""
        urls: list[str] = []
        page_num = 1

        while True:
            resp = self.session.get(
                f"{CHAPTER_LIST_API}{story_id}",
                params={"page": page_num},
                headers=self._api_headers,
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json().get("data", "")
            if not data:
                break

            soup = BeautifulSoup(data, "html.parser")
            chapter_links = [
                a for a in soup.select("a")
                if a.get("href", "").startswith("/")
            ]

            if not chapter_links:
                break

            for a in chapter_links:
                full_url = urljoin(BASE_URL, a["href"])
                urls.append(full_url)
                if max_chapters and len(urls) >= max_chapters:
                    return urls

            logger.info(f"Chapter list page {page_num}: +{len(chapter_links)} URLs (total: {len(urls)})")
            page_num += 1

            # Safety: if page returned fewer than 100, it's the last page
            if len(chapter_links) < 100:
                break

        return urls

    def _predict_urls(self, start_url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]] | None:
        """Fetch full chapter list via API, then return indexed URLs."""
        slug = self._extract_slug(start_url)

        story_id = self._get_story_id(slug)
        if not story_id:
            logger.warning("Could not extract story_id, falling back to sequential")
            return None

        logger.info(f"Story ID: {story_id}, fetching chapter list...")
        chapter_urls = self._fetch_chapter_list(story_id, max_chapters=max_chapters)
        if not chapter_urls:
            return None

        logger.info(f"Collected {len(chapter_urls)} chapter URLs from API")
        return [(start_index + i, url) for i, url in enumerate(chapter_urls)]

    def crawl(self, start_url: str, start_index: int = 0, max_chapters: int = 0) -> list[dict]:
        """
        Crawl all chapters starting from start_url by following 'next' links.
        Saves each volume to disk as soon as it's complete.
        Auto-saves buffer on crash/interrupt. Resumes from last saved progress.

        Args:
            start_url: URL of the first chapter to crawl.
            start_index: Starting chapter index number (default 0).
            max_chapters: Max chapters to crawl, 0 = unlimited.
        """
        slug = self._extract_slug(start_url)

        # Resume from previous crawl if available
        progress = self._load_progress(slug)
        if progress and progress.get("next_url"):
            url = progress["next_url"]
            index = progress["next_index"]
            story_title = progress.get("story_title")
            logger.info(f"Resuming from chapter {index + 1}: {url}")
        else:
            url = start_url
            index = start_index
            story_title = None
            logger.info(f"Starting crawl: {slug}")
            logger.info(f"First URL: {url}")

        vol_num = self._get_next_vol_num(slug)
        buffer = []
        session_count = 0
        completed = False

        try:
            while url:
                logger.info(f"Crawling chapter {index + 1}: {url}")

                try:
                    soup = self.fetch(url)
                    if story_title is None:
                        story_title = self._extract_story_title(soup)
                        if story_title:
                            logger.info(f"Story title: {story_title}")
                    chapter = self._extract_chapter(soup)
                    chapter["index"] = index
                    buffer.append(chapter)
                    session_count += 1
                    logger.info(f"  -> {chapter['title']} ({len(chapter['paragraphs'])} paragraphs)")
                except Exception as e:
                    logger.error(f"Failed to crawl {url}: {e}")
                    break

                # Flush volume when buffer is full
                if len(buffer) >= self.CHAPTERS_PER_VOL:
                    self.save_volume(buffer, vol_num, slug)
                    logger.info(f"Saved vol {vol_num} ({len(buffer)} chapters)")
                    vol_num += 1
                    buffer = []

                # Save progress for resume
                next_url = self._next_chapter_url(soup)
                self._save_progress({
                    "next_url": next_url,
                    "next_index": index + 1,
                    "story_title": story_title,
                }, slug)

                if max_chapters and session_count >= max_chapters:
                    logger.info(f"Reached max_chapters limit ({max_chapters})")
                    break

                url = next_url
                index += 1
            else:
                completed = True

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            # Save remaining buffer (handles crash/interrupt)
            if buffer:
                self.save_volume(buffer, vol_num, slug)
                logger.info(f"Saved partial vol {vol_num} ({len(buffer)} chapters)")

            # Rebuild index from all saved volumes
            all_index = self._rebuild_index(slug)
            if all_index:
                self.save_index(all_index, slug)
            if story_title:
                out = self.output_dir(slug)
                self.save_json({"story_title": story_title}, out / "metadata.json")

            if completed:
                self._cleanup_progress(slug)
                logger.info(f"Crawl complete: {len(all_index)} total chapters")
            else:
                logger.info(f"Saved {len(all_index)} chapters. Run again to resume.")

        return self._rebuild_index(slug)
