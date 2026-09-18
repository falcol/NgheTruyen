"""Crawler for piaotia.com (飘天文学) — GBK HTML, Tor on 429.

Chapter file IDs are not sequential. Catalog is the TOC page (all hrefs);
parallel fetch uses that list, not predicted IDs.
"""

import html as htmlmod
import re
import subprocess
import threading
import time
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import requests

from .base import BaseCrawler, logger, _HTML_PARSER

BASE_URL = "https://www.piaotia.com"
TOR_SOCKS = "socks5h://127.0.0.1:9050"
TOR_CONTAINER = "tor"

_TOC_RE = re.compile(r"/html/\d+/(\d+)(?:/(?:index\.html)?)?$", re.I)
_CH_RE = re.compile(r"/html/\d+/(\d+)/(\d+)\.html", re.I)
_NEXT_PAGE_RE = re.compile(r'var next_page\s*=\s*"([^"]+)"')
_TITLE_CH_RE = re.compile(r"第\s*\d+\s*章\S*")
_CH_NUM_RE = re.compile(r"第\s*(\d+)\s*章")
_FIRST_CH_RE = re.compile(r"第\s*1\s*章($|[^0-9])")
_NBSP_PARA_RE = re.compile(r"(?:&nbsp;|\xa0){2,}\s*([^<]+)")
_JUNK_RE = re.compile(
    r"GetMode|SelectColors|Gundong|GetFont|fontbig|font[123]|"
    r"选择背景|选择字体|繁體中文|上一章|下一章|返回目录|返回书页|"
    r"PT文学|飘天文学|我的藏书|加入书架|加入书签|推荐本书|收藏本书|"
    r"章节错误|重要声明|Copyright|返回顶部|小说阅读网|书籍介绍|章节目录"
)


class PiaotiaCrawler(BaseCrawler):
    """piaotia.com crawler. Routes through Tor when SOCKS5 :9050 is up."""

    BASE_URL = BASE_URL

    def __init__(self, dest_dir: str | None = None):
        self._tor_enabled: bool = False
        self._page_url: str | None = None
        self._tor_lock = threading.Lock()
        super().__init__(site_name="piaotia", dest_dir=dest_dir)
        self.delay = (3.0, 5.0)
        self.parallel_delay = (1.2, 2.0)
        self.READING_PAUSE_EVERY_CHUNKS = 0

    def _check_tor(self) -> bool:
        import socket
        try:
            with socket.create_connection(("127.0.0.1", 9050), timeout=3):
                return True
        except (OSError, ConnectionRefusedError):
            return False

    def _renew_ip(self) -> None:
        with self._tor_lock:
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
        else:
            logger.warning("Tor SOCKS5 :9050 not reachable — crawling direct (429 risk)")
        return s

    def _pick_headers(self, referer: str | None = None) -> dict[str, str]:
        headers = super()._pick_headers(referer)
        headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
        return headers

    def _on_rate_limited(self) -> None:
        super()._on_rate_limited()
        if self._tor_enabled:
            self._renew_ip()

    def _request(
        self,
        url: str,
        session: requests.Session,
        delay_range: tuple[float, float],
        retries: int,
        allow_404: bool,
        referer: str | None = None,
    ) -> BeautifulSoup | None:
        for attempt in range(1, retries + 1):
            try:
                self._rate_limit(delay_range)
                headers = self._pick_headers(referer=referer)
                resp = session.get(url, timeout=25, headers=headers)

                if allow_404 and resp.status_code == 404:
                    return None

                if resp.status_code in (429, 503):
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

                if resp.status_code == 403:
                    self._on_rate_limited()
                    if attempt == retries:
                        resp.raise_for_status()
                    wait = min(60.0, 5.0 * (2 ** attempt))
                    logger.warning(
                        f"HTTP 403 on {url} — sleeping {wait:.1f}s "
                        f"(attempt {attempt}/{retries})"
                    )
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
                resp.encoding = "gb18030"
                self._on_success()
                return BeautifulSoup(resp.text, _HTML_PARSER)

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

    def fetch(self, url: str, retries: int = 3, referer: str | None = None) -> BeautifulSoup:
        self._page_url = url
        return super().fetch(url, retries=retries, referer=referer)

    def fetch_parallel(self, url: str, retries: int = 3) -> BeautifulSoup | None:
        self._page_url = url
        return super().fetch_parallel(url, retries=retries)

    def _extract_slug(self, url: str) -> str:
        m = _CH_RE.search(url) or _TOC_RE.search(url.rstrip("/"))
        if m:
            return m.group(1)
        return "unknown"

    def _extract_story_title(self, soup: BeautifulSoup) -> str | None:
        if soup.title:
            t = soup.title.get_text()
            m = re.match(r"(.+?)最新章节", t)
            if m:
                return m.group(1).strip()
        a = soup.select_one('a[href*="/bookinfo/"] b')
        if a:
            return a.get_text(strip=True) or None
        return None

    def _extract_chapter(self, soup: BeautifulSoup) -> dict:
        title = "Unknown"
        if soup.title:
            for part in soup.title.get_text().split(","):
                part = part.strip()
                if _TITLE_CH_RE.search(part):
                    title = part
                    break

        paras: list[str] = []
        for raw in _NBSP_PARA_RE.findall(str(soup)):
            text = htmlmod.unescape(raw).strip()
            if text and not _JUNK_RE.search(text):
                paras.append(text)

        nchars = sum(len(p) for p in paras)
        if not paras or nchars < 80:
            raise ValueError(f"Could not extract chapter body ({len(paras)} paras, {nchars} chars)")
        return {"title": title, "paragraphs": paras}

    def _next_chapter_url(self, soup: BeautifulSoup) -> str | None:
        href = None
        for script in soup.find_all("script"):
            src = script.string or ""
            m = _NEXT_PAGE_RE.search(src)
            if m:
                href = m.group(1).strip()
                break
        if not href or href.lower() in ("index.html", "#", "javascript:void(0)"):
            return None
        base = self._page_url or (self.BASE_URL + "/")
        return urljoin(base, href)

    def _toc_url(self, url: str) -> str:
        if _CH_RE.search(url):
            return re.sub(r"/[^/]+\.html$", "/", url)
        return url.rstrip("/") + "/"

    def _resolve_start_url(self, url: str) -> str:
        if _CH_RE.search(url):
            return url
        toc = self._toc_url(url)
        if not _TOC_RE.search(toc.rstrip("/")) and "index.html" not in url:
            return url
        logger.info(f"TOC detected — resolving chapter 1: {toc}")
        soup = self.fetch(toc)
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True)
            if _FIRST_CH_RE.match(text):
                return urljoin(toc, a["href"])
        raise ValueError(f"Cannot find chapter 1 on TOC: {url}")

    def _predict_urls(
        self, start_url: str, start_index: int, max_chapters: int
    ) -> list[tuple[int, str]] | None:
        """Read TOC once; return (index, url) sorted by 第N章."""
        toc = self._toc_url(start_url)
        logger.info(f"Loading chapter catalog: {toc}")
        soup = self.fetch(toc)
        by_num: dict[int, str] = {}
        for a in soup.find_all("a", href=True):
            href = (a.get("href") or "").strip()
            text = a.get_text(strip=True)
            m = _CH_NUM_RE.search(text)
            if not m or not href.endswith(".html") or href.endswith("index.html"):
                continue
            abs_url = urljoin(toc, href)
            if not _CH_RE.search(abs_url):
                continue
            by_num[int(m.group(1))] = abs_url
        if not by_num:
            logger.warning("Catalog empty — sequential next_page fallback")
            return None
        urls = [(num - 1, u) for num, u in sorted(by_num.items())]
        urls = [(idx, u) for idx, u in urls if idx >= start_index]
        if max_chapters:
            urls = urls[:max_chapters]
        logger.info(
            f"Catalog: {len(urls)} chapters "
            f"(第{urls[0][0] + 1}–第{urls[-1][0] + 1}章)"
            if urls else "Catalog: 0 chapters after filters"
        )
        return urls

    def crawl(self, start_url: str, start_index: int = 0, max_chapters: int = 0) -> list[dict]:
        self.warmup()
        predicted = self._predict_urls(start_url, start_index, max_chapters)
        if predicted:
            slug = self._extract_slug(start_url)
            logger.info(f"Catalog crawl: {len(predicted)} URLs, 6 workers")
            return self._parallel_fetch(predicted, slug, workers=6)
        return super().crawl(
            self._resolve_start_url(start_url),
            start_index=start_index,
            max_chapters=max_chapters,
        )

    def crawl_parallel(
        self, start_url: str, start_index: int = 0, max_chapters: int = 0, workers: int = 3
    ) -> list[dict]:
        self.warmup()
        toc = self._toc_url(start_url)
        if not self.canary_check(toc):
            return []
        slug = self._extract_slug(start_url)
        predicted = self._predict_urls(start_url, start_index, max_chapters)
        if not predicted:
            logger.info("Catalog failed, sequential next_page")
            return super().crawl(
                self._resolve_start_url(start_url),
                start_index=start_index,
                max_chapters=max_chapters,
            )
        logger.info(f"Catalog {len(predicted)} URLs, {workers} workers")
        return self._parallel_fetch(predicted, slug, workers)
