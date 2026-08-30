import base64
import re
import subprocess
import time
import zlib

from bs4 import BeautifulSoup
import requests

from .base import BaseCrawler, logger, _HTML_PARSER

BASE_URL = "https://www.xtruyen.vn"
TOR_SOCKS = "socks5h://127.0.0.1:9050"
TOR_CONTAINER = "tor"

# xtruyen.vn's WAF blocks Tor exit nodes outright (instant 403, not a rate-limit
# ramp). After this many consecutive blocks while routed through Tor, give up
# on Tor for the rest of the run and fall back to a direct connection.
TOR_BLOCK_FALLBACK_THRESHOLD = 2

# Chapter content is delivered as a base64(custom-alphabet)+zlib blob, decoded
# client-side by an obfuscated inline <script>. The custom alphabet is just a
# permutation of standard base64 — translate then base64-decode then inflate.
_CUSTOM_B64_ALPHABET = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_"
_STD_B64_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
_B64_TRANSLATE_TABLE = str.maketrans(_CUSTOM_B64_ALPHABET, _STD_B64_ALPHABET)
_DATA_X_RE = re.compile(r'const\s+data_x\s*=\s*"([^"]+)"')

# Story detail page (no chapter segment) vs. chapter page.
_STORY_URL_RE = re.compile(r'^https?://(?:www\.)?xtruyen\.vn/truyen/[^/]+/?$')


class XtruyenCrawler(BaseCrawler):
    """Crawler for xtruyen.vn.

    Auto-detects local Tor SOCKS5 proxy (Docker container on port 9050).
    When Tor is available, routes all requests through it and renews IP
    on 429/403 rate-limit via SIGHUP to the container.
    """

    BASE_URL = BASE_URL

    def __init__(self, dest_dir: str | None = None):
        self._tor_enabled: bool = False
        self._tor_blocked: bool = False  # set once xtruyen's WAF is seen blocking Tor exits
        self._consecutive_tor_blocks: int = 0
        super().__init__(site_name="xtruyen", dest_dir=dest_dir)
        self.delay = (3.0, 5.0)
        self.parallel_delay = (2.5, 4.5)

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
        if self._tor_blocked:
            return s  # xtruyen already proven to block Tor exits — stay direct
        self._tor_enabled = self._check_tor()
        if self._tor_enabled:
            s.proxies = {"http": TOR_SOCKS, "https": TOR_SOCKS}
            logger.info("Tor SOCKS5 proxy detected — routing through Tor")
        return s

    def _on_success(self) -> None:
        super()._on_success()
        self._consecutive_tor_blocks = 0

    def _on_rate_limited(self) -> None:
        """Override to renew Tor IP when server blocks/limits us — unless xtruyen
        turns out to be blocking Tor exit nodes outright, in which case fall back
        to a direct connection instead of burning through exit nodes forever."""
        super()._on_rate_limited()
        if not self._tor_enabled or self._tor_blocked:
            return

        self._consecutive_tor_blocks += 1
        if self._consecutive_tor_blocks >= TOR_BLOCK_FALLBACK_THRESHOLD:
            logger.warning(
                f"{self._consecutive_tor_blocks} consecutive blocks via Tor — "
                "xtruyen.vn appears to block Tor exit nodes. Falling back to direct connection."
            )
            self._tor_blocked = True
            self._tor_enabled = False
            self.session.proxies = {}
            if hasattr(self._thread_local, "session"):
                self._thread_local.session.proxies = {}
            return

        self._renew_ip()

    # ── Story-page → first-chapter resolution ──────────────────────

    def _resolve_start_url(self, url: str) -> str:
        """If given the story detail page instead of a chapter, resolve to chapter 1."""
        if not _STORY_URL_RE.match(url):
            return url
        logger.info(f"Story page detected — resolving first chapter: {url}")
        soup = self.fetch(url)
        first_link = soup.select_one("#init-links a")
        if first_link and first_link.get("href"):
            resolved = first_link["href"]
            logger.info(f"Resolved to first chapter: {resolved}")
            return resolved
        raise ValueError(f"Could not find first-chapter link on story page: {url}")

    def crawl(self, start_url: str, start_index: int = 0, max_chapters: int = 0) -> list[dict]:
        return super().crawl(self._resolve_start_url(start_url), start_index=start_index, max_chapters=max_chapters)

    def crawl_parallel(self, start_url: str, start_index: int = 0, max_chapters: int = 0, workers: int = 3) -> list[dict]:
        return super().crawl_parallel(
            self._resolve_start_url(start_url), start_index=start_index, max_chapters=max_chapters, workers=workers
        )

    # ── Chapter content decoding ────────────────────────────────────

    @staticmethod
    def _decode_data_x(data_x: str) -> str:
        """Reverse the site's client-side decoder: custom-alphabet base64 + zlib."""
        translated = data_x.translate(_B64_TRANSLATE_TABLE)
        binary = base64.b64decode(translated)
        return zlib.decompress(binary).decode("utf-8")

    # ── BaseCrawler interface ────────────────────────────────────

    def _extract_slug(self, url: str) -> str:
        """Extract story slug from URL for output directory naming."""
        # https://www.xtruyen.vn/truyen/manh-nhat-tu-tien-hoc-sinh-tieu-hoc/
        m = re.search(r'xtruyen\.vn/truyen/([^/]+)', url)
        if m:
            return m.group(1)
        return "unknown-xtruyen-story"

    def _extract_story_title(self, soup: BeautifulSoup) -> str | None:
        """Extract the story title from the chapter page's breadcrumb heading."""
        title_el = soup.select_one("#chapter-heading a") or soup.select_one("div.post-title h1")
        if title_el:
            return title_el.get_text(strip=True)
        return None

    def _extract_chapter(self, soup: BeautifulSoup) -> dict:
        """Extract chapter title and paragraphs from a parsed page."""
        title = "Unknown Chapter"
        heading = soup.find(id="chapter-heading")
        h2 = heading.find_next("h2") if heading else soup.find("h2")
        if h2:
            title = h2.get_text(strip=True)

        html_fragment = None
        for script in soup.find_all("script"):
            script_text = script.string or script.get_text()
            if not script_text or "data_x" not in script_text:
                continue
            m = _DATA_X_RE.search(script_text)
            if m:
                html_fragment = self._decode_data_x(m.group(1))
                break

        paragraphs: list[str] = []
        if html_fragment is not None:
            content_soup = BeautifulSoup(html_fragment, _HTML_PARSER)
            paragraphs = [p.get_text(strip=True) for p in content_soup.find_all("p")]
            paragraphs = [p for p in paragraphs if p]
            if not paragraphs:
                text_only = content_soup.get_text("\n")
                paragraphs = [line.strip() for line in text_only.split("\n") if line.strip()]

        if not paragraphs:
            raise ValueError(f"Empty content for chapter: {title} — page structure may have changed or is blocked.")

        return {"title": title, "paragraphs": paragraphs}

    def _next_chapter_url(self, soup: BeautifulSoup) -> str | None:
        """Find the next chapter URL from the current page. Return None if last."""
        next_link = soup.select_one("div.nav-next a.next_page")
        if next_link and next_link.get("href"):
            return next_link["href"]
        return None
