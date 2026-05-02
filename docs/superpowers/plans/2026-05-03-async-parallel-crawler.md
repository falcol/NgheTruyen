# Async Parallel Crawler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crawl 1000 chapters in ~8 minutes instead of ~50 minutes using parallel fetching with URL prediction.

**Architecture:** ThreadPoolExecutor + requests (no new dependency). URL prediction generates all chapter URLs upfront, then parallel workers fetch+parse concurrently with per-request delay as rate limiter. Falls back to sequential crawl with reduced delay when URLs aren't predictable.

**Tech Stack:** Python 3, requests, BeautifulSoup4, concurrent.futures.ThreadPoolExecutor

**Speed expectations:**
- metruyencv (URL prediction): 3 workers × 1.5s/chapter = ~8 min for 1000 chapters
- truyenqq/metruyenchu (sequential fallback, reduced delay): ~25 min for 1000 chapters (1.5s vs 3s)

---

### Task 1: Add parallel infrastructure to BaseCrawler

**Files:**
- Modify: `crawler/base.py`

- [ ] **Step 1: Add imports and thread-local session to BaseCrawler**

Add imports at top of `crawler/base.py`:

```python
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
```

Add to `__init__` after `self.delay = delay`:

```python
self.parallel_delay = (1.0, 2.0)
self._thread_local = threading.local()
```

Add new method after `fetch()`:

```python
def _get_thread_session(self) -> requests.Session:
    """Create or return a thread-local requests.Session."""
    if not hasattr(self._thread_local, "session"):
        s = requests.Session()
        s.headers.update(self.session.headers)
        self._thread_local.session = s
    return self._thread_local.session

def fetch_parallel(self, url: str, retries: int = 3) -> BeautifulSoup | None:
    """Thread-safe fetch. Returns None on 404 (chapter not found)."""
    session = self._get_thread_session()
    for attempt in range(1, retries + 1):
        try:
            time.sleep(random.uniform(*self.parallel_delay))
            resp = session.get(url, timeout=15)
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return BeautifulSoup(resp.text, "html.parser")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
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
```

- [ ] **Step 2: Add crawl_parallel, _predict_urls, _parallel_fetch, _save_chapters methods**

Add before the abstract `crawl()` method:

```python
def _predict_urls(self, start_url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]] | None:
    """Override in subclass to predict URLs without fetching. Returns None if not possible."""
    return None

def crawl_parallel(self, start_url: str, start_index: int = 0, max_chapters: int = 0, workers: int = 3) -> list[dict]:
    """Crawl with parallel fetch when URL prediction is available."""
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
    """Fetch chapters in parallel using ThreadPoolExecutor."""
    results: dict[int, dict] = {}
    story_title = None
    failed = 0

    def worker(idx: int, url: str) -> tuple[dict | None, str | None]:
        nonlocal story_title
        soup = self.fetch_parallel(url)
        if soup is None:
            return None, None
        chapter = self._extract_chapter(soup)
        chapter["index"] = idx
        title = self._extract_story_title(soup)
        return chapter, title

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(worker, idx, url): idx for idx, url in url_list}

        for f in as_completed(futures):
            idx = futures[f]
            try:
                chapter, title = f.result()
                if chapter is None:
                    failed += 1
                else:
                    results[idx] = chapter
                    if title and not story_title:
                        story_title = title
                    logger.info(f"  Ch {idx + 1}: {chapter['title']} ({len(chapter['paragraphs'])} para)")
            except Exception as e:
                failed += 1
                logger.error(f"  Ch {idx + 1} failed: {e}")

    if failed:
        logger.warning(f"{failed} chapters failed or not found (404)")

    sorted_chapters = sorted(results.values(), key=lambda x: x["index"])
    self._save_chapters(sorted_chapters, slug, story_title)
    return self._rebuild_index(slug)

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
```

- [ ] **Step 3: Verify no syntax errors**

Run: `cd /home/falcol/NgheTruyen && python -c "from crawler.base import BaseCrawler; print('OK')"`

Expected: `OK` (import succeeds, abstract class can't be instantiated but import works)

- [ ] **Step 4: Verify sequential mode still works**

Run: `python -m crawler.run metruyencv "https://metruyencv.xyz/truyen/..." --max 2`

Expected: Same behavior as before (2 chapters, sequential, 2-4s delay)

- [ ] **Step 5: Commit**

```bash
git add crawler/base.py
git commit -m "feat: add parallel crawl infrastructure to BaseCrawler"
```

---

### Task 2: Add URL prediction to MetruyencvCrawler

**Files:**
- Modify: `crawler/metruyencv.py`

metruyencv URLs follow the pattern `https://metruyencv.xyz/truyen/{slug}/chuong-{N}/` where N increments by 1. This makes prediction straightforward.

- [ ] **Step 1: Add _predict_urls method**

Add to `MetruyencvCrawler` class, after `_extract_slug`:

```python
def _predict_urls(self, start_url: str, start_index: int, max_chapters: int) -> list[tuple[int, str]] | None:
    """Predict URLs for metruyencv: /truyen/{slug}/chuong-{N}/"""
    slug = self._extract_slug(start_url)
    match = re.search(r"chuong-(\d+)", start_url)
    if not match:
        return None

    start_ch = int(match.group(1))
    limit = max_chapters if max_chapters > 0 else 2000
    urls = []

    for i in range(limit):
        ch_num = start_ch + i
        url = f"{BASE_URL}truyen/{slug}/chuong-{ch_num}/"
        urls.append((start_index + i, url))

    return urls
```

- [ ] **Step 2: Verify prediction + parallel works**

Run: `python -m crawler.run metruyencv "https://metruyencv.xyz/truyen/..." --parallel --max 5 --workers 3`

Expected: 5 chapters fetched in parallel, ~5-8 seconds total. Log shows "Predicted 5 URLs".

- [ ] **Step 3: Commit**

```bash
git add crawler/metruyencv.py
git commit -m "feat: add URL prediction for metruyencv parallel crawl"
```

---

### Task 3: Update run.py with --parallel and --workers flags

**Files:**
- Modify: `crawler/run.py`

- [ ] **Step 1: Add CLI arguments**

After the `--dest` argument line, add:

```python
parser.add_argument("--parallel", action="store_true", help="Use parallel crawling with URL prediction")
parser.add_argument("--workers", type=int, default=3, help="Number of parallel workers (default: 3)")
```

- [ ] **Step 2: Update main() dispatch**

Replace the last 2 lines of `main()`:

```python
crawler = CRAWLERS[args.site](dest_dir=args.dest)
crawler.crawl(args.url, start_index=args.start, max_chapters=args.max)
```

With:

```python
crawler = CRAWLERS[args.site](dest_dir=args.dest)
if args.parallel:
    crawler.crawl_parallel(args.url, start_index=args.start, max_chapters=args.max, workers=args.workers)
else:
    crawler.crawl(args.url, start_index=args.start, max_chapters=args.max)
```

- [ ] **Step 3: Verify CLI help**

Run: `python -m crawler.run --help`

Expected: Shows `--parallel` and `--workers` in help output.

- [ ] **Step 4: Commit**

```bash
git add crawler/run.py
git commit -m "feat: add --parallel and --workers CLI flags"
```

---

### Task 4: End-to-end manual test

- [ ] **Step 1: Test parallel mode with metruyencv**

Run: `python -m crawler.run metruyencv "<any-story-url>" --parallel --max 10 --workers 3`

Expected:
- Log: "Predicted 10 URLs, fetching with 3 workers"
- 10 chapters complete in ~8-12 seconds
- Volume files saved in `crawler/data/metruyencv/<slug>/`

- [ ] **Step 2: Test fallback mode with truyenqq**

Run: `python -m crawler.run truyenqq "<any-story-url>" --parallel --max 5`

Expected:
- Log: "No URL prediction available, using sequential crawl with reduced delay"
- 5 chapters complete in ~8-10 seconds (1.5s delay instead of 3s)

- [ ] **Step 3: Test sequential mode still works (backward compat)**

Run: `python -m crawler.run metruyencv "<any-story-url>" --max 3`

Expected:
- No "Predicted" or "reduced delay" messages
- Sequential crawl with standard 2-4s delay

- [ ] **Step 4: Final commit (if any fixes needed)**

```bash
git add -A
git commit -m "fix: address issues from e2e testing"
```
