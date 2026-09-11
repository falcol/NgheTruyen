"""Crawler for wenxue.iqiyi.com — catalog + reader HTML.

Fills gaps in an existing local story (default dest: xtruyen). Only chapters
whose parsed title-number is absent locally are fetched.
"""

import re
import subprocess
import time

from bs4 import BeautifulSoup
import requests

from .base import BaseCrawler, logger, _HTML_PARSER

BASE_URL = "https://wenxue.iqiyi.com"
TOR_SOCKS = "socks5h://127.0.0.1:9050"
TOR_CONTAINER = "tor"

# Known iQiyi bookId → existing local slug under --dest (xtruyen).
SLUG_MAP = {
    "18l2h74lml": "manh-nhat-tu-tien-hoc-sinh-tieu-hoc",
}

_CATALOG_RE = re.compile(r"catalog-([a-z0-9]+)-(\d+)\.html", re.I)
_READER_RE = re.compile(r"reader-([a-z0-9]+)-([a-z0-9]+)\.html", re.I)
_DETAIL_RE = re.compile(r"detail-([a-z0-9]+)\.html", re.I)
_CHAPTER_HREF_RE = re.compile(
    r'href=["\']((?:https?:)?//wenxue\.iqiyi\.com/book/reader-[^"\']+\.html)["\']>([^<]+)</a>'
)

_CN_DIGIT = {
    "零": 0, "一": 1, "二": 2, "兩": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}
_CN_UNIT = {"千": 1000, "百": 100, "十": 10, "万": 10000, "萬": 10000}

_VIET_DIGIT = {
    "không": 0, "linh": 0, "lẻ": 0,
    "một": 1, "mốt": 1, "nhất": 1,
    "hai": 2, "nhị": 2,
    "ba": 3, "tam": 3,
    "bốn": 4, "tư": 4, "tứ": 4,
    "năm": 5, "lăm": 5, "ngũ": 5,
    "sáu": 6, "lục": 6,
    "bảy": 7, "thất": 7,
    "tám": 8, "bát": 8,
    "chín": 9, "cửu": 9,
}


def _parse_cn_num(s: str) -> int | None:
    s = s.replace("萬", "万")
    total = 0
    unit = 0
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "零":
            if unit and i + 1 < len(s) and s[i + 1] in _CN_DIGIT:
                total += unit * 100
                unit = 0
            i += 1
            continue
        if ch in _CN_DIGIT:
            unit = _CN_DIGIT[ch]
            i += 1
        elif ch in _CN_UNIT:
            u = _CN_UNIT[ch]
            if unit == 0 and ch == "十":
                unit = 1
            total += unit * u
            unit = 0
            i += 1
        else:
            return None
    return total + unit


def parse_zh_title_num(title: str) -> int | None:
    t = title.strip()
    if t.startswith("弟"):
        t = "第" + t[1:]
    m = re.search(r"第\s*([0-9]+)\s*章", t)
    if m:
        return int(m.group(1))
    m = re.search(r"第\s*([零一二兩三两四五六七八九十百千萬万]+)\s*章?", t)
    if m:
        return _parse_cn_num(m.group(1))
    m = re.search(r"^([零一二兩三两四五六七八九十百千萬万]+)\s*章", t)
    if m:
        return _parse_cn_num(m.group(1))
    return None


def _parse_viet_phrase(s: str) -> int | None:
    s = s.lower().replace("nghìn", "ngàn")
    tokens = re.findall(
        r"\d+|không|linh|lẻ|một|mốt|nhất|hai|nhị|ba|tam|bốn|tư|tứ|"
        r"năm|lăm|ngũ|sáu|lục|bảy|thất|tám|bát|chín|cửu|mươi|mười|trăm|ngàn",
        s,
    )
    if not tokens:
        return None
    total = 0
    unit = 0
    for tok in tokens:
        if tok.isdigit():
            unit = int(tok)
        elif tok in _VIET_DIGIT:
            unit = _VIET_DIGIT[tok]
        elif tok == "ngàn":
            if unit == 0:
                unit = 1
            total += unit * 1000
            unit = 0
        elif tok == "trăm":
            if unit == 0:
                unit = 1
            total += unit * 100
            unit = 0
        elif tok in ("mười", "mươi"):
            if unit == 0:
                unit = 1
            total += unit * 10
            unit = 0
    n = total + unit
    return n if n > 0 else None


def parse_local_title_num(title: str) -> int | None:
    t = title.strip()
    zh = parse_zh_title_num(t)
    if zh:
        return zh
    m = re.match(r"^(?:Chương|Chuong|C)\s+(\d+)\b", t, re.I)
    if m:
        return int(m.group(1))
    m = re.match(r"^Đệ\s+(\d+)\s*chương", t, re.I)
    if m:
        return int(m.group(1))
    m = re.match(r"^(?:Thứ\s+)?(\d+)\s*chương", t, re.I)
    if m:
        return int(m.group(1))
    m = re.match(r"^Thứ\s+(\d+)\s*(.*)$", t, re.I)
    if m:
        base = int(m.group(1))
        extra = _parse_viet_phrase(m.group(2))
        return base + extra if extra else base
    m = re.match(r"^Đệ\s+(\d+)\s+(.*)$", t, re.I)
    if m:
        base = int(m.group(1))
        rest = m.group(2)
        vn = _parse_viet_phrase(rest)
        if vn is None:
            return base
        # "Đệ 2001 mười" = 两千零一十 → 2010
        if base % 10 == 1 and 10 <= vn <= 19 and base >= 100:
            return (base - 1) + vn
        return base + vn
    return _parse_viet_phrase(t)


class IqiyiCrawler(BaseCrawler):
    """iQiyi wenxue crawler. Routes through Tor when SOCKS5 :9050 is up."""

    BASE_URL = BASE_URL

    def __init__(self, dest_dir: str | None = None):
        super().__init__(site_name="iqiyi", dest_dir=dest_dir or "xtruyen")
        self.delay = (3.0, 5.0)
        self.parallel_delay = (2.5, 4.5)
        self._tor_enabled: bool = False
        self._active_slug: str | None = None

    def _check_tor(self) -> bool:
        import socket
        try:
            with socket.create_connection(("127.0.0.1", 9050), timeout=3):
                return True
        except (OSError, ConnectionRefusedError):
            return False

    def _renew_ip(self) -> None:
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

    def _pick_headers(self, referer: str | None = None) -> dict[str, str]:
        headers = super()._pick_headers(referer)
        headers["Accept-Language"] = "zh-CN,zh;q=0.9,en;q=0.8"
        return headers

    def _on_rate_limited(self) -> None:
        super()._on_rate_limited()
        if self._tor_enabled:
            self._renew_ip()

    def _book_id(self, url: str) -> str:
        for cre in (_CATALOG_RE, _READER_RE, _DETAIL_RE):
            m = cre.search(url)
            if m:
                return m.group(1)
        raise ValueError(f"Cannot extract iQiyi book id from: {url}")

    def _extract_slug(self, url: str) -> str:
        book_id = self._book_id(url)
        slug = SLUG_MAP.get(book_id, book_id)
        self._active_slug = slug
        return slug

    def _abs_url(self, href: str) -> str:
        if href.startswith("//"):
            return "https:" + href
        if href.startswith("http"):
            return href
        return BASE_URL + href

    def _extract_story_title(self, soup: BeautifulSoup) -> str | None:
        slug = self._active_slug
        if slug:
            try:
                meta = self._read_json_any(self.output_dir(slug) / "metadata.json")
                if isinstance(meta, dict) and meta.get("story_title"):
                    return meta["story_title"]
            except FileNotFoundError:
                pass
        h1 = soup.select_one("h1")
        if h1:
            text = h1.get_text(strip=True)
            return text.split("第")[0].strip() or text
        return None

    def _extract_chapter(self, soup: BeautifulSoup) -> dict:
        title = "Unknown Chapter"
        tit = soup.select_one(".reader-chapter-tit")
        if tit:
            title = tit.get_text(strip=True)
        else:
            h1 = soup.select_one("h1 span") or soup.select_one("h1")
            if h1:
                title = h1.get_text(strip=True)

        article = soup.select_one(".reader-article")
        if article is None:
            raise ValueError(f"No .reader-article for: {title}")
        paragraphs = [p.get_text(strip=True) for p in article.find_all("p")]
        paragraphs = [p for p in paragraphs if p]
        if not paragraphs:
            raise ValueError(f"Empty content for chapter: {title}")
        return {"title": title, "paragraphs": paragraphs}

    def _next_chapter_url(self, soup: BeautifulSoup) -> str | None:
        link = soup.select_one("a.nextChapter") or soup.select_one(".reader-nextChapter a")
        if link and link.get("href") and "javascript" not in link["href"]:
            return self._abs_url(link["href"])
        return None

    def _catalog_page_url(self, book_id: str, page: int) -> str:
        return f"{BASE_URL}/book/catalog-{book_id}-{page}.html"

    def _parse_catalog_page(self, soup: BeautifulSoup) -> list[tuple[int, str, str]]:
        html = str(soup)
        rows: list[tuple[int, str, str]] = []
        for href, title in _CHAPTER_HREF_RE.findall(html):
            title = re.sub(r"\s+", " ", title).strip()
            n = parse_zh_title_num(title)
            if n is None:
                continue
            rows.append((n, title, self._abs_url(href)))
        return rows

    def _catalog_page_count(self, soup: BeautifulSoup) -> int:
        nums = [int(m.group(2)) for m in _CATALOG_RE.finditer(str(soup))]
        return max(nums) if nums else 1

    def _fetch_catalog(self, book_id: str) -> list[dict]:
        old_delay = self.delay
        self.delay = (1.0, 2.0)
        try:
            return self._fetch_catalog_pages(book_id)
        finally:
            self.delay = old_delay

    def _fetch_catalog_pages(self, book_id: str) -> list[dict]:
        first = self.fetch(self._catalog_page_url(book_id, 1))
        n_pages = self._catalog_page_count(first)
        logger.info(f"iQiyi catalog: {n_pages} pages")
        seen: dict[int, dict] = {}
        for page in range(1, n_pages + 1):
            rows: list[tuple[int, str, str]] = []
            for attempt in range(1, 6):
                soup = first if page == 1 and attempt == 1 else self.fetch(
                    self._catalog_page_url(book_id, page)
                )
                rows = self._parse_catalog_page(soup)
                if rows:
                    break
                page_title = soup.title.get_text(strip=True) if soup.title else "?"
                logger.warning(
                    f"Catalog page {page} empty (title={page_title!r}) — retry {attempt}/5"
                )
                if self._tor_enabled:
                    self._renew_ip()
                time.sleep(3)
            if not rows:
                logger.error(f"Catalog page {page} still empty after retries")
            for n, title, url in rows:
                if n not in seen:
                    seen[n] = {"num": n, "title": title, "url": url}
            logger.info(f"  page {page}: {len(rows)} links (unique so far {len(seen)})")
        catalog = [seen[k] for k in sorted(seen)]
        logger.info(f"Catalog unique chapter numbers: {len(catalog)}")
        return catalog

    def _local_chapter_nums(self, slug: str) -> set[int]:
        nums: set[int] = set()
        try:
            index = self._read_json_any(self.output_dir(slug) / "chapters_index.json")
        except FileNotFoundError:
            return nums
        if not isinstance(index, list):
            return nums
        for e in index:
            title = e.get("title") if isinstance(e, dict) else None
            if not title:
                continue
            n = parse_local_title_num(title)
            if n:
                nums.add(n)
        return nums

    def _missing_jobs(self, start_url: str) -> list[tuple[int, str]]:
        slug = self._extract_slug(start_url)
        book_id = self._book_id(start_url)
        catalog = self._fetch_catalog(book_id)
        local_nums = self._local_chapter_nums(slug)
        missing = [item for item in catalog if item["num"] not in local_nums]
        logger.info(
            f"Local unique nums={len(local_nums)}  iQiyi={len(catalog)}  missing={len(missing)}"
        )
        if missing:
            sample = ", ".join(str(m["num"]) for m in missing[:12])
            logger.info(f"Missing sample: {sample}{'…' if len(missing) > 12 else ''}")
        existing = self._rebuild_index(slug)
        next_idx = (max((ch["index"] for ch in existing), default=-1) + 1)
        return [(next_idx + i, item["url"]) for i, item in enumerate(missing)]

    def crawl(self, start_url: str, start_index: int = 0, max_chapters: int = 0) -> list[dict]:
        self.warmup()
        slug = self._extract_slug(start_url)
        jobs = self._missing_jobs(start_url)
        if max_chapters:
            jobs = jobs[:max_chapters]
        if not jobs:
            logger.info("No missing chapters — nothing to crawl")
            return self._rebuild_index(slug)

        vol_num = self._get_next_vol_num(slug)
        buffer: list[dict] = []
        story_title = self._extract_story_title(BeautifulSoup("", _HTML_PARSER))
        prev_url: str | None = None
        try:
            for idx, url in jobs:
                logger.info(f"Crawling chapter {idx + 1}: {url}")
                chapter = None
                for attempt in range(1, 4):
                    try:
                        soup = self.fetch(url, referer=prev_url)
                        if story_title is None:
                            story_title = self._extract_story_title(soup)
                        chapter = self._extract_chapter(soup)
                        break
                    except Exception as e:
                        logger.warning(f"  attempt {attempt}/3 failed: {e}")
                        if self._tor_enabled:
                            self._renew_ip()
                if chapter is None:
                    logger.error(f"Skipping {url}")
                    continue
                chapter["index"] = idx
                buffer.append(chapter)
                logger.info(f"  -> {chapter['title']} ({len(chapter['paragraphs'])} paragraphs)")
                if len(buffer) >= self.CHAPTERS_PER_VOL:
                    self.save_volume(buffer, vol_num, slug)
                    logger.info(f"Saved vol {vol_num} ({len(buffer)} chapters)")
                    vol_num += 1
                    buffer = []
                prev_url = url
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        finally:
            if buffer:
                self.save_volume(buffer, vol_num, slug)
                logger.info(f"Saved partial vol {vol_num} ({len(buffer)} chapters)")
            all_index = self._rebuild_index(slug)
            if all_index:
                self.save_index(all_index, slug)
            if story_title:
                self.save_json({"story_title": story_title}, self.output_dir(slug) / "metadata.json")
            self._save_cookies()
            logger.info(f"Crawl complete: {len(all_index)} total chapters indexed")
        return self._rebuild_index(slug)

    def crawl_parallel(
        self, start_url: str, start_index: int = 0, max_chapters: int = 0, workers: int = 3
    ) -> list[dict]:
        self.warmup()
        slug = self._extract_slug(start_url)
        jobs = self._missing_jobs(start_url)
        if max_chapters:
            jobs = jobs[:max_chapters]
        if not jobs:
            logger.info("No missing chapters — nothing to crawl")
            return self._rebuild_index(slug)
        if not self.canary_check(jobs[0][1]):
            return []
        return self._parallel_fetch(jobs, slug, workers)
