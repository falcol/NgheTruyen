# Async Parallel Crawler Design

## Goal

Crawl 1000 chapters in ~7 minutes (currently ~50 minutes) while maintaining correct chapter order and avoiding rate-limit blocks.

## Architecture

Producer-Consumer pipeline using asyncio + aiohttp:

```
Producer (sequential) ──► asyncio.Queue ──► Consumer Pool (3 workers)
  discover next_url         URL items        fetch + parse
                                               │
                                               ▼
                                    Results dict[index] = chapter
                                    Sort → flush volumes
```

## Components

### AsyncBaseCrawler (new class in base.py)

- `async_fetch(url)` — aiohttp equivalent of `fetch()`, with semaphore-based concurrency control
- `async crawl()` — override point for async crawl implementation
- Adaptive delay: default 1.0-2.0s, doubles on 429, resets after 10 OK requests
- Default 3 consumer workers (configurable)

### Producer

- Runs sequentially, fetches pages lightly to extract `next_url`
- Pushes `(index, url)` tuples into asyncio.Queue
- Stops when no more next_url or max_chapters reached

### Consumer Pool

- N workers (default 3) pull from queue
- Each does full fetch + `_extract_chapter()` + `_extract_story_title()`
- Results go into shared `dict[int, dict]` keyed by chapter index
- Semaphore controls max concurrent connections

### Volume Flush

- Periodically check results dict for consecutive completed indices
- Flush every 50 chapters as before
- Final flush in `finally` block

## CLI Changes

- `run.py`: add `--async` flag to enable parallel mode
- Default behavior (no flag) remains sequential crawl (backward compat)
- `--workers N` to override consumer count (default 3)

## File Changes

| File | Change |
|------|--------|
| `crawler/requirements.txt` | Add `aiohttp` |
| `crawler/base.py` | Add `AsyncBaseCrawler` class |
| `crawler/metruyencv.py` | Add `async crawl()` using pipeline |
| `crawler/truyenqq.py` | Add `async crawl()` using pipeline |
| `crawler/metruyenchu.py` | Add `async crawl()` using pipeline |
| `crawler/run.py` | Add `--async` flag, `--workers` flag |

## Preserved Behavior

- Sequential `crawl()` methods unchanged — still work as before
- Resume/progress logic identical
- Volume and index file formats identical
- `_extract_chapter()`, `_next_chapter_url()`, `_extract_slug()` reused as-is

## Rate Limiting Strategy

- Semaphore limits concurrent connections to worker count
- Per-request delay: 1.0-2.0s (reduced from 2.0-4.0s since semaphore caps concurrency)
- On 429: double current delay, retry with exponential backoff
- After 10 consecutive OK: reset delay to default range

## Error Handling

- Single chapter failure: log error, mark index as failed, continue
- Producer failure: stop queue, let consumers drain
- All errors logged; failed indices tracked in progress file for resume
