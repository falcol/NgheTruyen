# Coding Conventions

**Analysis Date:** 2026-05-19

## Languages

**Primary:**
- TypeScript (strict mode) — web frontend (`web/src/`), EPUB scripts (`web/scripts/`)
- Python 3 — crawler (`crawler/`)

## Naming Patterns

**Files:**
- TypeScript: `kebab-case` for all files (`chapter-nav.ts`, `epub-cache.ts`, `tts-chunks.ts`)
- React components: `PascalCase.tsx` (`Player.tsx`, `ChapterList.tsx`, `ReaderClient.tsx`)
- Python: `kebab-case.py` for modules (`truyenqq.py`, `metruyenchu.py`)
- CSS: `globals.css` (single file, no CSS modules)

**Functions:**
- `camelCase` for all functions (`buildTTSChunks`, `parseStoredReaderSettings`, `adjacentChapterContentUrls`)
- Private/internal helpers may be unexported at module level
- React hooks: `use` prefix (`useTTS`, `useProgress`, `useReaderSettings`)

**Variables:**
- `camelCase` for locals and consts (`MIN_CHUNK_CHARS`, `MAX_CHUNK_CHARS` are module-level constants in `SCREAMING_SNAKE_CASE`)
- `SCREAMING_SNAKE_CASE` for env key names (`SITE_BASIC_AUTH_USER_ENV_KEY`)
- CSS custom properties: `--kebab-case` (`--color-bg`, `--reader-font-family`)

**Types/Interfaces:**
- `PascalCase` for interfaces and types (`ChapterMeta`, `ReaderTheme`, `TTSChunk`)
- Interface prefix for related types: `Epub` prefix (`EpubBookMeta`, `EpubChapter`, `EpubChapterMeta`)
- No `I` prefix on interfaces

**Components:**
- `PascalCase` named exports (`export default function Player(...)`)
- Sub-components in same file: `PascalCase` function declarations (`function Chip(...)`, `function StoryCard(...)`)

## Code Style

**Formatting:**
- No Prettier config detected — relies on editor defaults
- 2-space indentation (TypeScript/TSX)
- 4-space indentation (Python)
- Single quotes for strings in TypeScript (observed in `vitest.config.ts`, `eslint.config.mjs`)
- Double quotes for strings in TypeScript source files (`import ... from "..."` consistently used)
- Trailing commas in multi-line structures

**Linting:**
- ESLint 9 with flat config: `web/eslint.config.mjs`
- Extends `eslint-config-next/core-web-vitals` and `eslint-config-next/typescript`
- No custom rules beyond Next.js defaults
- TypeScript strict mode enabled (`"strict": true` in `web/tsconfig.json`)

## Import Organization

**Order:**
1. External packages (`import fs from "fs"`, `import Link from "next/link"`)
2. `"use client"` directive at top of client component files
3. Internal modules using `@/` alias (`import { useTTS } from "@/hooks/useTTS"`)
4. Types with `import type` syntax (`import type { Metadata } from "next"`)

**Path Aliases:**
- `@/*` maps to `./src/*` (configured in both `web/tsconfig.json` and `web/vitest.config.ts`)

**Example:**
```typescript
"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import { buildTTSChunks, type TTSChunk } from "@/lib/tts-chunks";
```

## Styling Approach

**CSS Framework:** Tailwind CSS v4 via PostCSS (`@tailwindcss/postcss`)

**CSS Custom Properties:** Extensively used for theming. Defined in `web/src/app/globals.css` under `:root` and dynamically applied via JavaScript (`themeToCssVars()` in `web/src/lib/reader-settings.ts`).

**Pattern:** Utility-first Tailwind classes in JSX + CSS custom properties for theme colors. No CSS modules, no styled-components, no separate component CSS files.

**Theme variables pattern:**
```tsx
className="bg-[var(--color-surface)] text-[var(--color-text-muted)]"
```

**Reader-specific CSS classes:** Semantic utility classes defined in `globals.css` (`.reader-shell`, `.reader-muted`, `.reader-accent`, `.reader-surface`, `.reader-border`, `.reader-paragraph`). These are applied instead of inline color references for readability.

## Error Handling

**Return-null pattern:** Functions that can fail return `null` rather than throwing. Consistent across data layer:
```typescript
function getChapterIndex(slug: string): ChapterMeta[] | null
function getChapter(slug: string, chapterIdx: number): Chapter | null
function readMetaCache(...): EpubMetaCachePayload | null
```

**Try-catch with fallback:** JSON parsing and browser API access wrapped in try-catch, returning safe defaults:
```typescript
try {
  return JSON.parse(saved) as T;
} catch {
  return null;
}
```

**Empty catch blocks:** Used when failures are non-critical and should be silently ignored:
```typescript
} catch {
  // fallback to slug
}
```

**Validation with defaults:** User input parsed with fallback to defaults:
```typescript
export function parseStoredReaderSettings(raw: string | null): StoredReaderSettings {
  if (!raw) return DEFAULT_READER_SETTINGS;
  // ... validate each field, fallback to defaults
}
```

**API route error handling:** HTTP status codes via `Response` constructor:
```typescript
return new Response("Invalid chapter index", { status: 400 });
return new Response("Not found", { status: 404 });
```

**Discriminated union state pattern:** Loading states use tagged unions:
```typescript
type ChapterState =
  | { status: "loading" }
  | { status: "ready"; paragraphs: string[] }
  | { status: "error"; message: string };
```

## Logging

**Web (TypeScript):** No logging framework. Uses `console.log`/`console.warn`/`console.error` in build scripts only (`web/scripts/warm-epub-cache.ts`, `web/src/lib/epub-parse.ts`). No runtime logging in app code.

**Crawler (Python):** Standard `logging` module with basic config:
```python
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)
```

## Comments

**When to Comment:**
- Purpose comments on non-obvious business logic (volume calculation, cache invalidation strategy)
- File-level docstrings on Python modules (`"""Crawler for truyenqq.vn..."""`)
- No JSDoc/TSDoc on TypeScript functions — types serve as documentation

**Pattern in TypeScript:**
```typescript
// Read .json or .json.gz transparently. Prefers .gz when both exist.
function readJsonAny<T>(filePath: string): T | null {
```

**Pattern in Python:**
```python
"""Compress existing .json files in data/ to .json.gz (minified)."""
```

## Function Design

**Size:** Functions generally under 30 lines. Complex functions (like `ReaderClientInner`) may be longer but are rare.

**Parameters:** Named parameters via object destructuring for React components and multi-arg functions:
```tsx
export default function Player({
  playing,
  paused,
  loading,
  ...
}: {
  playing: boolean;
  paused: boolean;
  ...
})
```

**Return Values:**
- Lib functions: explicit return types via TypeScript interfaces
- Hooks: return object with named values `{ playing, paused, ... }`
- Factory pattern: `makeDataDir()` returns an object of functions (closure-based module)

## Module Design

**Exports:** Named exports preferred. Default exports for React components and page routes:
```typescript
export default function HomePage() { ... }
export function buildTTSChunks(...) { ... }
```

**Barrel re-exports:** Used sparingly. `web/src/lib/epub.ts` re-exports from `epub-cache.ts`, `epub-types.ts`:
```typescript
export type { EpubChapter, EpubChapterMeta, EpubBookMeta } from "./epub-types";
export type { EpubListSummary } from "./epub-cache";
export { chapterCacheUrlPath } from "./epub-cache";
```

**Module factory pattern:** `web/src/lib/data.ts` uses `makeDataDir()` returning an interface of functions. A singleton `defaultData` is created and its methods re-exported at module level.

## Git Commit Messages

**Style:** Varied — mix of conventional commits and short messages:
- `feat: add parallel crawl infrastructure to BaseCrawler`
- `fix`
- `EPUB cache and test fixes`
- `fix change page`

**No enforced convention** — commit messages range from single-word (`fix`, `new`) to detailed conventional commit format.

## Environment Variables

**Naming:** `SCREAMING_SNAKE_CASE` with descriptive prefixes:
- `SITE_BASIC_AUTH_USER`
- `SITE_BASIC_AUTH_PASSWORD`

**Access pattern:** Centralized accessor functions in `web/src/lib/site-access.ts`:
```typescript
export const SITE_BASIC_AUTH_USER_ENV_KEY = "SITE_BASIC_AUTH_USER";
export function getSiteBasicAuthCredentials() {
  return {
    username: process.env[SITE_BASIC_AUTH_USER_ENV_KEY]?.trim() ?? "",
    ...
  };
}
```

**No `.env` file committed** — `.env*` is in `.gitignore`.

## Type Definition Patterns

**Co-located types:** Interfaces defined in the same file as the functions that use them (`ChapterMeta` in `web/src/lib/data.ts`).

**Dedicated type files:** Shared types in `web/src/lib/epub-types.ts`.

**Inline type literals:** React props typed inline with object destructuring:
```tsx
function Chip({ active, onClick, children, className = "" }: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
  className?: string;
})
```

**Type narrowing:** Discriminated unions for state machines, `as` casts after validation checks.

## Client/Server Boundary

**Directive:** `"use client"` at top of client component files.

**Pattern:** Server components fetch data and pass to client components:
```tsx
// Server component (page.tsx)
export default async function ReaderPage({ params }) {
  const chapters = getChapterIndex(slug);
  return <ReaderClient chapters={chapters} ... />;
}

// Client component (ReaderClient.tsx)
"use client";
export default function ReaderClient(props) { ... }
```

**Never import server-only modules (fs, path, crypto) from client components.** Build-only code (`epub-parse.ts`) has explicit header comment warning against runtime import.

## Python Crawler Conventions

**Class hierarchy:** `BaseCrawler` (abstract) subclassed per site (`TruyenQQCrawler`, `MetruyenchuCrawler`).

**Type hints:** Used in method signatures (`dest_dir: str | None = None`).

**Data output:** JSON files in `crawler/data/` — either `.json` (pretty-printed, debug) or `.json.gz` (compressed, production).

**CLI:** `argparse` in `crawler/run.py` with `python -m crawler.run <site> <url>` pattern.

---

*Convention analysis: 2026-05-19*
