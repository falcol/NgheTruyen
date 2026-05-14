import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .base import BaseCrawler, logger

BASE_URL = "https://metruyenchu.com.vn/"
CHAPTER_LIST_API = "https://metruyenchu.com.vn/get/listchap/"


class MetruyenchuCrawler(BaseCrawler):
    """Crawler for metruyenchu.com.vn chapter pages."""

    BASE_URL = BASE_URL

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

    def _get_story_meta(self, slug: str) -> tuple[int, int] | None:
        """Fetch story page and extract (story_id, total_pages) from `page(ID, N)`.

        The site renders pagination as multiple `onclick="page(STORY_ID, N)"`
        buttons — one for each page number (1, 2, ..., 14). We need the MAX
        of N across all matches (first match is often "page 2" / next button).
        Returns None if no pattern found.
        """
        self._rate_limit(self.delay)
        headers = self._pick_headers(referer=BASE_URL)
        headers["Accept"] = "text/html,application/xhtml+xml"
        resp = self.session.get(
            f"{BASE_URL}{slug}",
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        # findall returns all (story_id, page_num) tuples. Multiple buttons
        # share the same story_id; take max of N across them.
        matches = re.findall(r"page\((\d+),\s*(\d+)\)", resp.text)
        if not matches:
            return None
        story_id = int(matches[0][0])
        # Filter to only matches for this story (defensive — same ID expected)
        nums = [int(n) for sid, n in matches if int(sid) == story_id]
        total_pages = max(nums) if nums else 1
        return story_id, total_pages

    # Back-compat shim — older callers still use _get_story_id
    def _get_story_id(self, slug: str) -> int | None:
        meta = self._get_story_meta(slug)
        return meta[0] if meta else None

    def _fetch_chapter_list(
        self,
        story_id: int,
        max_chapters: int = 0,
        max_pages: int | None = None,
    ) -> list[str]:
        """Fetch all chapter URLs via AJAX pagination API.

        Termination conditions (any one triggers stop):
          1. `max_pages` reached (authoritative bound from `page(ID, N)` JS call)
          2. Empty `data` field in JSON response
          3. Zero chapter links extracted
          4. Page returned fewer than 100 links (last page)
          5. Dedup guard: page returned only duplicate URLs (API looped to page 1)

        The dedup guard is kept as backup even when `max_pages` is known —
        cheap insurance against off-by-one or unexpected API behavior.
        """
        urls: list[str] = []
        seen: set[str] = set()
        page_num = 1
        story_url = BASE_URL
        # Hard cap: authoritative `max_pages` if provided, else generous safety
        cap = max_pages if max_pages else 200

        while page_num <= cap:
            self._rate_limit(self.delay)
            # AJAX call: keep XHR markers but rotate UA/Accept-Language
            base_headers = self._pick_headers(referer=story_url)
            api_headers = {**base_headers, **self._api_headers}
            resp = self.session.get(
                f"{CHAPTER_LIST_API}{story_id}",
                params={"page": page_num},
                headers=api_headers,
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

            page_urls = [urljoin(BASE_URL, a["href"]) for a in chapter_links]
            new_urls = [u for u in page_urls if u not in seen]

            # Dedup guard: API likely looping back to page 1 on invalid page numbers
            if not new_urls:
                logger.info(
                    f"Chapter list page {page_num}: all {len(page_urls)} URLs are duplicates — "
                    "API has stopped paginating (likely past last page)"
                )
                break

            for u in new_urls:
                urls.append(u)
                seen.add(u)
                if max_chapters and len(urls) >= max_chapters:
                    return urls

            dup_count = len(page_urls) - len(new_urls)
            dup_note = f" ({dup_count} duplicates ignored)" if dup_count else ""
            logger.info(
                f"Chapter list page {page_num}: +{len(new_urls)} URLs"
                f"{dup_note} (total: {len(urls)})"
            )
            page_num += 1

            # Safety: if page returned fewer than 100, it's the last page
            if len(chapter_links) < 100:
                break

        if page_num > cap:
            if max_pages:
                logger.info(f"Reached authoritative max_pages={max_pages}")
            else:
                logger.warning(f"Hit safety cap={cap} — stopping. Story may have more chapters.")

        return urls

    def _predict_urls(self, start_url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]] | None:
        """Fetch full chapter list via API, then return indexed URLs.

        Note: site uses "Trước 1 2 3 ... Tiếp" ellipsis pagination — total
        page count is NOT exposed in HTML (only visible button numbers).
        Rely on iterative fetch + dedup guard to detect end-of-list.
        """
        slug = self._extract_slug(start_url)

        meta = self._get_story_meta(slug)
        if not meta:
            logger.warning("Could not extract story_id, falling back to sequential")
            return None

        story_id, hint = meta
        # `hint` is the highest visible page button (e.g. 3 from "1 2 3 ... Tiếp").
        # NOT total pages — informational only. Dedup guard does the real work.
        logger.info(
            f"Story ID: {story_id}, fetching chapter list... "
            f"(visible-pagination hint: {hint}, real total detected via dedup)"
        )

        chapter_urls = self._fetch_chapter_list(story_id, max_chapters=max_chapters)
        if not chapter_urls:
            return None

        logger.info(f"Collected {len(chapter_urls)} chapter URLs from API")
        return [(start_index + i, url) for i, url in enumerate(chapter_urls)]

