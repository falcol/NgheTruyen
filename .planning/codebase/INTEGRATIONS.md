# External Integrations

**Analysis Date:** 2026-05-19

## APIs & External Services

**Web Scraping (Crawler — Python):**

The crawler (`crawler/`) scrapes Vietnamese story websites. Each site has a dedicated crawler subclass of `BaseCrawler` (`crawler/base.py`).

- **truyenqq.vn** — Story chapter scraping
  - Crawler: `crawler/truyenqq.py` (`TruyenQQCrawler`)
  - Method: HTTP requests + BeautifulSoup HTML parsing
  - Auth: None (public site)
  - Anti-detection: Rotating User-Agent pool, rotating Accept-Language headers, adaptive delay with backoff on 429s, cookie warm-up from homepage

- **metruyenchu.com.vn** — Story chapter scraping
  - Crawler: `crawler/metruyenchu.py` (`MetruyenchuCrawler`)
  - Method: HTTP requests + BeautifulSoup, plus AJAX API at `https://metruyenchu.com.vn/get/listchap/`
  - Auth: None (public site)
  - Special: Uses `X-Requested-With: XMLHttpRequest` headers for chapter list API

- **metruyencv.xyz** — Story chapter scraping
  - Crawler: `crawler/metruyencv.py` (`MetruyencvCrawler`)
  - Method: HTTP requests + BeautifulSoup HTML parsing
  - Auth: None (public site)

- **truyenfullmoi.com** — Story chapter scraping
  - Crawler: `crawler/truyenfullmoi.py` (`TruyenfullmoiCrawler`)
  - Method: HTTP requests + BeautifulSoup HTML parsing
  - Auth: None (public site)
  - Special: Detects non-existent chapters by checking element presence (redirects to homepage, not 404)

**Crawler shared infrastructure** (`crawler/base.py`):
- `requests` library with `HTTPAdapter` for connection pooling
- Threaded parallel crawling via `ThreadPoolExecutor`
- Adaptive rate limiting: increases delay multiplier on server pushback (429/5xx), slowly recovers on success
- Cookie persistence per session (writes `.cookies.json`)
- Resume support via `_progress.json` files
- Output: Gzipped JSON files into `crawler/data/{site_name}/{story_slug}/`

**Web Speech API (Browser-native TTS):**
- Service: Browser's built-in `window.speechSynthesis`
- Usage: `web/src/hooks/useTTS.ts`
- Language: `vi-VN` (Vietnamese)
- Voice selection: Prefers Google > Microsoft > system default Vietnamese voices
- No server-side TTS — entirely client-side
- `msedge-tts` package declared in `package.json` but **not used** in source code

**Google Fonts (CDN):**
- Service: Google Fonts via `next/font/google`
- Usage: `web/src/app/layout.tsx`
- Fonts: Be Vietnam Pro, Literata, Lora, Merriweather, Noto Serif, Source Serif 4
- Optimization: Next.js handles font subsetting, preloading, and CSS generation

## Data Storage

**Databases:**
- None — No database server or ORM used

**File Storage:**
- Local filesystem only
  - Crawler output: `crawler/data/{site}/{slug}/` — JSON files (plain or gzipped)
  - EPUB source files: `epub/` directory (committed, `.epub` files)
  - EPUB cache: `web/public/epub-cache/` — Pre-extracted metadata and chapter content as JSON
  - Symlink: `web/public/data` -> `../../crawler/data` (data sharing between subsystems)

**Caching:**
- Client-side in-memory LRU cache for chapter prefetch (max 12 entries) (`web/src/lib/chapter-prefetch.ts`)
- Server-side: Vercel CDN with `Cache-Control: public, max-age=31536000, immutable` for data files
- API routes: `Cache-Control: private, max-age=3600` for chapter API (`web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts`)
- EPUB meta cache: Versioned JSON files (`EPUB_META_CACHE_VERSION = 2`) checked at build time

## Authentication & Identity

**Auth Provider:**
- Custom HTTP Basic Auth middleware
  - Implementation: `web/src/proxy.ts` + `web/src/lib/site-access.ts`
  - Mechanism: Checks `SITE_BASIC_AUTH_USER` and `SITE_BASIC_AUTH_PASSWORD` env vars
  - Scope: Production only — skipped in development (`NODE_ENV !== "production"`)
  - Matcher: All routes except `_next/static`, `_next/image`, `favicon.ico`, `robots.txt`, `sitemap.xml`
  - This is a site-wide access gate (private personal app), not per-user authentication

## Monitoring & Observability

**Error Tracking:**
- None detected

**Logs:**
- Python crawler: Standard `logging` module (`crawler/base.py`) — `INFO` level, console output
- Next.js: Default console logging (no structured logging library)
- Client-side: No error tracking service

## CI/CD & Deployment

**Hosting:**
- Vercel (free tier)
  - Config: `web/vercel.json`
  - Build command: `npm run build` (triggers `prebuild` which copies data + warms EPUB cache)
  - Output: `.next` directory
  - Custom headers: gzip Content-Encoding for `.json.gz`, 1-year cache for data/epub-cache assets

**CI Pipeline:**
- None detected — No GitHub Actions, no CI config files

**Data deployment strategy:**
- Crawler data (`crawler/data/`) is committed to git
- `web/public/data` is a symlink to `../../crawler/data`
- Pre-build script copies data into `public/data` for Vercel deployment
- EPUB cache (`web/public/epub-cache/`) is `.gitignore`d, regenerated at build time from `epub/` source files

## Environment Configuration

**Required env vars:**
- `SITE_BASIC_AUTH_USER` — Basic auth username (production only)
- `SITE_BASIC_AUTH_PASSWORD` — Basic auth password (production only)

**Optional / not detected:**
- No database connection strings
- No third-party API keys
- No CDN configuration
- No analytics tracking IDs

**Secrets location:**
- `.env` file (listed in `.gitignore`, never read contents)
- Vercel environment variables (for production auth)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## Internal Service Communication

**Crawler -> Web Data Flow:**
1. Crawler writes JSON to `crawler/data/{site_name}/{story_slug}/`
2. Symlink `web/public/data` -> `../../crawler/data` provides access during development
3. Build-time `npm run data:copy` copies data into `web/public/data/` for Vercel
4. Web app reads data server-side via `fs` in `web/src/lib/data.ts`
5. Client fetches chapter content via API route `/api/chapter/{slug}/{idx}` or static `/epub-cache/` files

**EPUB Pipeline:**
1. EPUB source files stored in `epub/` directory
2. Build-time `npm run epub:cache` runs `web/scripts/warm-epub-cache.ts`
3. Script uses `@smoores/epub` to parse EPUBs, extracts metadata and chapter text
4. Writes cache to `web/public/epub-cache/` (gitignored, regenerated each deploy)
5. Runtime reads cache server-side (`web/src/lib/epub.ts`) and client-side fetches gzipped chapter JSON

---

*Integration audit: 2026-05-19*
