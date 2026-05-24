"""Crawler for sitruyencv.com — JSON API-based (React SPA backend)."""

import re
import subprocess
import time

import requests

from .base import BaseCrawler, logger

BASE_URL = "https://sitruyencv.com/"
API_BASE = "https://api.sitruyencv.com/api"
TOR_SOCKS = "socks5h://127.0.0.1:9050"
TOR_CONTAINER = "tor"


class SitruyencvCrawler(BaseCrawler):
    """Crawler for sitruyencv.com via its public JSON API.

    Auto-detects local Tor SOCKS5 proxy (Docker container on port 9050).
    When Tor is available, routes all requests through it and renews IP
    on 429 rate-limit via SIGHUP to the container.
    """

    BASE_URL = BASE_URL

    def __init__(self, dest_dir: str | None = None):
        super().__init__(site_name="sitruyencv", dest_dir=dest_dir)
        self.delay = (4.0, 6.0)
        self.parallel_delay = (3.5, 5.5)
        self._story_info_cache: dict[int, dict] = {}
        self._version_cache: dict[int, int] = {}
        self._cached_story_title: str | None = None
        self._tor_enabled: bool = False

    def _check_tor(self) -> bool:
        """Check if Tor SOCKS5 proxy is reachable."""
        import socket
        try:
            with socket.create_connection(("127.0.0.1", 9050), timeout=3):
                return True
        except (OSError, ConnectionRefusedError):
            return False

    def _renew_ip(self) -> None:
        """Send SIGHUP to Tor container to get a new exit IP."""
        try:
            subprocess.run(
                ["docker", "kill", "--signal=SIGHUP", TOR_CONTAINER],
                capture_output=True, timeout=10,
            )
            logger.info("Tor: SIGHUP sent — new IP requested")
            time.sleep(3)
        except Exception as e:
            logger.warning(f"Tor SIGHUP failed: {e}")
            time.sleep(10)

    def _build_session(self) -> requests.Session:
        s = super()._build_session()
        self._tor_enabled = self._check_tor()
        if self._tor_enabled:
            s.proxies = {"http": TOR_SOCKS, "https": TOR_SOCKS}
            logger.info("Tor SOCKS5 proxy detected — routing through Tor")
        return s

    # ── Override: parse JSON + Tor IP renewal ─────────────────────

    def _request(self, url, session, delay_range, retries, allow_404, referer=None):
        """Fetch URL and return parsed JSON. Renew Tor IP on 429."""
        for attempt in range(1, retries + 1):
            try:
                self._rate_limit(delay_range)
                headers = self._pick_headers(referer=referer)
                headers["Accept"] = "application/json"
                resp = session.get(url, timeout=15, headers=headers)

                if allow_404 and resp.status_code == 404:
                    return None

                if resp.status_code in (429, 503):
                    self._on_rate_limited()
                    if self._tor_enabled:
                        self._renew_ip()
                    wait = self._parse_retry_after(resp)
                    if wait is None:
                        wait = min(30.0, 3.0 * (2 ** attempt))
                    logger.warning(
                        f"HTTP {resp.status_code} on {url} — sleeping {wait:.1f}s "
                        f"(attempt {attempt}/{retries})"
                    )
                    if attempt == retries:
                        resp.raise_for_status()
                    time.sleep(wait)
                    continue

                if resp.status_code == 403:
                    self._on_rate_limited()
                    if self._tor_enabled:
                        self._renew_ip()
                    if attempt == retries:
                        resp.raise_for_status()
                    wait = min(30.0, 3.0 * (2 ** attempt))
                    logger.warning(
                        f"HTTP 403 on {url} — sleeping {wait:.1f}s "
                        f"(attempt {attempt}/{retries})"
                    )
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

    # ── API helpers ──────────────────────────────────────────────

    def _extract_story_id(self, url: str) -> int:
        m = re.search(r'sitruyencv\.com/(?:read|story)/(\d+)', url)
        if m:
            return int(m.group(1))
        raise ValueError(f"Cannot extract story ID from: {url}")

    def _get_story_info(self, story_id: int) -> dict:
        if story_id in self._story_info_cache:
            return self._story_info_cache[story_id]
        resp = self.fetch(f"{API_BASE}/stories/{story_id}")
        info = resp.get("data", resp)
        self._story_info_cache[story_id] = info
        self._cached_story_title = info.get("title")
        return info

    def _get_version_id(self, story_id: int) -> int:
        if story_id in self._version_cache:
            return self._version_cache[story_id]
        resp = self.fetch(f"{API_BASE}/stories/{story_id}/translate-versions")
        versions = resp.get("data", [])
        if not versions:
            raise ValueError(f"No translate versions for story {story_id}")
        vid = None
        for v in versions:
            if v.get("version_type") == "Official":
                vid = v["id"]
                break
        self._version_cache[story_id] = vid or versions[0]["id"]
        logger.info(f"Using version {self._version_cache[story_id]} for story {story_id}")
        return self._version_cache[story_id]

    # ── BaseCrawler interface ────────────────────────────────────

    def _extract_slug(self, url: str) -> str:
        m = re.search(r'sitruyencv\.com/story/\d+-([a-z0-9-]+)', url)
        if m:
            return m.group(1)
        story_id = self._extract_story_id(url)
        info = self._get_story_info(story_id)
        return info.get("slug", f"story-{story_id}")

    def _extract_story_title(self, data) -> str | None:
        return self._cached_story_title

    def _extract_chapter(self, data) -> dict:
        ch = data.get("data", data)
        title = ch.get("title", "Unknown")
        content = ch.get("content", "")
        if not content:
            raise ValueError(f"Empty content for chapter {ch.get('chapter_number', '?')}")
        paragraphs = [p.strip() for p in content.split("\n") if p.strip()]
        return {"title": title, "paragraphs": paragraphs}

    def _next_chapter_url(self, data) -> str | None:
        return None

    def _predict_urls(self, start_url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]] | None:
        story_id = self._extract_story_id(start_url)
        info = self._get_story_info(story_id)
        version_id = self._get_version_id(story_id)

        total = info.get("latest_chapter_number", 0) or info.get("total_chapters", 0)
        if total == 0:
            logger.warning("Story has 0 chapters — nothing to crawl")
            return []

        m = re.search(r'/read/\d+/(\d+)', start_url)
        start_ch = int(m.group(1)) if m else 1

        remaining = total - start_ch + 1
        if remaining <= 0:
            logger.warning(f"Start chapter {start_ch} exceeds total {total}")
            return []
        limit = min(max_chapters, remaining) if max_chapters > 0 else remaining
        urls = []
        for i in range(limit):
            ch_num = start_ch + i
            url = f"{API_BASE}/chapters/{version_id}/read/{ch_num}"
            urls.append((start_index + i, url))

        logger.info(f"Predicted {len(urls)} chapter URLs (ch {start_ch}-{start_ch + len(urls) - 1}, story {story_id})")
        return urls

    def canary_check(self, url: str) -> bool:
        try:
            story_id = self._extract_story_id(url)
            info = self._get_story_info(story_id)
            logger.info(f"Canary OK — {info.get('title')} ({info.get('total_chapters')} chapters)")
            return True
        except Exception as e:
            logger.error(f"Canary failed: {e}")
            return False
