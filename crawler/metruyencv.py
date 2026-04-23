import re
from urllib.parse import urljoin

from .base import BaseCrawler, logger

BASE_URL = "https://metruyencv.xyz/"


class MetruyencvCrawler(BaseCrawler):
    """Crawler for metruyencv.xyz chapter pages."""

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

    def crawl(self, start_url: str, start_index: int = 0, max_chapters: int = 0) -> list[dict]:
        """
        Crawl all chapters starting from start_url by following nav-next links.
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

            # Rebuild index from all saved volumes (with dedup)
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
