"""Crawler for sstruyen.pics — public JSON API (api.sstruyen.pics)."""

import re
import time

import requests
from bs4 import BeautifulSoup

from .base import BaseCrawler, logger

BASE_URL = "https://sstruyen.pics/"
API_BASE = "https://api.sstruyen.pics"
_PAGE_SIZE = 50
_INVISIBLE = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_AD_START = "Team chúng mình biết quảng cáo Popup"
_AD_LINK = "Hoặc nếu bạn cảm thấy phiền"
_STORY_URL = re.compile(r"sstruyen\.pics/truyen/([^/?#]+)")
_CHAPTER_URL = re.compile(r"sstruyen\.pics/doc-truyen/(.+)-chuong-(\d+)-(\d+)")


def paragraphs_from_html(html: str, chapter_no: int | None = None) -> list[str]:
    """Turn chapter HTML into plain paragraphs. Drops invisible format chars.

    sstruyen appends the chapter number as its own trailing paragraph.
    """
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup.find_all(["script", "style", "ins", "iframe"]):
        tag.decompose()
    nodes = soup.find_all("p")
    raw = [p.get_text(" ", strip=True) for p in nodes] if nodes else soup.get_text("\n").splitlines()
    paragraphs = []
    for line in raw:
        text = _INVISIBLE.sub("", line)
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            paragraphs.append(text)
    if chapter_no is not None and paragraphs and paragraphs[-1] == str(chapter_no):
        paragraphs.pop()
    return _drop_site_ad(paragraphs)


def _drop_site_ad(paragraphs: list[str]) -> list[str]:
    """Remove the site's maintenance-ad block, including when it is glued onto the last sentence."""
    cleaned = []
    for text in paragraphs:
        if text.startswith(_AD_LINK) and "lightnovel.vn" in text:
            continue
        cut = text.find(_AD_START)
        if cut >= 0:
            text = text[:cut].strip()
        if text:
            cleaned.append(text)
    return cleaned


class SstruyenCrawler(BaseCrawler):
    """Crawl sstruyen.pics via /novels/{id}/chapters and /chapters/{id}."""

    BASE_URL = BASE_URL
    # API listing is one call per 50 chapters; no long human-style pause.
    READING_PAUSE_EVERY_CHUNKS = 0

    def __init__(self, dest_dir: str | None = None):
        super().__init__(site_name="sstruyen", dest_dir=dest_dir)
        self.delay = (0.4, 0.8)
        self.parallel_delay = (0.25, 0.55)
        self._novel_id: int | None = None
        self._cached_story_title: str | None = None
        self._catalog: list[dict] | None = None

    def _request(
        self,
        url: str,
        session: requests.Session,
        delay_range: tuple[float, float],
        retries: int,
        allow_404: bool,
        referer: str | None = None,
    ):
        if not url.startswith(API_BASE):
            return super()._request(url, session, delay_range, retries, allow_404, referer=referer)
        return self._request_json(url, session, delay_range, retries, allow_404, referer)

    def _request_json(self, url, session, delay_range, retries, allow_404, referer):
        for attempt in range(1, retries + 1):
            try:
                self._rate_limit(delay_range)
                headers = self._pick_headers(referer=referer or BASE_URL)
                headers["Accept"] = "application/json"
                headers["Origin"] = "https://sstruyen.pics"
                resp = session.get(url, timeout=20, headers=headers)

                if allow_404 and resp.status_code == 404:
                    return None

                if resp.status_code in (429, 503, 403):
                    self._on_rate_limited()
                    wait = self._parse_retry_after(resp)
                    if wait is None:
                        wait = min(60.0, 5.0 * (2 ** attempt))
                    logger.warning(
                        f"HTTP {resp.status_code} on {url} — sleeping {wait:.1f}s "
                        f"(attempt {attempt}/{retries})"
                    )
                    if attempt == retries:
                        resp.raise_for_status()
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                self._on_success()
                return resp.json()
            except requests.HTTPError as e:
                if allow_404 and e.response is not None and e.response.status_code == 404:
                    return None
                if attempt == retries:
                    raise
                logger.warning(f"Attempt {attempt}/{retries} failed for {url}: {e}")
                time.sleep(2 ** attempt)
            except requests.RequestException as e:
                if attempt == retries:
                    raise
                logger.warning(f"Attempt {attempt}/{retries} failed for {url}: {e}")
                time.sleep(2 ** attempt)
        return None

    def _fetch_html(self, url: str) -> str:
        last_err: Exception | None = None
        for attempt in range(1, 4):
            try:
                self._rate_limit(self.delay)
                headers = self._pick_headers(referer=BASE_URL)
                resp = self.session.get(url, timeout=20, headers=headers)
                resp.raise_for_status()
                self._on_success()
                return resp.text
            except requests.RequestException as e:
                last_err = e
                logger.warning(f"HTML attempt {attempt}/3 failed for {url}: {e}")
                time.sleep(2 ** attempt)
        assert last_err is not None
        raise last_err

    def _extract_slug(self, url: str) -> str:
        match = _CHAPTER_URL.search(url)
        if match:
            return match.group(1)
        match = _STORY_URL.search(url)
        if match:
            return match.group(1).strip("/")
        raise ValueError(f"Cannot extract story slug from: {url}")

    def _novel_from_html(self, html: str, slug: str) -> tuple[int, str] | None:
        """Read novel id + title embedded in the story page RSC payload."""
        tokens = (
            (f'\\"slug\\":\\"{slug}\\"', True),
            (f'"slug":"{slug}"', False),
        )
        for token, escaped in tokens:
            idx = html.find(token)
            if idx < 0:
                continue
            window = html[max(0, idx - 1200):idx]
            if escaped:
                ids = re.findall(r'\\"id\\":(\d+)', window)
                names = re.findall(r'\\"name\\":\\"([^"\\]*)\\"', window)
            else:
                ids = re.findall(r'"id":(\d+)', window)
                names = re.findall(r'"name":"([^"\\]*)"', window)
            if not ids:
                continue
            title = names[-1].replace('\\"', '"').replace("\\/", "/") if names else ""
            return int(ids[-1]), title
        return None

    def _chapter_id_from_url(self, url: str) -> str | None:
        match = _CHAPTER_URL.search(url)
        if match:
            return match.group(3)
        return None

    def _ensure_story(self, url: str) -> None:
        if self._novel_id is not None:
            return
        slug = self._extract_slug(url)
        novel_id: int | None = None
        title = ""
        chapter_id = self._chapter_id_from_url(url)

        if chapter_id is None:
            html = self._fetch_html(f"{BASE_URL}truyen/{slug}")
            found = self._novel_from_html(html, slug)
            if found:
                novel_id, title = found
            else:
                link = re.search(rf"/doc-truyen/{re.escape(slug)}-chuong-\d+-(\d+)", html)
                if not link:
                    raise ValueError(f"No chapter link on story page: {slug}")
                chapter_id = link.group(1)

        if novel_id is None:
            if not chapter_id:
                raise ValueError(f"Cannot resolve novel id from: {url}")
            data = self.fetch(f"{API_BASE}/chapters/{chapter_id}")
            novel_id = int(data["novelId"])
            title = (data.get("novel") or {}).get("name") or title

        self._novel_id = novel_id
        if title:
            self._cached_story_title = title
        logger.info(f"Novel {novel_id}: {self._cached_story_title or slug}")

    def _load_catalog(self, url: str) -> list[dict]:
        if self._catalog is not None:
            return self._catalog
        self._ensure_story(url)
        chapters: list[dict] = []
        page = 1
        while page <= 500:
            data = self.fetch(
                f"{API_BASE}/novels/{self._novel_id}/chapters"
                f"?page={page}&limit={_PAGE_SIZE}&sort=asc&keyword="
            )
            batch = data.get("chapters") or []
            chapters.extend(batch)
            if not data.get("hasNext") or not batch:
                break
            page += 1
        self._catalog = chapters
        logger.info(f"Catalog: {len(chapters)} chapters")
        return chapters

    def _extract_story_title(self, data) -> str | None:
        if isinstance(data, dict):
            name = (data.get("novel") or {}).get("name")
            if name:
                self._cached_story_title = name
        return self._cached_story_title

    def _extract_chapter(self, data) -> dict:
        if not isinstance(data, dict):
            raise ValueError("Expected chapter JSON")
        title = (data.get("name") or "").strip() or "Unknown"
        number = re.match(r"Chương\s+(\d+)\b", title)
        chapter_no = int(number.group(1)) if number else None
        content = data.get("content") or ""
        paragraphs = paragraphs_from_html(content, chapter_no)
        if not paragraphs:
            raise ValueError(f"Empty content for {title}")
        return {"title": title, "paragraphs": paragraphs}

    def _next_chapter_url(self, data) -> str | None:
        return None

    def _slice_catalog(self, url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]]:
        catalog = self._load_catalog(url)
        match = _CHAPTER_URL.search(url)
        if match:
            chapter_id = int(match.group(3))
            start_pos = next(
                (i for i, chapter in enumerate(catalog) if chapter["id"] == chapter_id),
                max(0, int(match.group(2)) - 1),
            )
            # --start 0 keeps the chapter's real position; an explicit --start renumbers.
            index_base = start_index if start_index else start_pos
        else:
            start_pos = start_index
            index_base = start_index

        selected = catalog[start_pos:]
        if max_chapters > 0:
            selected = selected[:max_chapters]
        return [
            (index_base + offset, f"{API_BASE}/chapters/{chapter['id']}")
            for offset, chapter in enumerate(selected)
        ]

    def _predict_urls(self, start_url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]] | None:
        urls = self._slice_catalog(start_url, start_index, max_chapters)
        if not urls:
            logger.warning("No chapters to crawl")
            return []
        logger.info(f"Predicted {len(urls)} chapter URLs (index {urls[0][0]}..{urls[-1][0]})")
        return urls

    def canary_check(self, url: str) -> bool:
        try:
            self._ensure_story(url)
            logger.info(f"Canary OK — {self._cached_story_title} (novel {self._novel_id})")
            return True
        except Exception as e:
            logger.error(f"Canary failed: {e}")
            return False

    def crawl(self, start_url: str, start_index: int = 0, max_chapters: int = 0) -> list[dict]:
        self.warmup()
        slug = self._extract_slug(start_url)
        urls = self._predict_urls(start_url, start_index, max_chapters) or []
        if not urls:
            return []
        chapters = []
        story_title = self._cached_story_title
        for idx, chapter_url in urls:
            logger.info(f"Crawling chapter {idx + 1}: {chapter_url}")
            data = self.fetch(chapter_url)
            chapter = self._extract_chapter(data)
            chapter["index"] = idx
            chapters.append(chapter)
            story_title = self._extract_story_title(data) or story_title
            logger.info(f"  -> {chapter['title']} ({len(chapter['paragraphs'])} paragraphs)")
        self._save_chapters(chapters, slug, story_title)
        return self._rebuild_index(slug)
