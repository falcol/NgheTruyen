import abc
import gzip
import json
import os
import time
import random
import logging
import threading
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"

# Try lxml (2-3x faster), fall back to stdlib parser
try:
    import lxml  # noqa: F401
    _HTML_PARSER = "lxml"
except ImportError:
    _HTML_PARSER = "html.parser"


# Pool of realistic browser User-Agents (Chrome / Firefox / Safari, recent versions).
# Rotated per-request so traffic doesn't look like one bot.
USER_AGENT_POOL = [
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0",
    "Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
]

# Slight variations — vi-VN as primary always (region-appropriate for VN sites).
ACCEPT_LANGUAGE_POOL = [
    "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
    "vi-VN,vi;q=0.9",
    "vi,vi-VN;q=0.9,en;q=0.8",
    "vi-VN,vi;q=0.9,en;q=0.5",
]


class BaseCrawler(abc.ABC):
    """Base class for all site crawlers."""

    # Subclasses override with site homepage for cookie warm-up + default Referer.
    BASE_URL: str | None = None

    # When True, save data as gzipped + minified JSON (.json.gz, ~80% smaller).
    # When False, save as pretty-printed .json (debug-friendly).
    # Reader auto-detects both formats so it's safe to flip.
    COMPRESS: bool = True

    # Reading pause: every N chunks (CHAPTERS_PER_VOL=50 each), sleep a longer
    # window to mimic a human "reading break". Set N=0 to disable.
    READING_PAUSE_EVERY_CHUNKS: int = 4         # ≈ every 200 chapters
    READING_PAUSE_RANGE: tuple[float, float] = (20.0, 45.0)

    def __init__(self, site_name: str, delay: tuple[float, float] = (2.0, 4.0), dest_dir: str | None = None):
        self.site_name = site_name
        self.dest_dir = dest_dir
        self.delay = delay
        self.parallel_delay = (1.0, 2.0)
        self._thread_local = threading.local()
        self._next_vol_cache: dict[str, int] = {}

        # Adaptive delay state — shared across threads via lock.
        # Multiplier scales delay range when server pushes back; recovers slowly on success.
        self._adaptive_lock = threading.Lock()
        self._adaptive_multiplier: float = 1.0
        self._consecutive_success: int = 0
        self._warmed_up: bool = False

        self.session = self._build_session()
        self._load_cookies()  # Restore persistent cookies from previous runs

    def _build_session(self) -> requests.Session:
        """Create a session with larger connection pool for parallel fetches.

        Per-request headers are set in `_pick_headers`; session only holds
        Accept + connection settings shared by all requests.
        """
        s = requests.Session()
        adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20)
        s.mount("http://", adapter)
        s.mount("https://", adapter)
        s.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            # Only advertise encodings `requests` can auto-decode.
            # Adding `br` here without the `brotli` package installed makes the
            # server send Brotli-compressed bytes that requests can't decode,
            # so resp.text returns garbage and BeautifulSoup parses nothing.
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
        })
        return s

    def _pick_headers(self, referer: str | None = None) -> dict[str, str]:
        """Random per-request headers: rotate UA + Accept-Language + Referer.

        Each request looks like a different browser session — reduces
        fingerprint-based rate-limiting.
        """
        headers = {
            "User-Agent": random.choice(USER_AGENT_POOL),
            "Accept-Language": random.choice(ACCEPT_LANGUAGE_POOL),
        }
        ref = referer or self.BASE_URL
        if ref:
            headers["Referer"] = ref
        return headers

    def _rate_limit(self, delay_range: tuple[float, float]) -> None:
        """Per-thread strict-gap rate limiter, scaled by adaptive multiplier."""
        with self._adaptive_lock:
            mult = self._adaptive_multiplier
        target = random.uniform(*delay_range) * mult
        last = getattr(self._thread_local, "last_request", 0.0)
        if last > 0:
            remaining = target - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)
        self._thread_local.last_request = time.monotonic()

    def _on_success(self) -> None:
        """Record successful request; recover adaptive multiplier slowly."""
        with self._adaptive_lock:
            self._consecutive_success += 1
            # Every 10 consecutive successes, shrink multiplier 10% (toward 1.0)
            if self._consecutive_success % 10 == 0 and self._adaptive_multiplier > 1.0:
                old = self._adaptive_multiplier
                self._adaptive_multiplier = max(1.0, self._adaptive_multiplier * 0.9)
                logger.info(f"Adaptive recover: {old:.2f}x -> {self._adaptive_multiplier:.2f}x")

    def _on_rate_limited(self) -> None:
        """Record rate-limit hit; bump multiplier aggressively (capped at 5x)."""
        with self._adaptive_lock:
            self._consecutive_success = 0
            old = self._adaptive_multiplier
            self._adaptive_multiplier = min(5.0, self._adaptive_multiplier * 1.5)
            logger.warning(f"Rate-limited — adaptive multiplier {old:.2f}x -> {self._adaptive_multiplier:.2f}x")

    @staticmethod
    def _parse_retry_after(resp: requests.Response) -> float | None:
        """Parse Retry-After header: integer seconds or HTTP-date. Returns None if absent/invalid."""
        val = resp.headers.get("Retry-After")
        if not val:
            return None
        try:
            return float(val)
        except ValueError:
            try:
                dt = parsedate_to_datetime(val)
                return max(0.0, (dt - datetime.now(timezone.utc)).total_seconds())
            except (ValueError, TypeError):
                return None

    def _request(
        self,
        url: str,
        session: requests.Session,
        delay_range: tuple[float, float],
        retries: int,
        allow_404: bool,
        referer: str | None = None,
    ) -> BeautifulSoup | None:
        """Unified fetch: rate-limit, rotate headers, honor Retry-After, retry with backoff."""
        for attempt in range(1, retries + 1):
            try:
                self._rate_limit(delay_range)
                headers = self._pick_headers(referer=referer)
                resp = session.get(url, timeout=15, headers=headers)

                if allow_404 and resp.status_code == 404:
                    return None

                # Rate-limit / temporary block: respect server's Retry-After
                if resp.status_code in (429, 503):
                    self._on_rate_limited()
                    wait = self._parse_retry_after(resp)
                    if wait is None:
                        wait = min(60.0, 5.0 * (2 ** attempt))  # Long backoff
                    logger.warning(f"HTTP {resp.status_code} on {url} — sleeping {wait:.1f}s (attempt {attempt}/{retries})")
                    if attempt == retries:
                        resp.raise_for_status()
                    time.sleep(wait)
                    continue

                # Soft block (some sites return 403 instead of 429)
                if resp.status_code == 403:
                    self._on_rate_limited()
                    if attempt == retries:
                        resp.raise_for_status()
                    wait = min(60.0, 5.0 * (2 ** attempt))
                    logger.warning(f"HTTP 403 on {url} — sleeping {wait:.1f}s (attempt {attempt}/{retries})")
                    time.sleep(wait)
                    continue

                resp.raise_for_status()
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
        """Sequential fetch with main session. Raises on persistent failure."""
        soup = self._request(url, self.session, self.delay, retries, allow_404=False, referer=referer)
        assert soup is not None  # allow_404=False => raise on failure
        return soup

    def warmup(self) -> None:
        """One-time cookie warm-up: visit homepage so server sets initial cookies/CSRF.

        Called automatically before first crawl; idempotent. Skipped if BASE_URL not set.
        Persists fresh cookies to disk for next run.
        """
        if self._warmed_up or not self.BASE_URL:
            return
        try:
            logger.info(f"Warming up cookies via {self.BASE_URL}")
            headers = self._pick_headers(referer=None)
            # No Referer for the very first request — looks like fresh tab open
            self.session.get(self.BASE_URL, timeout=15, headers=headers)
            self._warmed_up = True
            self._save_cookies()
        except Exception as e:
            # Non-fatal: warmup is opportunistic
            logger.warning(f"Warmup failed (non-fatal): {e}")
            self._warmed_up = True  # don't retry every chapter

    def canary_check(self, url: str) -> bool:
        """Probe a single URL before committing to full crawl.

        Returns True if site responds normally, False if blocked/unreachable.
        Cheap insurance: 1 request to detect "wall" instead of burning 4200 retries.
        """
        logger.info(f"Canary check: {url}")
        try:
            soup = self.fetch_parallel(url, retries=2)
            if soup is None:
                logger.warning("Canary returned None (404). Continuing — first chapter may not exist at this URL.")
                return True
            logger.info("Canary OK — proceeding with full crawl")
            return True
        except Exception as e:
            logger.error(f"Canary failed: {e}")
            logger.error("Server appears to be blocking. Aborting — try again later or change IP/UA.")
            return False

    def _get_thread_session(self) -> requests.Session:
        """Create or return a thread-local session sharing the connection pool config + cookies.

        Snapshots the main session's cookies once at thread-session creation time —
        good enough for warm-up cookies. Workers don't share live cookie updates,
        which is desirable (avoids cross-thread mutation).
        """
        if not hasattr(self._thread_local, "session"):
            s = self._build_session()
            # Inherit cookies from the warmed-up main session
            s.cookies.update(self.session.cookies.get_dict())
            self._thread_local.session = s
        return self._thread_local.session

    def _cookie_path(self) -> Path:
        """Site-scoped cookie file. One file per real source site (ignores --dest)."""
        return DATA_DIR / self.site_name / ".cookies.json"

    def _load_cookies(self) -> None:
        """Restore cookies from disk. Silently skipped if file missing/corrupt."""
        path = self._cookie_path()
        if not path.exists():
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and data:
                self.session.cookies.update(data)
                logger.info(f"Loaded {len(data)} cookies from {path.name}")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to load cookies ({path}): {e}")

    def _save_cookies(self) -> None:
        """Persist current main-session cookies to disk for next run."""
        data = self.session.cookies.get_dict()
        if not data:
            return
        path = self._cookie_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except OSError as e:
            logger.warning(f"Failed to save cookies ({path}): {e}")

    def fetch_parallel(self, url: str, retries: int = 3) -> BeautifulSoup | None:
        """Thread-safe fetch. Returns None on 404 (chapter not found)."""
        session = self._get_thread_session()
        return self._request(url, session, self.parallel_delay, retries, allow_404=True)

    def output_dir(self, story_slug: str) -> Path:
        """Return and create output directory for a story."""
        if self.dest_dir:
            path = DATA_DIR / self.dest_dir / story_slug
        else:
            path = DATA_DIR / self.site_name / story_slug
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save_json(self, data: dict | list, filepath: Path) -> None:
        """Save data as JSON. If COMPRESS=True, output `.json.gz` minified (~80% smaller).

        The `.json.gz` suffix is appended automatically — caller passes the logical
        `.json` path. Reader (`_read_json_any`) handles both formats transparently.
        """
        if self.COMPRESS:
            text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            target = filepath.with_name(filepath.name + ".gz")
            with gzip.open(target, "wt", encoding="utf-8", compresslevel=9) as f:
                f.write(text)
            logger.info(f"Saved: {target}")
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved: {filepath}")

    @staticmethod
    def _read_json_any(filepath: Path) -> dict | list:
        """Read either `.json` or `.json.gz` from the same logical path.

        Tries the gzipped version first (preferred when COMPRESS=True), falls back to plain.
        Raises FileNotFoundError if neither exists.
        """
        gz_path = filepath.with_name(filepath.name + ".gz")
        if gz_path.exists():
            with gzip.open(gz_path, "rt", encoding="utf-8") as f:
                return json.load(f)
        if filepath.exists():
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        raise FileNotFoundError(f"Neither {filepath} nor {gz_path} exists")

    CHAPTERS_PER_VOL = 50

    def save_volume(self, vol_chapters: list[dict], vol_num: int, story_slug: str) -> None:
        """Save a single volume file."""
        out = self.output_dir(story_slug)
        ch_first = vol_chapters[0]["index"] + 1
        ch_last = vol_chapters[-1]["index"] + 1
        vol_data = {
            "volume": vol_num,
            "chapterRange": [ch_first, ch_last],
            "chapters": vol_chapters,
        }
        filename = f"vol-{vol_num:03d}-ch{ch_first:03d}-{ch_last:03d}.json"
        self.save_json(vol_data, out / filename)

    def save_index(self, index_meta: list[dict], story_slug: str) -> None:
        """Save chapters index file."""
        out = self.output_dir(story_slug)
        self.save_json(index_meta, out / "chapters_index.json")

    def _save_progress(self, progress: dict, story_slug: str) -> None:
        out = self.output_dir(story_slug)
        with open(out / "_progress.json", "w", encoding="utf-8") as f:
            json.dump(progress, f, ensure_ascii=False, indent=2)

    def _load_progress(self, story_slug: str) -> dict | None:
        path = self.output_dir(story_slug) / "_progress.json"
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return None

    def _cleanup_progress(self, story_slug: str) -> None:
        path = self.output_dir(story_slug) / "_progress.json"
        if path.exists():
            path.unlink()

    def _get_next_vol_num(self, story_slug: str) -> int:
        cached = self._next_vol_cache.get(story_slug)
        if cached is not None:
            return cached
        out = self.output_dir(story_slug)
        if not out.exists():
            self._next_vol_cache[story_slug] = 1
            return 1
        max_vol = 0
        # Match both vol-NNN-*.json and vol-NNN-*.json.gz
        for f in list(out.glob("vol-*.json")) + list(out.glob("vol-*.json.gz")):
            parts = f.name.split("-")
            if len(parts) >= 2 and parts[0] == "vol":
                try:
                    max_vol = max(max_vol, int(parts[1]))
                except ValueError:
                    pass
        next_vol = max_vol + 1
        self._next_vol_cache[story_slug] = next_vol
        return next_vol

    def _bump_vol_cache(self, story_slug: str) -> None:
        if story_slug in self._next_vol_cache:
            self._next_vol_cache[story_slug] += 1

    def _rebuild_index(self, story_slug: str) -> list[dict]:
        out = self.output_dir(story_slug)
        if not out.exists():
            return []
        # Collect both .json and .json.gz vol files; sort by name (vol number)
        vol_files = sorted(
            list(out.glob("vol-*.json")) + list(out.glob("vol-*.json.gz")),
            key=lambda p: p.name,
        )
        # Use dict keyed by index for dedup (later vols overwrite earlier)
        index_map: dict[int, dict] = {}
        for vol_file in vol_files:
            if vol_file.suffix == ".gz":
                with gzip.open(vol_file, "rt", encoding="utf-8") as f:
                    vol_data = json.load(f)
            else:
                with open(vol_file, "r", encoding="utf-8") as f:
                    vol_data = json.load(f)
            for ch in vol_data.get("chapters", []):
                index_map[ch["index"]] = {"index": ch["index"], "title": ch["title"]}
        index = sorted(index_map.values(), key=lambda x: x["index"])
        return index

    def _predict_urls(self, start_url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]] | None:
        """Override in subclass to predict URLs without fetching. Returns None if not possible."""
        return None

    def crawl_parallel(self, start_url: str, start_index: int = 0, max_chapters: int = 0, workers: int = 3) -> list[dict]:
        """Crawl with parallel fetch when URL prediction is available."""
        self.warmup()

        # Canary: probe one URL before committing to a long crawl
        if not self.canary_check(start_url):
            return []

        slug = self._extract_slug(start_url)
        predicted = self._predict_urls(start_url, start_index, max_chapters)

        if predicted:
            logger.info(f"Predicted {len(predicted)} URLs, fetching with {workers} workers")
            return self._parallel_fetch(predicted, slug, workers)
        else:
            logger.info("No URL prediction available, using sequential crawl with reduced delay")
            old_delay = self.delay
            self.delay = (1.0, 1.5)
            try:
                return self.crawl(start_url, start_index=start_index, max_chapters=max_chapters)
            finally:
                self.delay = old_delay

    def _parallel_fetch(self, url_list: list[tuple[int, str]], slug: str, workers: int) -> list[dict]:
        """Fetch chapters in parallel, chunk by chunk to bound memory usage.

        Resume: filter out indices already saved in vol files.
        Early stop: if a chunk returns 100% 404 (no successes), assume end-of-story.
        """
        chunk_size = self.CHAPTERS_PER_VOL
        all_failed: list[tuple[int, str]] = []
        story_title = None

        # Resume: drop URLs whose chapter index already exists in saved vols
        existing_indices = {ch["index"] for ch in self._rebuild_index(slug)}
        if existing_indices:
            before = len(url_list)
            url_list = [(idx, url) for idx, url in url_list if idx not in existing_indices]
            skipped = before - len(url_list)
            if skipped:
                logger.info(f"Resume: skipping {skipped} already-saved chapters")

        if not url_list:
            logger.info("Nothing to fetch (all chapters already saved)")
            return self._rebuild_index(slug)

        vol_num = self._get_next_vol_num(slug)

        def worker(idx: int, url: str) -> tuple[dict | None, str | None]:
            soup = self.fetch_parallel(url)
            if soup is None:
                return None, None
            chapter = self._extract_chapter(soup)
            chapter["index"] = idx
            title = self._extract_story_title(soup)
            return chapter, title

        chunks = [url_list[i:i + chunk_size] for i in range(0, len(url_list), chunk_size)]
        logger.info(f"Fetching {len(url_list)} chapters in {len(chunks)} chunks of {chunk_size}")

        for chunk_num, chunk in enumerate(chunks, 1):
            results: dict[int, dict] = {}
            transient_failures: list[tuple[int, str]] = []  # exceptions, retryable
            not_found: list[tuple[int, str]] = []           # 404s, deterministic

            logger.info(f"Chunk {chunk_num}/{len(chunks)}: {len(chunk)} chapters")

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {pool.submit(worker, idx, url): (idx, url) for idx, url in chunk}

                for f in as_completed(futures):
                    idx, url = futures[f]
                    try:
                        chapter, title = f.result()
                        if chapter is None:
                            not_found.append((idx, url))
                        else:
                            results[idx] = chapter
                            if title and not story_title:
                                story_title = title
                                logger.info(f"Story title: {story_title}")
                            logger.info(f"  Ch {idx + 1}: {chapter['title']} ({len(chapter['paragraphs'])} para)")
                    except Exception as e:
                        transient_failures.append((idx, url))
                        logger.error(f"  Ch {idx + 1} failed: {e}")

            # Retry only transient failures (404s won't change on retry)
            if transient_failures:
                logger.info(f"Retrying {len(transient_failures)} failed chapters...")
                for idx, url in transient_failures:
                    try:
                        soup = self.fetch_parallel(url)
                        if soup is not None:
                            chapter = self._extract_chapter(soup)
                            chapter["index"] = idx
                            results[idx] = chapter
                            title = self._extract_story_title(soup)
                            if title and not story_title:
                                story_title = title
                            logger.info(f"  Retry Ch {idx + 1}: OK - {chapter['title']}")
                            continue
                    except Exception as e:
                        logger.error(f"  Retry Ch {idx + 1} failed again: {e}")
                    all_failed.append((idx, url))

            # Save this chunk as a volume, release memory
            if results:
                sorted_chunk = sorted(results.values(), key=lambda x: x["index"])
                self.save_volume(sorted_chunk, vol_num, slug)
                logger.info(f"Saved vol {vol_num} ({len(sorted_chunk)} chapters)")
                vol_num += 1
                self._bump_vol_cache(slug)

            # Reading pause: occasionally take a longer break (mimics human reading session).
            # Skip if adaptive multiplier already throttling — we're slow enough.
            if (
                self.READING_PAUSE_EVERY_CHUNKS > 0
                and chunk_num % self.READING_PAUSE_EVERY_CHUNKS == 0
                and chunk_num < len(chunks)  # don't pause after last chunk
                and self._adaptive_multiplier <= 1.5
            ):
                pause = random.uniform(*self.READING_PAUSE_RANGE)
                logger.info(f"Reading pause: sleeping {pause:.0f}s (mimics user taking a break)")
                time.sleep(pause)

            # Early stop: entire chunk was 404 (likely past end-of-story)
            if not results and len(not_found) == len(chunk):
                logger.info(f"Chunk {chunk_num} returned all 404s — stopping early (likely end of story)")
                # Track 404s as failed for reporting, but don't try them again
                all_failed.extend(not_found)
                break

            # Also collect 404s as failures (for the report at the end)
            all_failed.extend(not_found)

        # Final: index + metadata (rebuild ONCE at end, not per-chunk)
        if all_failed:
            logger.warning(f"{len(all_failed)} chapters could not be fetched:")
            for idx, url in all_failed:
                logger.warning(f"  Ch {idx + 1}: {url}")

        all_index = self._rebuild_index(slug)
        if all_index:
            self.save_index(all_index, slug)
        if story_title:
            out = self.output_dir(slug)
            self.save_json({"story_title": story_title}, out / "metadata.json")

        # Persist any cookies the server set during the crawl (returning visitor signal)
        self._save_cookies()

        logger.info(f"Total: {len(all_index)} chapters saved")
        return all_index

    def _save_chapters(self, chapters: list[dict], slug: str, story_title: str | None) -> None:
        """Sort chapters and save as volumes + index."""
        vol_num = self._get_next_vol_num(slug)
        buffer = []

        for ch in chapters:
            buffer.append(ch)
            if len(buffer) >= self.CHAPTERS_PER_VOL:
                self.save_volume(buffer, vol_num, slug)
                logger.info(f"Saved vol {vol_num} ({len(buffer)} chapters)")
                vol_num += 1
                buffer = []

        if buffer:
            self.save_volume(buffer, vol_num, slug)
            logger.info(f"Saved vol {vol_num} ({len(buffer)} chapters)")

        all_index = self._rebuild_index(slug)
        if all_index:
            self.save_index(all_index, slug)
        if story_title:
            out = self.output_dir(slug)
            self.save_json({"story_title": story_title}, out / "metadata.json")

        logger.info(f"Total: {len(chapters)} chapters saved")

    @abc.abstractmethod
    def _extract_chapter(self, soup) -> dict:
        """Extract chapter title and paragraphs from a parsed page."""
        ...

    @abc.abstractmethod
    def _next_chapter_url(self, soup) -> str | None:
        """Find the next chapter URL from the current page. Return None if last."""
        ...

    @abc.abstractmethod
    def _extract_story_title(self, soup) -> str | None:
        """Extract the story title from the page."""
        ...

    @abc.abstractmethod
    def _extract_slug(self, url: str) -> str:
        """Extract story slug from URL for output directory naming."""
        ...

    def crawl(self, start_url: str, start_index: int = 0, max_chapters: int = 0) -> list[dict]:
        """
        Crawl all chapters starting from start_url by following next links.
        Saves each volume to disk as soon as it's complete.
        Auto-saves buffer on crash/interrupt. Resumes from last saved progress.
        """
        self.warmup()
        slug = self._extract_slug(start_url)

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
        all_index: list[dict] = []

        prev_url: str | None = None
        try:
            while url:
                logger.info(f"Crawling chapter {index + 1}: {url}")

                try:
                    soup = self.fetch(url, referer=prev_url)
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

                if len(buffer) >= self.CHAPTERS_PER_VOL:
                    self.save_volume(buffer, vol_num, slug)
                    logger.info(f"Saved vol {vol_num} ({len(buffer)} chapters)")
                    vol_num += 1
                    buffer = []

                next_url = self._next_chapter_url(soup)
                self._save_progress({
                    "next_url": next_url,
                    "next_index": index + 1,
                    "story_title": story_title,
                }, slug)

                if max_chapters and session_count >= max_chapters:
                    logger.info(f"Reached max_chapters limit ({max_chapters})")
                    break

                prev_url = url
                url = next_url
                index += 1
            else:
                completed = True

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
                out = self.output_dir(slug)
                self.save_json({"story_title": story_title}, out / "metadata.json")

            if completed:
                self._cleanup_progress(slug)
                logger.info(f"Crawl complete: {len(all_index)} total chapters")
            else:
                logger.info(f"Saved {len(all_index)} chapters. Run again to resume.")

            # Persist cookies for next run — survive crashes/interrupts via finally
            self._save_cookies()

        return all_index
