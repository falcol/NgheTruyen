# Codebase Structure

**Analysis Date:** 2026-05-19

## Directory Layout

```
NgheTruyen/
├── crawler/              # Python scraping pipeline
│   ├── data/             # Scraped story data (JSON/JSON.gz)
│   │   ├── metruyenchu/  # Stories from metruyenchu.com.vn
│   │   └── truyenfullmoi/# Stories from truyenfullmoi.com
│   ├── base.py           # BaseCrawler abstract class
│   ├── run.py            # CLI entry point
│   ├── compress.py       # Batch compress JSON to JSON.gz
│   ├── delete.py         # Interactive story deletion
│   ├── truyenqq.py       # TruyenQQ site crawler
│   ├── metruyenchu.py    # MeTruyenChu site crawler
│   ├── metruyencv.py     # MeTruyenCV site crawler
│   ├── truyenfullmoi.py  # TruyenFullMoi site crawler
│   └── requirements.txt  # Python dependencies
├── epub/                 # EPUB source files (committed to repo)
├── web/                  # Next.js frontend app
│   ├── public/
│   │   ├── data -> ../../crawler/data  # Symlink (local dev)
│   │   └── epub-cache/  # Pre-extracted EPUB cache (generated)
│   ├── src/
│   │   ├── app/          # Next.js App Router pages
│   │   ├── components/   # React components
│   │   ├── context/      # React contexts
│   │   ├── hooks/        # Custom React hooks
│   │   ├── lib/          # Data access and utilities
│   │   └── proxy.ts      # Auth proxy (not wired to middleware)
│   ├── scripts/          # Build scripts
│   ├── __tests__/        # Test files
│   └── package.json
├── docs/                 # Documentation and specs
├── _bmad/                # BMAD methodology tools (agent skills)
├── _bmad-output/         # BMAD generated artifacts
├── openspec/             # OpenSpec artifacts
├── .agent/               # Agent skill definitions
├── .agents/              # Agent configurations
├── .claude/              # Claude Code skills and commands
├── .cursor/              # Cursor IDE skills and commands
└── .planning/            # Planning documents (this file)
```

## Directory Purposes

**`crawler/`:**
- Purpose: Python-based web scraping pipeline for Vietnamese novel sites
- Contains: Site-specific crawler classes, CLI tools, scraped data
- Key files: `base.py` (base class), `run.py` (CLI), `compress.py` (batch compression)

**`epub/`:**
- Purpose: Source EPUB files placed here by the user
- Contains: `.epub` files that get extracted at build time
- Key files: EPUB files directly in this directory

**`web/`:**
- Purpose: Next.js web application (the main user-facing app)
- Contains: All frontend code, configuration, and build scripts
- Key files: `package.json`, `next.config.ts`, `tsconfig.json`

**`web/src/app/`:**
- Purpose: Next.js App Router pages and API routes
- Contains: Page components organized by URL path
- Key files: `page.tsx` (home), `layout.tsx` (root layout)

**`web/src/components/`:**
- Purpose: Reusable React components (all are `"use client"`)
- Contains: UI components shared across pages
- Key files: `ReaderClient.tsx` (unified reader), `Player.tsx` (TTS controls), `ChapterList.tsx`

**`web/src/hooks/`:**
- Purpose: Custom React hooks for stateful logic
- Contains: TTS, progress tracking, reader settings hooks
- Key files: `useTTS.ts`, `useProgress.ts`, `useReaderSettings.ts`

**`web/src/lib/`:**
- Purpose: Pure functions and data access layer (no React, no state)
- Contains: Filesystem readers, URL builders, type definitions
- Key files: `data.ts` (crawler data), `epub.ts`/`epub-cache.ts` (EPUB cache), `chapter-prefetch.ts` (client-side cache)

**`web/src/context/`:**
- Purpose: React Context providers
- Contains: Single context for reader settings
- Key files: `ReaderSettingsContext.tsx`

**`web/src/app/api/`:**
- Purpose: Next.js API route handlers
- Contains: Single route for serving crawler chapter data
- Key files: `chapter/[slug]/[chapterIdx]/route.ts`

**`web/scripts/`:**
- Purpose: Build-time scripts
- Contains: EPUB cache warmer
- Key files: `warm-epub-cache.ts`

**`web/__tests__/`:**
- Purpose: Unit tests
- Contains: Test files co-located in a single directory
- Key files: `data.test.ts`, `tts-chunks.test.ts`, `epub-cache.test.ts`

**`web/public/`:**
- Purpose: Static assets served by Next.js
- Contains: Symlink to crawler data, generated EPUB cache
- Key files: `epub-cache/index.json` (EPUB book list), `data/` (symlink)

**`crawler/data/`:**
- Purpose: Scraped story data organized by source site
- Contains: Subdirectories per site, each containing story folders with volume JSON files
- Key files: `{site}/{story}/chapters_index.json.gz`, `{site}/{story}/metadata.json.gz`, `{site}/{story}/vol-NNN-*.json.gz`

## Key File Locations

**Entry Points:**
- `web/src/app/page.tsx`: Home page (story list + EPUB link)
- `web/src/app/layout.tsx`: Root layout (fonts, metadata, viewport)
- `crawler/run.py`: Crawler CLI entry point

**Configuration:**
- `web/package.json`: Dependencies, scripts (dev/build/test/data:copy/epub:cache/prebuild)
- `web/tsconfig.json`: TypeScript config (strict mode, `@/*` path alias)
- `web/next.config.ts`: Next.js config (turbopack enabled)
- `web/vitest.config.ts`: Vitest config (jsdom environment, `@/*` alias)
- `web/postcss.config.mjs`: PostCSS with Tailwind CSS v4
- `crawler/requirements.txt`: Python dependencies (requests, beautifulsoup4)

**Core Logic:**
- `web/src/lib/data.ts`: Multi-source story data reader (read JSON.gz transparently)
- `web/src/lib/epub-cache.ts`: EPUB cache read/write (build + runtime)
- `web/src/lib/epub-parse.ts`: EPUB parsing (build-time only)
- `web/src/lib/epub.ts`: EPUB runtime data access (reads pre-extracted cache)
- `web/src/lib/chapter-prefetch.ts`: Client-side chapter cache with LRU eviction
- `web/src/lib/tts-chunks.ts`: Paragraph-to-speech-chunk splitter
- `web/src/hooks/useTTS.ts`: SpeechSynthesis orchestration
- `crawler/base.py`: BaseCrawler abstract class with adaptive throttling

**Testing:**
- `web/__tests__/data.test.ts`: Tests for data access layer
- `web/__tests__/tts-chunks.test.ts`: Tests for TTS chunking
- `web/__tests__/epub-cache.test.ts`: Tests for EPUB cache
- `web/__tests__/reader-settings.test.ts`: Tests for reader settings
- `web/__tests__/site-access.test.ts`: Tests for Basic Auth
- `web/__tests__/chapter-nav.test.ts`: Tests for chapter navigation URLs
- `web/__tests__/useProgress.test.ts`: Tests for progress persistence

## Naming Conventions

**Files:**
- React components: PascalCase `ReaderClient.tsx`, `Player.tsx`, `ChapterList.tsx`
- Hooks: camelCase with `use` prefix `useTTS.ts`, `useProgress.ts`, `useReaderSettings.ts`
- Lib modules: kebab-case `chapter-prefetch.ts`, `epub-cache.ts`, `tts-chunks.ts`
- Test files: Match source file name `data.test.ts`, `epub-cache.test.ts`
- Page files: Always `page.tsx` inside route directory
- Layout files: Always `layout.tsx` at route level
- API routes: Always `route.ts` inside API route directory

**Directories:**
- App routes: kebab-case matching URL segments `story/[slug]/`, `read/[slug]/[chapterIdx]/`
- Dynamic segments: `[slug]`, `[chapterIdx]`, `[filename]` (Next.js convention)
- Data directories: Match crawler site name `metruyenchu/`, `truyenqq/`

## Where to Add New Code

**New Crawler Site:**
- Create `crawler/{sitename}.py` extending `BaseCrawler`
- Implement `_extract_chapter()` and `_next_url()` methods
- Register in `CRAWLERS` dict in `crawler/run.py`
- Example: `crawler/truyenqq.py` as reference

**New Page/Route:**
- Create directory under `web/src/app/` following URL structure
- Add `page.tsx` (server component by default)
- Use `"use client"` directive only when interactivity is needed
- Example: `web/src/app/epub/[filename]/page.tsx`

**New API Route:**
- Create directory under `web/src/app/api/`
- Add `route.ts` with exported `GET`/`POST` functions
- Example: `web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts`
- Note: Prefer static file approach (like EPUB) over API routes for new data sources

**New Client Component:**
- Create in `web/src/components/` with PascalCase filename
- Add `"use client"` directive at top
- Import hooks from `@/hooks/`, utilities from `@/lib/`
- Example: `web/src/components/ChapterList.tsx`

**New Hook:**
- Create in `web/src/hooks/` with `use` prefix
- Can access browser APIs (window, localStorage)
- Export as named export
- Example: `web/src/hooks/useProgress.ts`

**New Library/Utility:**
- Create in `web/src/lib/` with kebab-case filename
- Pure functions only, no React imports, no side effects
- Server-safe (check `typeof window` before browser APIs)
- Example: `web/src/lib/tts-chunks.ts`

**New Test:**
- Create in `web/__tests__/` matching source filename
- Uses Vitest with jsdom environment
- Example: `web/__tests__/data.test.ts`

**New EPUB File:**
- Place `.epub` file in `epub/` directory
- Run `npm run epub:cache` to extract
- Deploy to pick up new cache files

## Routing Structure

```
/                           -> Home page (story list + EPUB link)
/story/[slug]               -> Story chapter list
/read/[slug]/[chapterIdx]   -> Crawler story reader
/epub                       -> EPUB book list
/epub/[filename]            -> EPUB chapter list
/epub/[filename]/read/[chapterIdx] -> EPUB reader
/api/chapter/[slug]/[chapterIdx]   -> Chapter JSON API (crawler data only)
```

## Special Directories

**`web/public/epub-cache/`:**
- Purpose: Pre-extracted EPUB metadata and chapter content
- Generated: Yes (by `npm run epub:cache`)
- Committed: Yes (deployed as static assets via Vercel)
- Structure: `{sha256-hash}.json` (book meta), `{sha256-hash}/ch/{00000}.json.gz` (chapter), `index.json` (book list)

**`web/public/data`:**
- Purpose: Symlink to crawler data for local development
- Generated: No (manual symlink)
- Committed: Symlink is committed; actual data in `crawler/data/`
- Build: `prebuild` script replaces symlink with actual copy for deployment

**`epub/`:**
- Purpose: Source EPUB files
- Generated: No (user places files manually)
- Committed: Yes (EPUB files are committed to repo)

**`web/node_modules/`:**
- Purpose: NPM dependencies
- Generated: Yes (`npm install`)
- Committed: No

**`.venv/`:**
- Purpose: Python virtual environment for crawler
- Generated: Yes (`python -m venv`)
- Committed: No

**`web/.next/`:**
- Purpose: Next.js build output
- Generated: Yes (`next build`)
- Committed: No

**`_bmad/`, `_bmad-output/`, `openspec/`, `.agent/`, `.agents/`, `.claude/`, `.cursor/`:**
- Purpose: AI agent tooling and methodology frameworks (BMAD, OpenSpec)
- These are development tooling, not part of the application itself
- Committed: Yes

---

*Structure analysis: 2026-05-19*
