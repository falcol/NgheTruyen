# Codebase Concerns

**Analysis Date:** 2026-05-19

---

## HIGH Severity

### Missing Middleware — Site Basic Auth Not Wired

- **Issue:** `web/src/proxy.ts` exports a `proxy()` function and a `config` matcher object intended to be used as Next.js middleware, but no `web/src/middleware.ts` file exists. The basic auth protection described in `web/src/lib/site-access.ts` and `web/src/proxy.ts` is never executed. On Vercel in production, the site is completely open — no auth challenge is presented to visitors.
- **Files:** `web/src/proxy.ts` (lines 20-48), `web/src/lib/site-access.ts`
- **Impact:** Any visitor can access all stories and chapters without authentication. The entire auth layer is dead code.
- **Fix approach:** Create `web/src/middleware.ts` that re-exports `proxy` and `config` from `web/src/proxy.ts`:
  ```typescript
  export { proxy as default, config } from "@/proxy";
  ```
  Alternatively, move the `config` export and middleware function into `web/src/middleware.ts` directly following Next.js conventions.

### Synchronous Filesystem Reads in API Route (Blocking Event Loop)

- **Issue:** `web/src/lib/data.ts` uses `fs.existsSync()`, `fs.readdirSync()`, `fs.readFileSync()`, and `fs.statSync()` extensively throughout the data layer. These are called on every API request in `web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts` (which is `force-dynamic`). On Vercel serverless, a single cold-start request blocks while scanning directories, reading gzipped JSON, and decompressing.
- **Files:** `web/src/lib/data.ts` (lines 6-17, 46-57, 89-117), `web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts`
- **Impact:** Request latency spikes under load; serverless function CPU is wasted on blocking I/O. The `getChapter()` function (line 77-117) calls `readdirSync` on every request, then opens and parses potentially large JSON volume files.
- **Fix approach:** Convert to async `fs.promises` equivalents (`fs.promises.readdir`, `fs.promises.readFile`, etc.) and cache story metadata at module load or use `await` in the route handler. Consider adding an in-memory LRU cache for frequently accessed chapters.

### Large Binary Assets Committed to Git Repository

- **Issue:** The `epub/` directory contains two EPUB files totaling 27MB (`Hoa Cao Thu Tai Do Thi` at 16.2MB, `Trung Sinh Chi Than Cap Bai Gia Tu` at 7.2MB). The `crawler/data/` directory is 108MB and is copied to `web/public/data/` during build. The `.git` directory is 174MB, suggesting these large files have been tracked historically.
- **Files:** `epub/*.epub`, `crawler/data/` (108MB)
- **Impact:** Slow clones, large repository size, wasted CI/CD bandwidth. Vercel free tier has build time limits — copying 108MB of data during `prebuild` adds significant overhead.
- **Fix approach:** Add `epub/*.epub` and `crawler/data/` to `.gitignore`. Store EPUB source files externally (e.g., S3, R2) or use Git LFS. For crawler data, consider generating during CI rather than committing. The `web/public/data/` copy step in `prebuild` could fetch from a CDN instead.

### Basic Auth Uses Non-Constant-Time String Comparison

- **Issue:** `web/src/lib/site-access.ts` line 52-55 compares username and password using `===` (strict equality), which is vulnerable to timing attacks. An attacker can measure response times to progressively guess credentials character-by-character.
- **Files:** `web/src/lib/site-access.ts` (lines 44-57)
- **Impact:** Credential enumeration risk. While mitigated by the small credential space, this is a security anti-pattern.
- **Fix approach:** Use `crypto.timingSafeEqual()` from Node.js `crypto` module:
  ```typescript
  import { timingSafeEqual } from "crypto";
  const a = Buffer.from(credentials.username);
  const b = Buffer.from(expectedCredentials.username);
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
  ```

---

## MEDIUM Severity

### `msedge-tts` Dependency Unused in Runtime Code

- **Issue:** `msedge-tts@^2.0.4` is listed as a production dependency in `web/package.json` but is never imported anywhere in the codebase. The TTS functionality uses the browser-native `SpeechSynthesis` API exclusively (see `web/src/hooks/useTTS.ts`).
- **Files:** `web/package.json` (line 18)
- **Impact:** Unnecessary bundle size increase and dependency surface. `msedge-tts` may pull in native modules or large assets that bloat the Vercel deployment.
- **Fix approach:** Remove `msedge-tts` from `dependencies` in `web/package.json`. If it was intended for server-side TTS, that feature was never implemented — the current approach is browser-only.

### `ReaderClient.tsx` is a God Component (387 lines)

- **Issue:** `web/src/components/ReaderClient.tsx` handles chapter loading, scroll restoration, prefetching, keyboard navigation, chapter picker UI, TTS coordination, and error state rendering — all in a single component. `ReaderClientInner` has 15 `useEffect` hooks.
- **Files:** `web/src/components/ReaderClient.tsx`
- **Impact:** Difficult to test in isolation. Any change to one concern (e.g., scroll behavior) risks regressions in another (e.g., TTS). The dense effect hooks create implicit ordering dependencies.
- **Fix approach:** Extract into focused hooks: `useChapterLoader` (content fetch + cache), `useScrollRestore` (scroll save/restore), `useKeyboardNav` (arrow key navigation), `useChapterPicker` (filter + picker UI state). The component would compose these hooks instead of managing all state inline.

### `useTTS` Hook Manages Complex Mutable Refs (311 lines)

- **Issue:** `web/src/hooks/useTTS.ts` uses 9 `useRef` values to coordinate state between closure callbacks. The `playIdRef` / `stoppedRef` pattern is a manual cancellation token that requires every callback to check both refs. The `playChunkAtRef` pattern (storing a function in a ref and updating it via a separate `useEffect`) is fragile.
- **Files:** `web/src/hooks/useTTS.ts` (lines 55-66, 86-141, 139-141)
- **Impact:** Race condition risk if refs are not checked in the correct order. The `playChunkAt` function is defined with `useCallback` then immediately mirrored into a ref — if the ref update is batched differently, stale closures could speak the wrong chunk.
- **Fix approach:** Consider using `useReducer` with a state machine approach (states: idle, loading, playing, paused) instead of multiple independent boolean states + refs. Alternatively, use a class-based TTS controller instantiated via `useRef` that encapsulates all playback logic.

### No Path Traversal Protection in API Route

- **Issue:** `web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts` passes the `slug` parameter directly to `getChapter()` which constructs filesystem paths via `path.join(dataDir, slug, ...)`. A malicious slug like `../../etc/passwd` could potentially read files outside the data directory.
- **Files:** `web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts` (line 15), `web/src/lib/data.ts` (lines 61-64, 87-88)
- **Impact:** Potential arbitrary file read on the server. On Vercel, the attack surface is limited (read-only filesystem), but in any self-hosted deployment this is exploitable.
- **Fix approach:** Validate that the resolved path is within `dataDir`:
  ```typescript
  const resolved = path.resolve(dataDir, slug);
  if (!resolved.startsWith(dataDir)) return null;
  ```
  Apply this check in `makeDataDir` for slug-based path construction.

### EPUB Cache Under `public/` Served Statically Without Auth

- **Issue:** EPUB chapter caches are written to `web/public/epub-cache/` as gzipped JSON files. These are served directly by Vercel as static assets with `max-age=31536000, immutable` (see `web/vercel.json`). The basic auth middleware (if it were wired) does NOT protect static assets — the matcher explicitly skips `_next/static` but does not skip `epub-cache/`.
- **Files:** `web/vercel.json` (lines 21-26), `web/src/proxy.ts` (line 44-48)
- **Impact:** Even if the middleware were connected, all EPUB content would be publicly accessible via direct URL (`/epub-cache/{hash}/ch/{idx}.json.gz`). The cache key is a truncated SHA-256 hash of the filename (only 32 hex chars = 128 bits), which is not a secret.
- **Fix approach:** Either move EPUB cache outside `public/` and serve via an API route (with auth check), or add the `epub-cache/` path to the middleware matcher so it requires authentication.

### Crawler Data Copied to `public/` in Prebuild — Build-Time Coupling

- **Issue:** The `prebuild` script in `web/package.json` runs `rm -rf public/data && mkdir -p public && cp -r ../crawler/data public/data` which copies 108MB of crawler output into the Next.js `public/` directory. This creates tight coupling between the crawler's output format and the web app's static asset serving.
- **Files:** `web/package.json` (line 13)
- **Impact:** Build times are dominated by 108MB file copy. If the crawler data directory is empty or missing, the build succeeds silently but the site has no content. The `public/data/` directory is likely tracked in git, doubling storage (crawler/data + web/public/data).
- **Fix approach:** Serve crawler data via the API route (already exists at `web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts`) and have it read directly from `../crawler/data/`. Remove the copy step. For Vercel deployment, mount the data as a read-only volume or fetch from object storage.

### No Error Boundaries in React Component Tree

- **Issue:** The React component tree has no error boundaries. If any component throws during rendering (e.g., EPUB parsing error, undefined chapter data), the entire page crashes to a white screen.
- **Files:** All page components under `web/src/app/`
- **Impact:** Poor user experience on edge cases — a corrupt data file or unexpected API response crashes the whole page with no recovery UI.
- **Fix approach:** Add a React error boundary component wrapping `ReaderClient` and `ChapterList`. Next.js app router supports `error.tsx` files — add `web/src/app/error.tsx` for a global error fallback, and `web/src/app/read/[slug]/[chapterIdx]/error.tsx` for reader-specific errors.

### `force-dynamic` on Chapter API Route Without Caching Strategy

- **Issue:** `web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts` uses `export const dynamic = "force-dynamic"` which means every request hits the filesystem. The crawler data is immutable (static JSON files), so this route could be statically generated or heavily cached.
- **Files:** `web/src/app/api/chapter/[slug]/[chapterIdx]/route.ts` (line 3)
- **Impact:** Unnecessary serverless function invocations on Vercel. Each chapter read triggers a cold filesystem read. On the free tier, function invocations are limited.
- **Fix approach:** Change to `export const dynamic = "force-static"` with `generateStaticParams()`, or use ISR with a long revalidation period. The data only changes when the crawler runs (offline), not on-demand.

---

## LOW Severity

### Test Coverage Gaps — No Component Tests

- **Issue:** All 7 test files test pure functions and hooks (`data.test.ts`, `epub-cache.test.ts`, `useProgress.test.ts`, `tts-chunks.test.ts`, `chapter-nav.test.ts`, `reader-settings.test.ts`, `site-access.test.ts`). There are zero tests for React components (`ReaderClient`, `Player`, `ChapterList`). The most complex UI logic (chapter loading state, TTS integration, scroll restoration) is untested.
- **Files:** `web/__tests__/` (all test files)
- **Impact:** UI regressions from refactoring are caught only by manual testing. The TTS integration between `useTTS` and `ReaderClient` has complex state transitions that are particularly fragile.
- **Fix approach:** Add integration tests using `@testing-library/react` for `ReaderClient` (testing loading -> ready -> error states, keyboard navigation, chapter switching). Test `Player` controls trigger correct TTS callbacks.

### No Test Coverage for Crawler Code

- **Issue:** The Python crawler (`crawler/`) has no test files. The HTML parsing logic in each crawler (`_extract_chapter`, `_extract_story_title`, `_next_chapter_url`) is tightly coupled to the source site's DOM structure and will break silently when sites change their layout.
- **Files:** `crawler/truyenqq.py`, `crawler/metruyenchu.py`, `crawler/metruyencv.py`, `crawler/truyenfullmoi.py`
- **Impact:** Site layout changes break crawlers without any test signal. The noise-filtering regex patterns in `TruyenQQCrawler.NOISE_PATTERNS` are fragile.
- **Fix approach:** Add pytest tests with saved HTML fixtures for each crawler. Test `_extract_chapter` returns expected paragraphs from known HTML. Test `_next_chapter_url` finds the correct link.

### `@smoores/epub` Dependency Is Low-Maturity

- **Issue:** `@smoores/epub@^0.1.9` is a pre-1.0 package. The `Epub` class API used in `web/src/lib/epub-parse.ts` (`readXhtmlItemContents`, `getManifest`, `getSpineItems`) could change in breaking ways.
- **Files:** `web/package.json` (line 17), `web/src/lib/epub-parse.ts`
- **Impact:** A breaking update could silently break EPUB cache generation during build. The caret range (`^0.1.9`) allows minor updates that may break.
- **Fix approach:** Pin the exact version (`"0.1.9"` without caret) or add a lockfile integrity check. Consider extracting EPUB parsing to a standalone script that runs offline, decoupled from the web build.

### EPUB Filenames with Special Characters May Break URL Routing

- **Issue:** EPUB filenames can contain Vietnamese characters, spaces, brackets, and ampersands (e.g., `Hộ Hoa Cao Thủ Tại Đô Thị (Phần 1 & 2) - Tâm Tại Lưu Lãng.epub`). These are URL-encoded in routes (`/epub/${encodeURIComponent(filename)}`) and then decoded. The `epubFilenameFromReaderSlug` function (`web/src/lib/epub-urls.ts` line 13) strips the `epub-` prefix but does not validate the result is a real filename.
- **Files:** `web/src/lib/epub-urls.ts` (lines 12-15), `web/src/app/epub/[filename]/page.tsx` (line 13)
- **Impact:** Edge cases with double-encoding or encoding mismatches could cause 404s for certain filenames. The `&` character in particular is problematic for URL parsing.
- **Fix approach:** Use the SHA-256 hash as the URL identifier instead of the raw filename, or sanitize filenames to URL-safe characters during cache generation.

### `maximumScale: 1` Viewport Setting Blocks Pinch-to-Zoom

- **Issue:** `web/src/app/layout.tsx` line 65 sets `maximumScale: 1` in the viewport meta tag. This prevents users from pinch-to-zooming on mobile devices, which is an accessibility concern.
- **Files:** `web/src/app/layout.tsx` (line 65)
- **Impact:** Users with visual impairments cannot zoom in to read text. While the reader has font size controls, the app shell (navigation, buttons) is not resizable.
- **Fix approach:** Remove `maximumScale: 1` or set it to a higher value (e.g., `5`). The custom font size controls in the reader settings provide sufficient zoom for reading content.

### All CSS Theme Colors Hardcoded — No Light Mode

- **Issue:** `web/src/lib/reader-settings.ts` defines only dark themes. The `globals.css` default colors are dark (`--color-bg: #0f0f0f`). The legacy `LEGACY_THEME_MAP` (line 146-150) maps removed light/sepia themes to dark alternatives. The entire app is dark-only.
- **Files:** `web/src/lib/reader-settings.ts` (lines 32-99, 146-150), `web/src/app/globals.css`
- **Impact:** Users who prefer light mode have no option. In bright sunlight, a dark theme can be harder to read on some screens.
- **Fix approach:** If light mode is not intended, document it as a design decision. If it is desired, add at least one light theme and respect `prefers-color-scheme` as the default.

### `findInstance()` Linear Scan on Every Data Access

- **Issue:** `web/src/lib/data.ts` line 153-155 (`findInstance`) iterates all source instances and calls `listStories()` on each to find which instance owns a given slug. `listStories()` itself calls `readdirSync` + `existsSync` checks. This means every `getChapter()`, `getChapterIndex()`, etc. call scans the entire data directory tree.
- **Files:** `web/src/lib/data.ts` (lines 153-155, 137-181)
- **Impact:** O(S * N) filesystem operations per data access, where S = number of sources and N = stories per source. With 4 sources and hundreds of stories, this is hundreds of unnecessary filesystem calls per request.
- **Fix approach:** Build a slug-to-instance index once at module initialization (`makeAllSources()` at line 183) and cache it. The index is a simple `Map<string, DataDirInstance>` built from a single scan of all source directories.

### Unhandled TTS Errors on Unsupported Browsers

- **Issue:** `web/src/hooks/useTTS.ts` checks for `window.speechSynthesis` existence at function entry but the `play()` function (line 165) silently returns if speech synthesis is missing. The `Player` component shows a "no Vietnamese voice" message but this only triggers when `viVoices.length === 0` — it does not handle the case where `speechSynthesis` itself is missing.
- **Files:** `web/src/hooks/useTTS.ts` (lines 8-16, 165-168), `web/src/components/Player.tsx` (line 85)
- **Impact:** On browsers without Speech Synthesis API (some Firefox configurations, older browsers), the play button does nothing with no error message.
- **Fix approach:** Add a `supported` boolean to the `useTTS` return value. Check `typeof window.speechSynthesis !== "undefined"` and surface the unsupported state to the Player component.

### `delete.py` Crawler Utility with No Safety Confirmations

- **Issue:** `crawler/delete.py` (152 lines) is a data deletion utility that removes story directories. It has no confirmation prompt or dry-run mode (unlike `compress.py` which defaults to dry-run).
- **Files:** `crawler/delete.py`
- **Impact:** Accidental data loss if wrong arguments are passed. Combined with the large git-tracked data, this could cause irreversible deletion.
- **Fix approach:** Add a `--dry-run` default mode (matching the pattern in `compress.py`) and require `--apply` flag for actual deletion.

### Scroll Restoration Race with Chapter Content Loading

- **Issue:** In `web/src/components/ReaderClient.tsx` lines 172-176, the `useLayoutEffect` for scroll restoration fires when `paragraphs` becomes non-null. However, the content is rendered as a flat list of `<p>` tags. If the browser has not completed layout by the time `scrollTo` is called, the scroll position may be incorrect.
- **Files:** `web/src/components/ReaderClient.tsx` (lines 172-176)
- **Impact:** On slow connections or with large chapters (thousands of paragraphs), the scroll position may overshoot or land at the wrong location after async content loads.
- **Fix approach:** Use `requestAnimationFrame` or a double-RAF pattern to ensure layout is complete before scrolling. Alternatively, use a `ResizeObserver` on the content container to detect when all paragraphs are laid out.

### Vercel `vercel.json` Headers May Conflict with Basic Auth

- **Issue:** `web/vercel.json` applies `Cache-Control: public, max-age=31536000, immutable` to all `/epub-cache/*` and `/data/*` paths. If the middleware is ever connected, these static headers would cause the CDN to cache responses that bypass authentication. The `public` directive means intermediate caches can store and serve the content without revalidation.
- **Files:** `web/vercel.json` (lines 5-26)
- **Impact:** Even with middleware auth, CDN-cached copies of chapters would be served to unauthenticated users. The `immutable` directive means the CDN will never recheck auth.
- **Fix approach:** Change `public` to `private` for data paths that should be auth-protected. Add authentication-aware cache headers from the API route (already done in `route.ts` line 22: `"private, max-age=3600"`).

---

*Concerns audit: 2026-05-19*
