# Technology Stack

**Analysis Date:** 2026-05-19

## Project Overview

NgheTruyen is a personal Vietnamese story reader app with text-to-speech. It has two subsystems: a **Python crawler** that scrapes Vietnamese story sites into JSON, and a **Next.js web app** that serves the stories for reading and listening. Data is committed to the repo as gzipped JSON and deployed to Vercel free tier.

The project is NOT a monorepo workspace — it is a multi-directory repo with separate `crawler/` (Python) and `web/` (Node.js) subprojects that share data via the filesystem (`crawler/data/` symlinked to `web/public/data/`).

## Languages

**Primary:**
- TypeScript 5.x — Web frontend and API routes (`web/src/`)
- Python 3.14 — Crawler scripts (`crawler/`)

**Secondary:**
- CSS (Tailwind v4) — Styling (`web/src/app/globals.css`)

## Runtime

**Environment:**
- Node.js v24.14.1 (development)
- Python 3.14.4 (crawler scripts)

**Package Manager:**
- npm 11.11.0 (web app)
- pip (crawler — no lockfile, `crawler/requirements.txt`)
- Lockfile: `web/package-lock.json` present

## Frameworks

**Core:**
- Next.js 16.2.6 — App Router, React Server Components, API routes, Turbopack
- React 19.2.4 — UI library (latest, RSC-compatible)
- Tailwind CSS v4 — Utility-first CSS via `@tailwindcss/postcss` plugin

**Testing:**
- Vitest 4.1.4 — Unit test runner
- jsdom 29.0.2 — DOM environment for component tests
- @vitejs/plugin-react 6.0.1 — React support in Vitest

**Build/Dev:**
- Turbopack — Dev bundler (configured in `web/next.config.ts`)
- ESLint 9 + eslint-config-next 16.2.3 — Linting with core-web-vitals + TypeScript rules
- PostCSS — CSS processing via `@tailwindcss/postcss`

## Key Dependencies

**Critical:**
- `@smoores/epub` ^0.1.9 — EPUB parsing library (build-time only, used in `web/src/lib/epub-parse.ts` and `web/scripts/warm-epub-cache.ts`)
- `msedge-tts` ^2.0.4 — Listed in dependencies but NOT used in source code (declared but unused)
- `next` ^16.2.6 — Core framework

**Infrastructure:**
- `react` 19.2.4 / `react-dom` 19.2.4 — UI runtime
- `typescript` ^5 — Type checking
- `tailwindcss` ^4 — Styling
- `zlib` (Node built-in) — Gzip decompression for `.json.gz` data files
- `crypto` (Node built-in) — SHA-256 hashing for EPUB cache keys
- `fs` / `path` (Node built-in) — Filesystem access for data and EPUB cache

**Python (Crawler):**
- `requests` >=2.31.0 — HTTP client for web scraping
- `beautifulsoup4` >=4.12.0 — HTML parsing
- `lxml` >=5.0.0 — Fast XML/HTML parser (fallback to stdlib `html.parser`)

## Data Storage

**Primary:** Static JSON files on filesystem
- Crawler output: `crawler/data/{site}/{story-slug}/` containing `metadata.json[.gz]`, `chapters_index.json[.gz]`, `vol-NNN-*.json[.gz]`
- EPUB cache: `web/public/epub-cache/{hash}.json` for book meta, `web/public/epub-cache/{hash}/ch/{idx}.json.gz` for chapters
- Data symlink: `web/public/data` -> `../../crawler/data`

**Client-side:** localStorage
- Reading progress: `progress-{slug}` key (`web/src/hooks/useProgress.ts`)
- Reader settings: `reader-settings-v1` key (`web/src/hooks/useReaderSettings.ts`)
- TTS voice preference: `nghetruyen-tts-voice` key (`web/src/hooks/useTTS.ts`)

**No database** — All data is file-based static JSON, committed to git, deployed as static assets.

## Configuration

**Environment:**
- `SITE_BASIC_AUTH_USER` — Basic auth username for production (`web/src/lib/site-access.ts`)
- `SITE_BASIC_AUTH_PASSWORD` — Basic auth password for production (`web/src/lib/site-access.ts`)
- `.env` file present — Listed in `.gitignore`
- No other env vars detected

**Build:**
- `web/next.config.ts` — Turbopack root config
- `web/tsconfig.json` — TypeScript strict mode, `@/*` path alias, ES2017 target
- `web/postcss.config.mjs` — Tailwind CSS plugin
- `web/eslint.config.mjs` — ESLint with core-web-vitals + TypeScript
- `web/vitest.config.ts` — jsdom environment, `@/` path alias
- `web/vercel.json` — Build command, output directory, cache headers for `.json.gz`

**Pre-build pipeline** (`web/package.json` `"prebuild"` script):
1. `npm run data:copy` — Copies `../crawler/data` into `public/data`
2. `npm run epub:cache` — Runs `scripts/warm-epub-cache.ts` to extract EPUB metadata/chapters

## Platform Requirements

**Development:**
- Node.js 24+ (for Next.js 16)
- Python 3.12+ (for crawler, uses `str | None` type syntax)
- npm 11+

**Production:**
- Vercel free tier deployment
- Static JSON data committed to repo (gzipped to reduce size)
- Basic Auth middleware for production access control (`web/src/proxy.ts`)
- Cache-Control: 1 year immutable for data assets (`web/vercel.json`)

## Text-to-Speech

**Implementation:** Browser-native Web Speech API
- `SpeechSynthesisUtterance` with `lang: "vi-VN"` (`web/src/hooks/useTTS.ts`)
- Filters for Vietnamese voices (`vi-VN` lang)
- Preference order: saved voice > Google > Microsoft > first available
- Chunk-based playback: paragraphs split into 60-250 char chunks (`web/src/lib/tts-chunks.ts`)
- Adjustable rate (0.75x - 2x) and voice selection

**Note:** `msedge-tts` npm package is declared in dependencies but never imported in source code. The actual TTS uses the browser's built-in `speechSynthesis` API.

## Fonts

Google Fonts loaded via `next/font/google` (`web/src/app/layout.tsx`):
- Be Vietnam Pro (UI font, Vietnamese support)
- Literata, Lora, Merriweather, Noto Serif, Source Serif 4 (reader fonts)

---

*Stack analysis: 2026-05-19*
