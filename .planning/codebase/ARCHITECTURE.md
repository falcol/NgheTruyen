<!-- refreshed: 2026-05-19 -->
# Architecture

**Analysis Date:** 2026-05-19

## System Overview

NgheTruyen is a personal Vietnamese story reading and listening app with two data pipelines feeding a single Next.js frontend. Crawled stories are scraped from Vietnamese novel sites and stored as gzipped JSON on disk. EPUB files are extracted at build time into a static cache. The web app serves both sources through a unified reader with text-to-speech.

```text
┌─────────────────────────────────────────────────────────────────────┐
│                        External Sources                             │
├──────────────────────┬──────────────────────────────────────────────┤
│  Vietnamese Novel    │           EPUB Files                         │
│  Websites            │           (placed in epub/)                  │
│  (truyenqq, etc.)    │                                             │
└──────────┬───────────┴──────────────────┬───────────────────────────┘
           │ (Python crawler)             │ (Node.js build script)
           ▼                              ▼
┌──────────────────────┐   ┌──────────────────────────────────────────┐
│  crawler/data/       │   │  web/public/epub-cache/                  │
│  {site}/{story}/     │   │  {hash}/ch/{idx}.json.gz                 │
│  vol-NNN.json.gz     │   │  index.json                              │
│  chapters_index.json │   │  {hash}.json (meta)                      │
│  metadata.json       │   │                                          │
└──────────┬───────────┘   └──────────────────┬───────────────────────┘
           │ (symlink: public/data)           │ (static files)
           ▼                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Next.js Web App (web/)                            │
│                                                                     │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐│
│  │ Server       │  │ API Route    │  │ Client Components          ││
│  │ Components   │  │ /api/chapter │  │ ReaderClient, Player,      ││
│  │ (pages)      │  │              │  │ ChapterList                ││
│  └──────┬───────┘  └──────┬───────┘  └────────────┬───────────────┘│
│         │                  │                        │                │
│         ▼                  ▼                        ▼                │
│  ┌─────────────────────────────────────────────────────────────────┐│
│  │                     Data Layer (lib/)                           ││
│  │  data.ts          epub.ts / epub-cache.ts                      ││
│  │  (read JSON.gz)   (read pre-extracted cache)                   ││
│  └─────────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| Crawler (Python) | Scrape chapters from novel sites, save as gzipped JSON volumes | `crawler/run.py`, `crawler/base.py` |
| Crawler Compress | Batch-compress raw JSON to .json.gz | `crawler/compress.py` |
| Crawler Delete | Interactive story deletion from local data | `crawler/delete.py` |
| EPUB Cache Warmer | Extract EPUB chapters into static cache at build time | `web/scripts/warm-epub-cache.ts`, `web/src/lib/epub-parse.ts` |
| Data Layer | Read story data from filesystem (JSON or JSON.gz transparently) | `web/src/lib/data.ts` |
| EPUB Runtime | Read pre-extracted EPUB cache for server rendering | `web/src/lib/epub.ts`, `web/src/lib/epub-cache.ts` |
| API Route | Serve individual crawled chapters as JSON | `web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts` |
| ReaderClient | Unified client-side reader for both data sources | `web/src/components/ReaderClient.tsx` |
| Player | TTS controls bar (play/pause/rate/voice/theme/font) | `web/src/components/Player.tsx` |
| ChapterList | Chapter index with progress indicator and prefetching | `web/src/components/ChapterList.tsx` |
| useTTS | SpeechSynthesis orchestration with chunking and skip | `web/src/hooks/useTTS.ts` |
| useProgress | Reading progress persistence in localStorage | `web/src/hooks/useProgress.ts` |
| useReaderSettings | Theme/font/size preferences in localStorage | `web/src/hooks/useReaderSettings.ts` |
| Site Access | HTTP Basic Auth middleware for production | `web/src/proxy.ts`, `web/src/lib/site-access.ts` |

## Pattern Overview

**Overall:** Static-site generator with client-side interactivity. Next.js App Router with server components for data fetching and `"use client"` components for interactive UI.

**Key Characteristics:**
- **Zero-database architecture**: All data is files on disk (JSON/JSON.gz). Crawled data symlinked from `crawler/data/` into `web/public/data/`. EPUB data pre-extracted into `web/public/epub-cache/`.
- **Dual content pipeline**: Crawler data served via API route; EPUB data served as static gzipped JSON files. ReaderClient abstracts the difference via `chapterContentUrl`.
- **Client-side TTS**: Uses browser `SpeechSynthesis` API with Vietnamese voices. Paragraphs are chunked into speech-friendly segments (60-250 chars).
- **LocalStorage persistence**: Reading progress, TTS voice preference, and reader settings (theme/font/size) stored client-side.
- **Build-time data preparation**: `prebuild` script copies crawler data and warms EPUB cache. Vercel deployment runs this automatically.

## Layers

**Server Layer (Next.js Server Components):**
- Purpose: Render pages with metadata, provide API routes
- Location: `web/src/app/*/page.tsx`
- Contains: Async page components that read filesystem data
- Depends on: `@/lib/data.ts`, `@/lib/epub.ts`
- Used by: Next.js router

**API Layer (Next.js Route Handlers):**
- Purpose: Serve individual chapter JSON for crawler-fed stories
- Location: `web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts`
- Contains: GET handler that reads from filesystem
- Depends on: `@/lib/data.ts`
- Used by: Client-side chapter prefetching

**Client Component Layer:**
- Purpose: Interactive UI (TTS playback, navigation, settings, scroll tracking)
- Location: `web/src/components/*.tsx`
- Contains: React components marked `"use client"`
- Depends on: `@/hooks/*`, `@/context/*`, `@/lib/*`
- Used by: Server component pages

**Data Access Layer:**
- Purpose: Abstract filesystem reads (transparent .json / .json.gz handling)
- Location: `web/src/lib/data.ts`, `web/src/lib/epub.ts`, `web/src/lib/epub-cache.ts`
- Contains: Pure functions that read and parse data files
- Depends on: Node.js `fs`, `zlib`
- Used by: Server components, API routes

**Crawler Pipeline (Python):**
- Purpose: Scrape Vietnamese novel sites, store structured chapter data
- Location: `crawler/`
- Contains: Base crawler class with site-specific implementations
- Depends on: `requests`, `beautifulsoup4`, `lxml`
- Used by: CLI (`python -m crawler.run`)

## Data Flow

### Crawler Story Reading

1. User visits `/story/{slug}` (`web/src/app/story/[slug]/page.tsx`)
2. Server calls `listStories()` -> `getChapterIndex(slug)` from `web/src/lib/data.ts`
3. `data.ts` reads `public/data/{site}/{slug}/chapters_index.json[.gz]`
4. Server renders `ChapterList` with chapter metadata

### Crawler Chapter Reading (async mode)

1. User visits `/read/{slug}/{chapterIdx}` (`web/src/app/read/[slug]/[chapterIdx]/page.tsx`)
2. Server renders `ReaderClient` with `chapterContentUrl=/api/chapter/{slug}/{chapterIdx}`
3. Client fetches chapter JSON from API route (`web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts`)
4. API route reads volume file from disk, returns chapter JSON
5. Client prefetches prev/next chapters via `chapter-prefetch.ts` (in-memory LRU cache, max 12)
6. TTS hook chunks paragraphs and plays via SpeechSynthesis

### EPUB Chapter Reading (static mode)

1. User visits `/epub/{filename}/read/{chapterIdx}` (`web/src/app/epub/[filename]/read/[chapterIdx]/page.tsx`)
2. Server reads EPUB meta cache from `public/epub-cache/{hash}.json`
3. Server renders `ReaderClient` with `chapterContentUrl=/epub-cache/{hash}/ch/{idx}.json.gz`
4. Client fetches gzipped chapter directly from static files (no API route)
5. Client decompresses gzip via `DecompressionStream`, parses JSON
6. Same TTS and prefetch pipeline as crawler stories

### EPUB Cache Warm-up (build time)

1. `npm run epub:cache` runs `web/scripts/warm-epub-cache.ts`
2. Script calls `warmAllEpubCaches()` from `web/src/lib/epub-parse.ts`
3. For each `.epub` in `epub/` directory:
   - Opens EPUB with `@smoores/epub`
   - Extracts metadata (title, chapter list from TOC/NCX)
   - Writes meta cache to `public/epub-cache/{hash}.json`
   - Extracts each chapter's paragraphs, writes to `public/epub-cache/{hash}/ch/{idx}.json.gz`
   - Writes `public/epub-cache/index.json` with book summaries

**State Management:**
- No global state manager (Redux, Zustand, etc.)
- React Context used only for reader settings (`ReaderSettingsContext`)
- localStorage for persistence: reading progress, TTS voice, reader settings
- In-memory cache for chapter prefetching (Map with LRU eviction, max 12 entries)

## Key Abstractions

**Dual Content Mode in ReaderClient:**
- Purpose: Single reader component handles both crawler data and EPUB data
- Implementation: Discriminated union props in `web/src/components/ReaderClient.tsx`:
  ```typescript
  type ReaderClientProps = {
    slug: string;
    // ...
  } & (
    | { paragraphs: string[]; chapterContentUrl?: never }  // sync mode
    | { chapterContentUrl: string; paragraphs?: never }    // async mode
  );
  ```
- EPUB uses async mode (static .json.gz files), crawler uses async mode (API route)

**Multi-Source Data Aggregation:**
- Purpose: Aggregate stories from multiple crawl sites
- Implementation: `makeAllSources()` in `web/src/lib/data.ts` scans all subdirectories under `public/data/`, creates a `makeDataDir` instance per source, and delegates lookups to the first matching source

**Volume-based Chapter Storage:**
- Purpose: Keep individual file sizes manageable for stories with thousands of chapters
- Implementation: Chapters grouped into volumes of 50. Files named `vol-NNN-{hash}.json.gz`. Lookup searches the expected volume plus 2 neighbors for robustness.

## Entry Points

**Web App:**
- Location: `web/src/app/page.tsx` (home page listing all stories)
- Triggers: Browser navigation
- Responsibilities: Lists crawled stories and EPUB link

**EPUB List:**
- Location: `web/src/app/epub/page.tsx`
- Triggers: Navigation to `/epub`
- Responsibilities: Lists all EPUB books from cache index

**Crawler CLI:**
- Location: `crawler/run.py`
- Triggers: `python -m crawler.run <site> <url>`
- Responsibilities: Scrape chapters, save to `crawler/data/{site}/{story}/`

**EPUB Cache CLI:**
- Location: `web/scripts/warm-epub-cache.ts`
- Triggers: `npm run epub:cache` or `npm run prebuild`
- Responsibilities: Extract all EPUB files into static cache

**Data Compress CLI:**
- Location: `crawler/compress.py`
- Triggers: `python -m crawler.compress --apply`
- Responsibilities: Compress raw JSON to .json.gz

## Architectural Constraints

- **No database**: All data is file-based. Storage is gzipped JSON on disk, read at request time. This constrains query flexibility but eliminates infrastructure.
- **Vercel free tier deployment**: Filesystem is ephemeral on Vercel. Build-time data preparation (`prebuild`) copies crawler data and warms EPUB cache into `public/` so it gets deployed as static assets. Crawler data must be committed to git or copied before deploy.
- **Single API route**: Only one API route exists (`/api/chapter/[slug]/[chapterIdx]`). EPUB chapters bypass the API entirely, served as static gzipped JSON. New data sources should follow the EPUB pattern (static files) rather than adding API routes.
- **Client-only TTS**: SpeechSynthesis is browser-only. No server-side audio generation. The `msedge-tts` dependency in `web/package.json` is present but not used in the current architecture.
- **No middleware file**: The proxy/auth logic in `web/src/proxy.ts` is exported but has no corresponding `middleware.ts` at the expected Next.js location. Auth may not be active currently.

## Anti-Patterns

### Proxy Not Wired

**What happens:** `web/src/proxy.ts` exports a `proxy` function with a matcher config, but no `middleware.ts` file exists in `web/` or `web/src/`.
**Why it's wrong:** The Basic Auth protection for production is defined but not connected. The site may be accessible without authentication.
**Do this instead:** Create `web/src/middleware.ts` that re-exports the proxy function, or remove the dead code.

### Crawler Data Symlink

**What happens:** `web/public/data` is a symlink to `../../crawler/data`. The `prebuild` script copies data via `cp -r ../crawler/data public/data`.
**Why it's wrong:** The symlink works locally but the copy script overwrites it during build. The symlink may confuse tooling.
**Do this instead:** The build script already handles this correctly by removing and copying. Keep the symlink for local dev only.

## Error Handling

**Strategy:** Graceful degradation with user-facing retry.

**Patterns:**
- Chapter fetch failures show error message with "Thu lai" (retry) button (`web/src/components/ReaderClient.tsx`)
- Missing EPUB cache shows `EpubCacheMissing` component with instructions to run `npm run epub:cache` (`web/src/components/EpubCacheMissing.tsx`)
- Story listing shows "Chua co truyen nao" when no data exists (`web/src/app/page.tsx`)
- Invalid chapter indices return 404 via `notFound()` from `next/navigation`
- TTS errors (canceled utterances) are silently skipped, advancing to next chunk (`web/src/hooks/useTTS.ts`)

## Cross-Cutting Concerns

**Logging:** No structured logging in the web app. Crawler uses Python `logging` module with INFO level.

**Validation:** File existence checks before reads. Type assertions on parsed JSON. No runtime schema validation (Zod, etc.).

**Authentication:** HTTP Basic Auth defined in `web/src/proxy.ts` via env vars `SITE_BASIC_AUTH_USER` and `SITE_BASIC_AUTH_PASSWORD`. Skipped in development (`NODE_ENV !== "production"`). Not currently wired to middleware.

---

*Architecture analysis: 2026-05-19*
