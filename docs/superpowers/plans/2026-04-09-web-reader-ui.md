# Web Reader UI - Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Next.js web app to read and listen to crawled story data, with chapter navigation, TTS playback, and reading progress tracking.

**Architecture:** Server Components read JSON from filesystem at build/request time. Client Components handle interactivity (TTS, reading progress, navigation). Static deployment on Vercel. Zero backend — all data is pre-processed JSON files served from `public/data/`.

**Tech Stack:** Next.js 15 (App Router), TypeScript, Tailwind CSS v4, Web Speech API, localStorage, Vercel

---

## File Structure

```
web/
├── package.json
├── next.config.ts
├── vitest.config.ts
├── tsconfig.json
├── public/
│   └── data → ../../crawler/data       # symlink (dev) or copy (deploy)
├── src/
│   ├── app/
│   │   ├── layout.tsx                  # Root layout: dark theme, mobile viewport
│   │   ├── page.tsx                    # Home: story list
│   │   ├── globals.css                 # Tailwind base styles
│   │   ├── story/[slug]/
│   │   │   └── page.tsx                # Chapter list (wraps client component)
│   │   └── read/[slug]/[chapterIdx]/
│   │       └── page.tsx                # Reader: loads data, wraps client component
│   ├── components/
│   │   ├── ChapterList.tsx             # Client: chapter list with progress badges
│   │   ├── ReaderClient.tsx            # Client: paragraph display + TTS + nav
│   │   └── Player.tsx                  # Client: TTS floating player bar
│   ├── hooks/
│   │   ├── useTTS.ts                   # Web Speech API wrapper
│   │   └── useProgress.ts             # localStorage reading progress
│   └── lib/
│       └── data.ts                     # Server-side JSON reader (fs)
├── __tests__/
│   ├── fixtures/
│   │   └── test-story/
│   │       ├── chapters_index.json
│   │       └── vol-001-ch001-002.json
│   └── data.test.ts
```

---

### Task 1: Initialize Next.js Project

**Files:**
- Create: `web/` (via create-next-app)
- Create: `web/public/data` (symlink)
- Create: `web/vitest.config.ts`

- [ ] **Step 1: Create Next.js app**

```bash
cd /home/falcol/NgheTruyen
npx create-next-app@latest web --typescript --tailwind --app --src-dir --import-alias "@/*" --use-npm
```

- [ ] **Step 2: Create data symlink**

```bash
cd /home/falcol/NgheTruyen/web
ln -s ../../crawler/data public/data
# Verify symlink works
cat public/data/truyenqq/that-nghiep-ve-sau-bi-bao-tang-nu-hai-nhat-ve-nha-32158/chapters_index.json | head -5
```

- [ ] **Step 3: Install Vitest**

```bash
cd /home/falcol/NgheTruyen/web
npm install -D vitest @vitejs/plugin-react jsdom
```

- [ ] **Step 4: Create vitest.config.ts**

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

- [ ] **Step 5: Add test script to package.json**

Add to `web/package.json` scripts:
```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 6: Verify setup**

```bash
cd /home/falcol/NgheTruyen/web
npm run dev &
# Wait for server, then curl localhost:3000
curl -s http://localhost:3000 | head -20
# Kill dev server
kill %1
npm test
```

Expected: dev server returns HTML, test runner exits with no tests found (success).

- [ ] **Step 7: Commit**

```bash
cd /home/falcol/NgheTruyen
git add web/
git commit -m "feat: scaffold Next.js web app with Vitest"
```

---

### Task 2: Data Layer with Tests

**Files:**
- Create: `web/src/lib/data.ts`
- Create: `web/__tests__/fixtures/test-story/chapters_index.json`
- Create: `web/__tests__/fixtures/test-story/vol-001-ch001-002.json`
- Create: `web/__tests__/data.test.ts`

- [ ] **Step 1: Create test fixtures**

```bash
mkdir -p /home/falcol/NgheTruyen/web/__tests__/fixtures/test-story
```

`web/__tests__/fixtures/test-story/chapters_index.json`:
```json
[
  { "index": 0, "title": "Chương 01: Test chapter one" },
  { "index": 1, "title": "Chương 02: Test chapter two" }
]
```

`web/__tests__/fixtures/test-story/vol-001-ch001-002.json`:
```json
{
  "volume": 1,
  "chapterRange": [1, 2],
  "chapters": [
    {
      "title": "Chương 01: Test chapter one",
      "paragraphs": ["Đoạn văn thứ nhất.", "Đoạn văn thứ hai."],
      "index": 0
    },
    {
      "title": "Chương 02: Test chapter two",
      "paragraphs": ["Đoạn văn thứ ba.", "Đoạn văn thứ tư."],
      "index": 1
    }
  ]
}
```

- [ ] **Step 2: Write failing tests**

`web/__tests__/data.test.ts`:
```typescript
import { describe, it, expect } from "vitest";
import { listStories, getChapterIndex, getChapter, getTotalChapters } from "@/lib/data";

// Override DATA_DIR for tests by importing and testing with fixtures
// We test by pointing to the fixtures directory

describe("data layer", () => {
  // These tests use the actual symlink data if available,
  // or can be pointed to fixtures

  it("getChapterIndex returns array of chapter metadata", async () => {
    // Use fixtures path
    const { makeDataDir } = await import("@/lib/data");
    const getIdx = makeDataDir("__tests__/fixtures");
    const index = getIdx.getChapterIndex("test-story");
    expect(index).toHaveLength(2);
    expect(index[0]).toEqual({ index: 0, title: "Chương 01: Test chapter one" });
    expect(index[1]).toEqual({ index: 1, title: "Chương 02: Test chapter two" });
  });

  it("getChapter returns chapter paragraphs from volume file", async () => {
    const { makeDataDir } = await import("@/lib/data");
    const data = makeDataDir("__tests__/fixtures");
    const chapter = data.getChapter("test-story", 0);
    expect(chapter).not.toBeNull();
    expect(chapter!.title).toBe("Chương 01: Test chapter one");
    expect(chapter!.paragraphs).toHaveLength(2);
    expect(chapter!.paragraphs[0]).toBe("Đoạn văn thứ nhất.");
  });

  it("getChapter returns null for invalid index", async () => {
    const { makeDataDir } = await import("@/lib/data");
    const data = makeDataDir("__tests__/fixtures");
    const chapter = data.getChapter("test-story", 99);
    expect(chapter).toBeNull();
  });

  it("getTotalChapters returns correct count", async () => {
    const { makeDataDir } = await import("@/lib/data");
    const data = makeDataDir("__tests__/fixtures");
    expect(data.getTotalChapters("test-story")).toBe(2);
  });

  it("listStories returns story directories", async () => {
    const { makeDataDir } = await import("@/lib/data");
    const data = makeDataDir("__tests__/fixtures");
    const stories = data.listStories();
    expect(stories).toContain("test-story");
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
cd /home/falcol/NgheTruyen/web
npm test
```

Expected: FAIL — `@/lib/data` does not exist yet.

- [ ] **Step 4: Implement data layer**

`web/src/lib/data.ts`:
```typescript
import fs from "fs";
import path from "path";

export interface ChapterMeta {
  index: number;
  title: string;
}

export interface Chapter extends ChapterMeta {
  paragraphs: string[];
}

export interface Volume {
  volume: number;
  chapterRange: [number, number];
  chapters: Chapter[];
}

const DEFAULT_DATA_DIR = path.join(process.cwd(), "public", "data", "truyenqq");

export function makeDataDir(baseDir: string) {
  const dataDir = path.join(process.cwd(), baseDir);

  function listStories(): string[] {
    if (!fs.existsSync(dataDir)) return [];
    return fs
      .readdirSync(dataDir)
      .filter((d) => fs.statSync(path.join(dataDir, d)).isDirectory());
  }

  function getChapterIndex(slug: string): ChapterMeta[] {
    const filePath = path.join(dataDir, slug, "chapters_index.json");
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  }

  function getChapter(slug: string, chapterIdx: number): Chapter | null {
    const volNum = Math.floor(chapterIdx / 50) + 1;
    const storyDir = path.join(dataDir, slug);
    if (!fs.existsSync(storyDir)) return null;

    const files = fs.readdirSync(storyDir);
    const prefix = `vol-${String(volNum).padStart(3, "0")}-`;
    const volFile = files.find(
      (f) => f.startsWith(prefix) && f.endsWith(".json")
    );
    if (!volFile) return null;

    const volData: Volume = JSON.parse(
      fs.readFileSync(path.join(storyDir, volFile), "utf-8")
    );
    return volData.chapters.find((c) => c.index === chapterIdx) || null;
  }

  function getTotalChapters(slug: string): number {
    return getChapterIndex(slug).length;
  }

  return { listStories, getChapterIndex, getChapter, getTotalChapters };
}

// Default instance for production use
const defaultData = makeDataDir(
  path.relative(process.cwd(), path.join("public", "data", "truyenqq"))
);

export const listStories = defaultData.listStories;
export const getChapterIndex = defaultData.getChapterIndex;
export const getChapter = defaultData.getChapter;
export const getTotalChapters = defaultData.getTotalChapters;
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd /home/falcol/NgheTruyen/web
npm test
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
cd /home/falcol/NgheTruyen
git add web/src/lib/data.ts web/__tests__/
git commit -m "feat: add data layer to read crawled JSON from filesystem"
```

---

### Task 3: Root Layout and Global Styles

**Files:**
- Modify: `web/src/app/layout.tsx`
- Modify: `web/src/app/globals.css`

- [ ] **Step 1: Update globals.css**

Replace `web/src/app/globals.css` with:

```css
@import "tailwindcss";

:root {
  --color-bg: #0f0f0f;
  --color-surface: #1a1a1a;
  --color-text: #e5e5e5;
  --color-text-muted: #9ca3af;
  --color-accent: #60a5fa;
  --color-accent-dim: #3b82f6;
}

html {
  background-color: var(--color-bg);
  color: var(--color-text);
}

body {
  font-family: system-ui, -apple-system, sans-serif;
  -webkit-font-smoothing: antialiased;
}

/* Reading paragraph style */
.reader-paragraph {
  line-height: 1.9;
  font-size: 1.125rem;
  margin-bottom: 1rem;
}

/* Highlight paragraph being spoken by TTS */
.reader-paragraph.speaking {
  background-color: rgba(96, 165, 250, 0.15);
  border-left: 3px solid var(--color-accent);
  padding-left: 0.75rem;
  border-radius: 0 0.25rem 0.25rem 0;
}
```

- [ ] **Step 2: Update layout.tsx**

Replace `web/src/app/layout.tsx` with:

```typescript
import type { Metadata, Viewport } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Nghe Truyện",
  description: "Đọc và nghe truyện cá nhân",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  maximumScale: 1,
  themeColor: "#0f0f0f",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="vi">
      <body className="bg-[var(--color-bg)] text-[var(--color-text)] min-h-dvh">
        {children}
      </body>
    </html>
  );
}
```

- [ ] **Step 3: Verify in browser**

```bash
cd /home/falcol/NgheTruyen/web
npm run dev
```

Open http://localhost:3000 — should show dark background with default Next.js page.

- [ ] **Step 4: Commit**

```bash
cd /home/falcol/NgheTruyen
git add web/src/app/layout.tsx web/src/app/globals.css
git commit -m "feat: dark theme layout with reading styles"
```

---

### Task 4: Home Page — Story List

**Files:**
- Modify: `web/src/app/page.tsx`

- [ ] **Step 1: Implement home page**

Replace `web/src/app/page.tsx` with:

```typescript
import Link from "next/link";
import { listStories, getChapterIndex } from "@/lib/data";

export default function HomePage() {
  const stories = listStories();

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-6">Nghe Truyện</h1>

      {stories.length === 0 && (
        <p className="text-[var(--color-text-muted)]">
          Chưa có truyện nào. Hãy crawl dữ liệu trước.
        </p>
      )}

      <div className="space-y-3">
        {stories.map((slug) => (
          <StoryCard key={slug} slug={slug} />
        ))}
      </div>
    </main>
  );
}

function StoryCard({ slug }: { slug: string }) {
  let title = slug;
  let chapterCount = 0;

  try {
    const index = getChapterIndex(slug);
    chapterCount = index.length;
    title = index[0]?.title?.split(":")[0] || slug;
  } catch {
    // fallback to slug
  }

  return (
    <Link
      href={`/story/${slug}`}
      className="block p-4 rounded-lg bg-[var(--color-surface)] hover:bg-[var(--color-surface)]/80 transition-colors"
    >
      <div className="font-semibold text-lg truncate">{title}</div>
      <div className="text-sm text-[var(--color-text-muted)] mt-1">
        {chapterCount} chương · {slug}
      </div>
    </Link>
  );
}
```

- [ ] **Step 2: Verify in browser**

```bash
cd /home/falcol/NgheTruyen/web
npm run dev
```

Open http://localhost:3000 — should show story card with slug and chapter count.

- [ ] **Step 3: Commit**

```bash
cd /home/falcol/NgheTruyen
git add web/src/app/page.tsx
git commit -m "feat: home page with story list"
```

---

### Task 5: Chapter List Page

**Files:**
- Create: `web/src/app/story/[slug]/page.tsx`
- Create: `web/src/components/ChapterList.tsx`
- Create: `web/src/hooks/useProgress.ts`

- [ ] **Step 1: Create useProgress hook**

`web/src/hooks/useProgress.ts`:
```typescript
"use client";

import { useState, useEffect } from "react";

interface ReadingProgress {
  chapterIdx: number;
  timestamp: number;
}

export function useProgress(slug: string) {
  const key = `progress-${slug}`;
  const [progress, setProgress] = useState<ReadingProgress | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem(key);
    if (saved) {
      try {
        setProgress(JSON.parse(saved));
      } catch {
        // invalid JSON, ignore
      }
    }
  }, [key]);

  const save = (chapterIdx: number) => {
    const p: ReadingProgress = { chapterIdx, timestamp: Date.now() };
    localStorage.setItem(key, JSON.stringify(p));
    setProgress(p);
  };

  return { progress, save };
}
```

- [ ] **Step 2: Create ChapterList client component**

`web/src/components/ChapterList.tsx`:
```typescript
"use client";

import Link from "next/link";
import { useProgress } from "@/hooks/useProgress";

interface ChapterMeta {
  index: number;
  title: string;
}

export default function ChapterList({
  slug,
  chapters,
}: {
  slug: string;
  chapters: ChapterMeta[];
}) {
  const { progress } = useProgress(slug);

  return (
    <div className="space-y-1">
      {progress && (
        <Link
          href={`/read/${slug}/${progress.chapterIdx}`}
          className="block p-3 mb-4 rounded-lg bg-[var(--color-accent-dim)] text-white font-medium"
        >
          Tiếp tục đọc: {chapters[progress.chapterIdx]?.title || `Chương ${progress.chapterIdx + 1}`}
        </Link>
      )}

      {chapters.map((ch) => {
        const isRead = progress && progress.chapterIdx >= ch.index;
        const isCurrent = progress && progress.chapterIdx === ch.index;

        return (
          <Link
            key={ch.index}
            href={`/read/${slug}/${ch.index}`}
            className={`block p-3 rounded-lg transition-colors ${
              isCurrent
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                : "hover:bg-[var(--color-surface)]"
            }`}
          >
            <span className={isRead && !isCurrent ? "text-[var(--color-text-muted)]" : ""}>
              {ch.title}
            </span>
          </Link>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 3: Create story page (server component)**

Create directory:
```bash
mkdir -p /home/falcol/NgheTruyen/web/src/app/story/\[slug\]
```

`web/src/app/story/[slug]/page.tsx`:
```typescript
import Link from "next/link";
import { getChapterIndex } from "@/lib/data";
import ChapterList from "@/components/ChapterList";

export default async function StoryPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const chapters = getChapterIndex(slug);

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <Link
        href="/"
        className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-accent)] mb-4 inline-block"
      >
        ← Trang chủ
      </Link>

      <h1 className="text-xl font-bold mb-2 truncate">{slug}</h1>
      <p className="text-sm text-[var(--color-text-muted)] mb-6">
        {chapters.length} chương
      </p>

      <ChapterList slug={slug} chapters={chapters} />
    </main>
  );
}
```

- [ ] **Step 4: Verify in browser**

```bash
cd /home/falcol/NgheTruyen/web
npm run dev
```

Navigate to http://localhost:3000 → click story → see chapter list.

- [ ] **Step 5: Commit**

```bash
cd /home/falcol/NgheTruyen
git add web/src/app/story/ web/src/components/ChapterList.tsx web/src/hooks/useProgress.ts
git commit -m "feat: chapter list page with reading progress"
```

---

### Task 6: Reader Page — Chapter Display

**Files:**
- Create: `web/src/app/read/[slug]/[chapterIdx]/page.tsx`
- Create: `web/src/components/ReaderClient.tsx`

- [ ] **Step 1: Create ReaderClient component**

`web/src/components/ReaderClient.tsx`:
```typescript
"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useProgress } from "@/hooks/useProgress";

interface ReaderClientProps {
  slug: string;
  chapterIdx: number;
  totalChapters: number;
  title: string;
  paragraphs: string[];
  speakingIdx: number;
  onPlay: () => void;
  onPause: () => void;
  onStop: () => void;
  playing: boolean;
}

export default function ReaderClient({
  slug,
  chapterIdx,
  totalChapters,
  title,
  paragraphs,
  speakingIdx,
  onPlay,
  onPause,
  onStop,
  playing,
}: ReaderClientProps) {
  const router = useRouter();
  const { save } = useProgress(slug);
  const topRef = useRef<HTMLDivElement>(null);

  // Save progress on mount
  useEffect(() => {
    save(chapterIdx);
  }, [chapterIdx, save]);

  // Scroll to top on chapter change
  useEffect(() => {
    topRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chapterIdx]);

  const hasPrev = chapterIdx > 0;
  const hasNext = chapterIdx < totalChapters - 1;

  const goNext = () => {
    if (hasNext) router.push(`/read/${slug}/${chapterIdx + 1}`);
  };

  const goPrev = () => {
    if (hasPrev) router.push(`/read/${slug}/${chapterIdx - 1}`);
  };

  return (
    <main className="max-w-2xl mx-auto px-4 py-6 pb-32">
      <div ref={topRef} />

      {/* Header */}
      <div className="mb-6">
        <Link
          href={`/story/${slug}`}
          className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
        >
          ← Danh sách chương
        </Link>
        <h1 className="text-xl font-bold mt-2">{title}</h1>
        <p className="text-sm text-[var(--color-text-muted)]">
          Chương {chapterIdx + 1} / {totalChapters}
        </p>
      </div>

      {/* Content */}
      <div className="space-y-0">
        {paragraphs.map((p, i) => (
          <p
            key={i}
            className={`reader-paragraph ${i === speakingIdx ? "speaking" : ""}`}
          >
            {p}
          </p>
        ))}
      </div>

      {/* Navigation */}
      <div className="flex justify-between items-center mt-8 pt-4 border-t border-[var(--color-surface)]">
        <button
          onClick={goPrev}
          disabled={!hasPrev}
          className="px-4 py-2 rounded-lg bg-[var(--color-surface)] disabled:opacity-30 hover:bg-[var(--color-surface)]/80"
        >
          ← Trước
        </button>
        <button
          onClick={goNext}
          disabled={!hasNext}
          className="px-4 py-2 rounded-lg bg-[var(--color-surface)] disabled:opacity-30 hover:bg-[var(--color-surface)]/80"
        >
          Sau →
        </button>
      </div>
    </main>
  );
}
```

- [ ] **Step 2: Create reader page (server component)**

Create directory:
```bash
mkdir -p "/home/falcol/NgheTruyen/web/src/app/read/[slug]/[chapterIdx]"
```

`web/src/app/read/[slug]/[chapterIdx]/page.tsx`:
```typescript
import { notFound } from "next/navigation";
import { getChapter, getTotalChapters } from "@/lib/data";
import ReaderClient from "@/components/ReaderClient";

export default async function ReaderPage({
  params,
}: {
  params: Promise<{ slug: string; chapterIdx: string }>;
}) {
  const { slug, chapterIdx: idxStr } = await params;
  const chapterIdx = parseInt(idxStr, 10);

  if (isNaN(chapterIdx)) return notFound();

  const chapter = getChapter(slug, chapterIdx);
  if (!chapter) return notFound();

  const totalChapters = getTotalChapters(slug);

  // Initial render: no TTS playing
  return (
    <ReaderClientWrapper
      slug={slug}
      chapterIdx={chapterIdx}
      totalChapters={totalChapters}
      title={chapter.title}
      paragraphs={chapter.paragraphs}
    />
  );
}

// Separate wrapper to handle TTS state on client
function ReaderClientWrapper({
  slug,
  chapterIdx,
  totalChapters,
  title,
  paragraphs,
}: {
  slug: string;
  chapterIdx: number;
  totalChapters: number;
  title: string;
  paragraphs: string[];
}) {
  // This will be enhanced in Task 7 with TTS
  return (
    <ReaderClient
      slug={slug}
      chapterIdx={chapterIdx}
      totalChapters={totalChapters}
      title={title}
      paragraphs={paragraphs}
      speakingIdx={-1}
      onPlay={() => {}}
      onPause={() => {}}
      onStop={() => {}}
      playing={false}
    />
  );
}
```

Wait — `ReaderClientWrapper` is in a server component file but needs to be a client component. Let me fix this approach. The server page should pass data to the client component directly. The TTS state will be managed inside `ReaderClient` itself.

Let me revise:

`web/src/app/read/[slug]/[chapterIdx]/page.tsx`:
```typescript
import { notFound } from "next/navigation";
import { getChapter, getTotalChapters } from "@/lib/data";
import ReaderClient from "@/components/ReaderClient";

export default async function ReaderPage({
  params,
}: {
  params: Promise<{ slug: string; chapterIdx: string }>;
}) {
  const { slug, chapterIdx: idxStr } = await params;
  const chapterIdx = parseInt(idxStr, 10);

  if (isNaN(chapterIdx)) return notFound();

  const chapter = getChapter(slug, chapterIdx);
  if (!chapter) return notFound();

  const totalChapters = getTotalChapters(slug);

  return (
    <ReaderClient
      slug={slug}
      chapterIdx={chapterIdx}
      totalChapters={totalChapters}
      title={chapter.title}
      paragraphs={chapter.paragraphs}
    />
  );
}
```

And update `ReaderClient.tsx` to manage its own TTS state (for now with stubs, TTS integrated in Task 7):

`web/src/components/ReaderClient.tsx` (revised):
```typescript
"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useProgress } from "@/hooks/useProgress";

export default function ReaderClient({
  slug,
  chapterIdx,
  totalChapters,
  title,
  paragraphs,
}: {
  slug: string;
  chapterIdx: number;
  totalChapters: number;
  title: string;
  paragraphs: string[];
}) {
  const router = useRouter();
  const { save } = useProgress(slug);
  const topRef = useRef<HTMLDivElement>(null);
  const [speakingIdx, setSpeakingIdx] = useState(-1);

  // Save progress on mount
  useEffect(() => {
    save(chapterIdx);
  }, [chapterIdx, save]);

  // Scroll to top on chapter change
  useEffect(() => {
    topRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chapterIdx]);

  // Stop TTS on unmount
  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  const hasPrev = chapterIdx > 0;
  const hasNext = chapterIdx < totalChapters - 1;

  const goNext = () => {
    if (hasNext) router.push(`/read/${slug}/${chapterIdx + 1}`);
  };

  const goPrev = () => {
    if (hasPrev) router.push(`/read/${slug}/${chapterIdx - 1}`);
  };

  return (
    <main className="max-w-2xl mx-auto px-4 py-6 pb-32">
      <div ref={topRef} />

      {/* Header */}
      <div className="mb-6">
        <Link
          href={`/story/${slug}`}
          className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
        >
          ← Danh sách chương
        </Link>
        <h1 className="text-xl font-bold mt-2">{title}</h1>
        <p className="text-sm text-[var(--color-text-muted)]">
          Chương {chapterIdx + 1} / {totalChapters}
        </p>
      </div>

      {/* Content */}
      <div className="space-y-0">
        {paragraphs.map((p, i) => (
          <p
            key={i}
            className={`reader-paragraph ${i === speakingIdx ? "speaking" : ""}`}
          >
            {p}
          </p>
        ))}
      </div>

      {/* Navigation */}
      <div className="flex justify-between items-center mt-8 pt-4 border-t border-[var(--color-surface)]">
        <button
          onClick={goPrev}
          disabled={!hasPrev}
          className="px-4 py-2 rounded-lg bg-[var(--color-surface)] disabled:opacity-30 hover:bg-[var(--color-surface)]/80"
        >
          ← Trước
        </button>
        <button
          onClick={goNext}
          disabled={!hasNext}
          className="px-4 py-2 rounded-lg bg-[var(--color-surface)] disabled:opacity-30 hover:bg-[var(--color-surface)]/80"
        >
          Sau →
        </button>
      </div>
    </main>
  );
}
```

- [ ] **Step 3: Verify in browser**

```bash
cd /home/falcol/NgheTruyen/web
npm run dev
```

Navigate: Home → Story → Chapter → see paragraphs rendered with comfortable reading style.

- [ ] **Step 4: Commit**

```bash
cd /home/falcol/NgheTruyen
git add web/src/app/read/ web/src/components/ReaderClient.tsx
git commit -m "feat: reader page with chapter display and navigation"
```

---

### Task 7: TTS Hook — Web Speech API

**Files:**
- Create: `web/src/hooks/useTTS.ts`

- [ ] **Step 1: Implement useTTS hook**

`web/src/hooks/useTTS.ts`:
```typescript
"use client";

import { useState, useCallback, useRef } from "react";

export function useTTS() {
  const [playing, setPlaying] = useState(false);
  const [paused, setPaused] = useState(false);
  const [currentIdx, setCurrentIdx] = useState(-1);
  const [rate, setRateState] = useState(1);
  const [onComplete, setOnComplete] = useState<(() => void) | null>(null);

  const paragraphsRef = useRef<string[]>([]);
  const rateRef = useRef(1);
  const idxRef = useRef(-1);

  const speakNext = useCallback(
    (idx: number) => {
      if (idx >= paragraphsRef.current.length) {
        setPlaying(false);
        setCurrentIdx(-1);
        idxRef.current = -1;
        // Fire completion callback
        setOnComplete((prev) => {
          if (prev) prev();
          return null;
        });
        return;
      }

      idxRef.current = idx;
      setCurrentIdx(idx);

      const u = new SpeechSynthesisUtterance(paragraphsRef.current[idx]);
      u.lang = "vi-VN";
      u.rate = rateRef.current;

      u.onend = () => speakNext(idx + 1);
      u.onerror = () => {
        setPlaying(false);
        setCurrentIdx(-1);
      };

      window.speechSynthesis.speak(u);
    },
    [] // speakNext is stable via ref
  );

  const play = useCallback(
    (texts: string[], startIdx = 0) => {
      window.speechSynthesis.cancel();
      paragraphsRef.current = texts;
      setPlaying(true);
      setPaused(false);
      speakNext(startIdx);
    },
    [speakNext]
  );

  const pause = useCallback(() => {
    window.speechSynthesis.pause();
    setPaused(true);
  }, []);

  const resume = useCallback(() => {
    window.speechSynthesis.resume();
    setPaused(false);
  }, []);

  const stop = useCallback(() => {
    window.speechSynthesis.cancel();
    setPlaying(false);
    setPaused(false);
    setCurrentIdx(-1);
    idxRef.current = -1;
    paragraphsRef.current = [];
  }, []);

  const setRate = useCallback((newRate: number) => {
    rateRef.current = newRate;
    setRateState(newRate);
  }, []);

  const setOnChapterComplete = useCallback((cb: () => void) => {
    setOnComplete(() => cb);
  }, []);

  return {
    playing,
    paused,
    currentIdx,
    rate,
    play,
    pause,
    resume,
    stop,
    setRate,
    setOnChapterComplete,
  };
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/falcol/NgheTruyen
git add web/src/hooks/useTTS.ts
git commit -m "feat: useTTS hook wrapping Web Speech API"
```

---

### Task 8: TTS Player Component and Integration

**Files:**
- Create: `web/src/components/Player.tsx`
- Modify: `web/src/components/ReaderClient.tsx`

- [ ] **Step 1: Create Player component**

`web/src/components/Player.tsx`:
```typescript
"use client";

const RATES = [0.75, 1, 1.25, 1.5, 2];

export default function Player({
  playing,
  paused,
  rate,
  currentIdx,
  totalParagraphs,
  onPlay,
  onPause,
  onResume,
  onStop,
  onRateChange,
}: {
  playing: boolean;
  paused: boolean;
  rate: number;
  currentIdx: number;
  totalParagraphs: number;
  onPlay: () => void;
  onPause: () => void;
  onResume: () => void;
  onStop: () => void;
  onRateChange: (rate: number) => void;
}) {
  const progress =
    currentIdx >= 0 ? Math.round((currentIdx / totalParagraphs) * 100) : 0;

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-[var(--color-surface)] border-t border-gray-800 px-4 py-3 z-50">
      {/* Progress bar */}
      {playing && (
        <div className="w-full h-1 bg-gray-800 rounded-full mb-2">
          <div
            className="h-full bg-[var(--color-accent)] rounded-full transition-all"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      <div className="flex items-center justify-between max-w-2xl mx-auto">
        {/* Play/Pause/Stop controls */}
        <div className="flex items-center gap-3">
          <button
            onClick={playing && !paused ? onPause : playing && paused ? onResume : onPlay}
            className="w-12 h-12 rounded-full bg-[var(--color-accent)] text-black flex items-center justify-center text-xl font-bold"
            aria-label={playing && !paused ? "Tạm dừng" : "Phát"}
          >
            {playing && !paused ? "⏸" : "▶"}
          </button>

          {playing && (
            <button
              onClick={onStop}
              className="w-10 h-10 rounded-full bg-gray-700 flex items-center justify-center text-lg"
              aria-label="Dừng"
            >
              ⏹
            </button>
          )}
        </div>

        {/* Paragraph progress */}
        <div className="text-sm text-[var(--color-text-muted)]">
          {currentIdx >= 0
            ? `${currentIdx + 1} / ${totalParagraphs}`
            : "Sẵn sàng"}
        </div>

        {/* Speed control */}
        <div className="flex gap-1">
          {RATES.map((r) => (
            <button
              key={r}
              onClick={() => onRateChange(r)}
              className={`px-2 py-1 text-xs rounded ${
                rate === r
                  ? "bg-[var(--color-accent)] text-black font-bold"
                  : "bg-gray-700 text-[var(--color-text-muted)]"
              }`}
            >
              {r}x
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Integrate TTS into ReaderClient**

Replace `web/src/components/ReaderClient.tsx`:

```typescript
"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useProgress } from "@/hooks/useProgress";
import { useTTS } from "@/hooks/useTTS";
import Player from "@/components/Player";

export default function ReaderClient({
  slug,
  chapterIdx,
  totalChapters,
  title,
  paragraphs,
}: {
  slug: string;
  chapterIdx: number;
  totalChapters: number;
  title: string;
  paragraphs: string[];
}) {
  const router = useRouter();
  const { save } = useProgress(slug);
  const topRef = useRef<HTMLDivElement>(null);
  const tts = useTTS();

  // Save progress on mount
  useEffect(() => {
    save(chapterIdx);
  }, [chapterIdx, save]);

  // Scroll to top on chapter change
  useEffect(() => {
    topRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chapterIdx]);

  // Stop TTS on unmount
  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

  // Auto-advance to next chapter when TTS finishes
  useEffect(() => {
    tts.setOnChapterComplete(() => {
      if (chapterIdx < totalChapters - 1) {
        router.push(`/read/${slug}/${chapterIdx + 1}`);
      }
    });
  }, [chapterIdx, totalChapters, slug, router, tts.setOnChapterComplete]);

  const hasPrev = chapterIdx > 0;
  const hasNext = chapterIdx < totalChapters - 1;

  const goNext = () => {
    if (hasNext) router.push(`/read/${slug}/${chapterIdx + 1}`);
  };

  const goPrev = () => {
    if (hasPrev) router.push(`/read/${slug}/${chapterIdx - 1}`);
  };

  return (
    <>
      <main className="max-w-2xl mx-auto px-4 py-6 pb-32">
        <div ref={topRef} />

        {/* Header */}
        <div className="mb-6">
          <Link
            href={`/story/${slug}`}
            className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
          >
            ← Danh sách chương
          </Link>
          <h1 className="text-xl font-bold mt-2">{title}</h1>
          <p className="text-sm text-[var(--color-text-muted)]">
            Chương {chapterIdx + 1} / {totalChapters}
          </p>
        </div>

        {/* Content */}
        <div className="space-y-0">
          {paragraphs.map((p, i) => (
            <p
              key={i}
              className={`reader-paragraph ${i === tts.currentIdx ? "speaking" : ""}`}
            >
              {p}
            </p>
          ))}
        </div>

        {/* Navigation */}
        <div className="flex justify-between items-center mt-8 pt-4 border-t border-[var(--color-surface)]">
          <button
            onClick={goPrev}
            disabled={!hasPrev}
            className="px-4 py-2 rounded-lg bg-[var(--color-surface)] disabled:opacity-30 hover:bg-[var(--color-surface)]/80"
          >
            ← Trước
          </button>
          <button
            onClick={goNext}
            disabled={!hasNext}
            className="px-4 py-2 rounded-lg bg-[var(--color-surface)] disabled:opacity-30 hover:bg-[var(--color-surface)]/80"
          >
            Sau →
          </button>
        </div>
      </main>

      {/* Floating TTS Player */}
      <Player
        playing={tts.playing}
        paused={tts.paused}
        rate={tts.rate}
        currentIdx={tts.currentIdx}
        totalParagraphs={paragraphs.length}
        onPlay={() => tts.play(paragraphs)}
        onPause={tts.pause}
        onResume={tts.resume}
        onStop={tts.stop}
        onRateChange={tts.setRate}
      />
    </>
  );
}
```

- [ ] **Step 3: Verify in browser**

```bash
cd /home/falcol/NgheTruyen/web
npm run dev
```

Open a chapter → click Play button → hear Vietnamese TTS → see paragraph highlighting → auto-advance on chapter end.

- [ ] **Step 4: Commit**

```bash
cd /home/falcol/NgheTruyen
git add web/src/components/Player.tsx web/src/components/ReaderClient.tsx
git commit -m "feat: TTS player with Web Speech API and auto-advance"
```

---

### Task 9: Generate Static Params for Build

**Files:**
- Modify: `web/src/app/story/[slug]/page.tsx`
- Modify: `web/src/app/read/[slug]/[chapterIdx]/page.tsx`

Next.js needs `generateStaticParams` for static export. Add these to enable SSG.

- [ ] **Step 1: Add generateStaticParams to story page**

Add to `web/src/app/story/[slug]/page.tsx` (before the default export):

```typescript
import { listStories } from "@/lib/data";

export function generateStaticParams() {
  return listStories().map((slug) => ({ slug }));
}
```

- [ ] **Step 2: Add generateStaticParams to reader page**

Add to `web/src/app/read/[slug]/[chapterIdx]/page.tsx` (before the default export):

```typescript
import { listStories, getChapterIndex } from "@/lib/data";

export function generateStaticParams() {
  const params: { slug: string; chapterIdx: string }[] = [];
  for (const slug of listStories()) {
    const chapters = getChapterIndex(slug);
    for (const ch of chapters) {
      params.push({ slug, chapterIdx: String(ch.index) });
    }
  }
  return params;
}
```

- [ ] **Step 3: Verify build works**

```bash
cd /home/falcol/NgheTruyen/web
npm run build
```

Expected: Build succeeds with all pages pre-rendered.

- [ ] **Step 4: Commit**

```bash
cd /home/falcol/NgheTruyen
git add web/src/app/story/ web/src/app/read/
git commit -m "feat: add generateStaticParams for SSG build"
```

---

### Task 10: Vercel Deployment Configuration

**Files:**
- Modify: `web/package.json` (add data:copy script)
- Create: `web/vercel.json`

- [ ] **Step 1: Add data copy script to package.json**

Add to `web/package.json` scripts section:

```json
"data:copy": "rm -rf public/data && mkdir -p public && cp -r ../crawler/data public/data",
"prebuild": "npm run data:copy"
```

The `prebuild` hook runs automatically before `next build` on Vercel.

- [ ] **Step 2: Create vercel.json**

`web/vercel.json`:
```json
{
  "buildCommand": "npm run build",
  "outputDirectory": ".next"
}
```

- [ ] **Step 3: Update .gitignore for web/**

Add to `web/.gitignore` (if not already present):
```
public/data
```

(The symlink won't be committed; Vercel runs data:copy during build.)

- [ ] **Step 4: Test production build locally**

```bash
cd /home/falcol/NgheTruyen/web
npm run data:copy
npm run build
```

Expected: Build succeeds. Static pages generated for all stories and chapters.

- [ ] **Step 5: Commit**

```bash
cd /home/falcol/NgheTruyen
git add web/package.json web/vercel.json web/.gitignore
git commit -m "feat: Vercel deployment config with data copy"
```

---

## Self-Review

**1. Spec coverage:**
- Story list (home page) — Task 4
- Chapter list with progress — Task 5
- Chapter reader with paragraph display — Task 6
- Chapter navigation (prev/next) — Task 6
- Reading progress (localStorage) — Task 5 (hook) + Task 6 (integrate)
- TTS playback with Web Speech API — Tasks 7, 8
- Auto-advance to next chapter — Task 8
- Speed control — Task 8
- Player UI (Spotify-style bottom bar) — Task 8
- Dark theme — Task 3
- Mobile optimized — Task 3 (viewport) + responsive layout throughout
- Vercel deployment — Tasks 9, 10

**2. Placeholder scan:** No TBD, TODO, or placeholder patterns found. All steps contain complete code.

**3. Type consistency:**
- `ChapterMeta` = `{ index: number, title: string }` — consistent across data.ts, ChapterList, ReaderClient
- `Chapter` extends `ChapterMeta` with `paragraphs: string[]` — used in data.ts
- `useTTS` returns `{ playing, paused, currentIdx, rate, play, pause, resume, stop, setRate, setOnChapterComplete }` — matched in ReaderClient and Player
- `useProgress` returns `{ progress: ReadingProgress | null, save: (idx: number) => void }` — matched in ChapterList and ReaderClient
