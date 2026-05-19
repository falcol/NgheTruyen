# Testing Patterns

**Analysis Date:** 2026-05-19

## Test Framework

**Runner:**
- Vitest 4.1.4
- Config: `web/vitest.config.ts`

**Assertion Library:**
- Vitest built-in (`expect` from `vitest`)

**Run Commands:**
```bash
cd web && npm test          # Run all tests (vitest run)
cd web && npm run test:watch  # Watch mode (vitest)
```

**Vitest Configuration:**
```typescript
// web/vitest.config.ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
});
```

## Test File Organization

**Location:** Separate `__tests__` directory at web root:
```
web/
├── __tests__/
│   ├── chapter-nav.test.ts
│   ├── data.test.ts
│   ├── epub-cache.test.ts
│   ├── fixtures/
│   │   └── test-story/
│   │       ├── chapters_index.json
│   │       ├── metadata.json
│   │       └── vol-001-ch001-002.json
│   ├── reader-settings.test.ts
│   ├── site-access.test.ts
│   ├── tts-chunks.test.ts
│   └── useProgress.test.ts
```

**Naming:** `<module-name>.test.ts` — matches the source module name. Test for `web/src/lib/chapter-nav.ts` is `web/__tests__/chapter-nav.test.ts`.

## Test Structure

**Suite Organization:**
```typescript
import { describe, expect, it } from "vitest";
import { adjacentChapterContentUrls } from "@/lib/chapter-nav";

describe("adjacentChapterContentUrls", () => {
  const chapters = [
    { index: 0, title: "A" },
    { index: 1, title: "B" },
    { index: 5, title: "F" },
  ];

  it("returns API paths for crawl stories", () => {
    const urls = adjacentChapterContentUrls("my-story", chapters, 1);
    expect(urls.prev).toBe("/api/chapter/my-story/0");
    expect(urls.next).toBe("/api/chapter/my-story/5");
  });
});
```

**Patterns:**
- Import test functions from `vitest`: `describe`, `expect`, `it`, `vi`, `afterEach`
- Import the function under test using `@/` alias
- One `describe` block per module or function group
- Shared test data defined at `describe` scope
- One assertion per `it` block (loosely followed — some tests have multiple expects)

## Mocking

**Framework:** Vitest built-in (`vi`)

**Patterns:**
```typescript
import { describe, expect, it, vi, afterEach } from "vitest";

describe("site access helpers", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("validates configured basic auth credentials", () => {
    vi.stubEnv("SITE_BASIC_AUTH_USER", "admin");
    vi.stubEnv("SITE_BASIC_AUTH_PASSWORD", "secret-pass");
    const validHeader = `Basic ${btoa("admin:secret-pass")}`;

    expect(isSiteBasicAuthConfigured()).toBe(true);
  });
});
```

**What to Mock:**
- Environment variables via `vi.stubEnv()` / `vi.unstubAllEnvs()` (see `web/__tests__/site-access.test.ts`)
- File system operations use real temp directories with cleanup in `afterEach` (see `web/__tests__/epub-cache.test.ts`)

**What NOT to Mock:**
- Pure functions and data transformations — tested directly
- The data layer — uses fixture files on disk

## Fixtures and Factories

**Test Data:**
Static JSON fixture files in `web/__tests__/fixtures/`:
```json
// fixtures/test-story/chapters_index.json
[
  { "index": 0, "title": "Chuong 01: Test chapter one" },
  { "index": 1, "title": "Chuong 02: Test chapter two" }
]

// fixtures/test-story/metadata.json
{ "story_title": "Test Story Title" }
```

**Location:** `web/__tests__/fixtures/test-story/`

**Usage:** Data layer tests point `makeDataDir` at the fixtures directory:
```typescript
const data = makeDataDir("__tests__/fixtures");
```

**Filesystem fixture pattern for cache tests:** Temp directories created per test and cleaned up in `afterEach`:
```typescript
let tmpDir: string;

afterEach(() => {
  if (tmpDir && fs.existsSync(tmpDir)) {
    fs.rmSync(tmpDir, { recursive: true, force: true });
  }
});

it("...", () => {
  tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "epub-cache-"));
  // ... use tmpDir
});
```

## Coverage

**Requirements:** No coverage target enforced. No coverage config in `vitest.config.ts`.

**View Coverage:**
```bash
cd web && npx vitest run --coverage
```

## Test Types

**Unit Tests:**
- All current tests are unit tests
- Scope: pure functions, data parsing, validation logic
- No external dependencies, network calls, or database access in tests

**Integration Tests:**
- Not present as a separate category
- The `data.test.ts` tests edge close to integration by reading real fixture files through the data layer

**E2E Tests:**
- Not used

**Component Tests:**
- Not used (no React component rendering tests despite `@vitejs/plugin-react` and `jsdom` environment being configured)

## What Is Tested

| Module | Test File | What's Covered |
|--------|-----------|---------------|
| `src/lib/chapter-nav.ts` | `__tests__/chapter-nav.test.ts` | URL generation for prev/next chapters |
| `src/lib/data.ts` | `__tests__/data.test.ts` | Story listing, chapter index, chapter retrieval, metadata |
| `src/lib/epub-cache.ts` | `__tests__/epub-cache.test.ts` | Cache read/write, invalidation, gzip round-trip, index |
| `src/lib/reader-settings.ts` | `__tests__/reader-settings.test.ts` | Settings parsing, theme mapping, CSS var generation |
| `src/lib/site-access.ts` | `__tests__/site-access.test.ts` | Basic auth header decode, credential validation |
| `src/lib/tts-chunks.ts` | `__tests__/tts-chunks.test.ts` | Chunk building, chunk size limits, paragraph lookup |
| `src/hooks/useProgress.ts` | `__tests__/useProgress.test.ts` | Progress parsing, legacy migration |

## What Is NOT Tested

| Module | Gap |
|--------|-----|
| `src/components/Player.tsx` | No component rendering tests |
| `src/components/ReaderClient.tsx` | No component rendering tests |
| `src/components/ChapterList.tsx` | No component rendering tests |
| `src/components/EpubCacheMissing.tsx` | No component rendering tests |
| `src/hooks/useTTS.ts` | No tests (complex hook with browser Speech API) |
| `src/hooks/useReaderSettings.ts` | No tests (the underlying lib is tested) |
| `src/lib/chapter-prefetch.ts` | No tests (client-side fetch + cache) |
| `src/lib/epub-parse.ts` | No tests (build-only EPUB parsing) |
| `src/lib/epub.ts` | No tests (thin runtime wrapper) |
| `src/lib/epub-urls.ts` | No tests (URL generation helpers) |
| `src/app/api/chapter/[slug]/[chapterIdx]/route.ts` | No API route tests |
| `src/proxy.ts` | No middleware tests |
| `crawler/` (Python) | No tests at all |

## Common Patterns

**Async Testing:**
No async tests currently. All tests are synchronous function calls.

**Error Testing:**
```typescript
it("falls back on invalid ids", () => {
  const s = parseStoredReaderSettings(
    JSON.stringify({ themeId: "nope", fontId: "bad", fontSizeId: "x" }),
  );
  expect(s.themeId).toBe("dark");  // default fallback
});
```

**Null/edge-case Testing:**
```typescript
it("returns null for non-existent slug", () => {
  expect(data.getChapterIndex("non-existent")).toBeNull();
});

it("returns null for invalid index", () => {
  const chapter = data.getChapter("test-story", 99);
  expect(chapter).toBeNull();
});
```

**Migration/compatibility Testing:**
```typescript
it("migrates legacy scrollY field", () => {
  const p = parseProgress({ chapterIdx: 7, scrollY: 900 });
  expect(getChapterScrollY(p, 7)).toBe(900);
});
```

## CI Test Configuration

**CI Pipeline:** None detected. No `.github/workflows/`, no CI config in `package.json`.

**Pre-push:** No husky, lint-staged, or pre-push hooks configured.

## Testing Conventions Summary

1. **Test only pure functions and data-layer logic** — no component tests, no hook tests with side effects
2. **Use real filesystem with temp dirs** for cache tests (not mocks)
3. **Use static JSON fixtures** for data layer tests
4. **One `describe` per module**, `it` blocks for individual cases
5. **No test utilities or shared helpers** — each test file is self-contained
6. **Vitest with jsdom environment** configured but not yet used for React component testing

---

*Testing analysis: 2026-05-19*
