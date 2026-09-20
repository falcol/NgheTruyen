"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import {
  adjacentChapterContentUrls,
  crawlChapterApiPath,
} from "@/lib/chapter-nav";
import {
  CHAPTER_LIST_PAGE,
  filterChapters,
  visibleChapterWindow,
  windowRangeForJump,
} from "@/lib/chapter-list";
import { prefetchChapterContent } from "@/lib/chapter-prefetch";
import { chapterCacheUrlPath, epubFilenameFromReaderSlug } from "@/lib/epub-urls";
import { useProgress } from "@/hooks/useProgress";
import { MagnifyingGlass, CaretDown, CircleNotch, PlayCircle, X } from "@/components/icons";

interface ChapterMeta {
  index: number;
  title: string;
}

function chapterContentUrl(slug: string, chapterIdx: number): string | null {
  const epubFile = epubFilenameFromReaderSlug(slug);
  if (epubFile) return chapterCacheUrlPath(epubFile, chapterIdx);
  return crawlChapterApiPath(slug, chapterIdx);
}

export default function ChapterList({
  slug,
  chapters,
  readHref,
}: {
  slug: string;
  chapters: ChapterMeta[];
  readHref?: string;
}) {
  const router = useRouter();
  const { progress } = useProgress(slug);
  const [query, setQuery] = useState("");
  const [rangeStart, setRangeStart] = useState(0);
  const [visibleCount, setVisibleCount] = useState(CHAPTER_LIST_PAGE);
  const topSentinelRef = useRef<HTMLDivElement>(null);
  const bottomSentinelRef = useRef<HTMLDivElement>(null);
  const searchBoxRef = useRef<HTMLInputElement>(null);
  const pendingJumpIdx = useRef<number | null>(null);
  const pinSearchRef = useRef(false);
  const loadMoreArmedRef = useRef(true);
  const pendingPrepend = useRef<{ id: string; top: number } | null>(null);
  const firstVisibleIdx = useRef<number | null>(null);

  const filtered = useMemo(() => filterChapters(chapters, query), [chapters, query]);
  const { items: visible, hasMoreBefore, hasMoreAfter } = useMemo(
    () => visibleChapterWindow(filtered, rangeStart, visibleCount),
    [filtered, rangeStart, visibleCount],
  );
  firstVisibleIdx.current = visible[0]?.index ?? null;

  function setSearchQuery(value: string) {
    setQuery(value);
    setRangeStart(0);
    setVisibleCount(CHAPTER_LIST_PAGE);
    pinSearchRef.current = true;
    loadMoreArmedRef.current = false;
  }

  useLayoutEffect(() => {
    const prepend = pendingPrepend.current;
    if (prepend) {
      pendingPrepend.current = null;
      const el = document.getElementById(prepend.id);
      if (el) window.scrollBy(0, el.getBoundingClientRect().top - prepend.top);
    }
    const jumpIdx = pendingJumpIdx.current;
    if (jumpIdx != null) {
      const el = document.getElementById(`ch-${jumpIdx}`);
      if (el) {
        pendingJumpIdx.current = null;
        el.scrollIntoView({ behavior: "instant", block: "center" });
        loadMoreArmedRef.current = true;
      }
    }
    if (!pinSearchRef.current) return;
    pinSearchRef.current = false;
    searchBoxRef.current?.scrollIntoView({ block: "start", behavior: "instant" });
  });

  useEffect(() => {
    const top = topSentinelRef.current;
    const bottom = bottomSentinelRef.current;
    if (!top && !bottom) return;
    const obs = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) {
          loadMoreArmedRef.current = true;
          continue;
        }
        if (!loadMoreArmedRef.current) continue;
        if (entry.target === top) {
          const idx = firstVisibleIdx.current;
          const anchor = idx == null ? null : document.getElementById(`ch-${idx}`);
          if (anchor) {
            pendingPrepend.current = {
              id: `ch-${idx}`,
              top: anchor.getBoundingClientRect().top,
            };
          }
          setRangeStart((s) => Math.max(0, s - CHAPTER_LIST_PAGE));
          setVisibleCount((n) => n + CHAPTER_LIST_PAGE);
        } else if (entry.target === bottom) {
          setVisibleCount((n) => n + CHAPTER_LIST_PAGE);
        }
      }
    });
    if (top) obs.observe(top);
    if (bottom) obs.observe(bottom);
    return () => obs.disconnect();
  }, [hasMoreBefore, hasMoreAfter, rangeStart, visibleCount, filtered.length]);

  const href = (idx: number) =>
    readHref ? `${readHref}/${idx}` : `/read/${slug}/${idx}`;

  // `href` is recreated each render; deps intentionally track its real inputs
  // (slug, readHref) instead of the unstable `href` ref to keep this memoized.
  /* eslint-disable react-hooks/preserve-manual-memoization, react-hooks/exhaustive-deps */
  const prefetchOnIntent = useCallback(
    (chapterIdx: number) => {
      router.prefetch(href(chapterIdx));

      const main = chapterContentUrl(slug, chapterIdx);
      if (main) prefetchChapterContent(main).catch(() => {});

      const { prev, next } = adjacentChapterContentUrls(slug, chapters, chapterIdx);
      if (prev) prefetchChapterContent(prev).catch(() => {});
      if (next) prefetchChapterContent(next).catch(() => {});
    },
    [slug, chapters, router, readHref],
  );
  /* eslint-enable react-hooks/preserve-manual-memoization, react-hooks/exhaustive-deps */

  useEffect(() => {
    if (progress) prefetchOnIntent(progress.chapterIdx);
  }, [progress, prefetchOnIntent]);

  return (
    <div className="space-y-1.5">
      {progress && (
        <Link
          href={href(progress.chapterIdx)}
          onMouseEnter={() => prefetchOnIntent(progress.chapterIdx)}
          onFocus={() => prefetchOnIntent(progress.chapterIdx)}
          className="block p-4 mb-8 rounded-2xl bg-[var(--color-surface)] border border-[var(--color-accent)]/30 hover:border-[var(--color-accent)]/50 hover:-translate-y-0.5 transition-all duration-300"
        >
          <div className="flex items-center justify-between">
            <div className="truncate pr-4">
              <div className="text-[10px] sm:text-xs text-[var(--color-accent)] uppercase tracking-widest mb-1 font-bold">Tiếp tục đọc</div>
              <div className="text-base font-medium truncate">
                {chapters.find((ch) => ch.index === progress.chapterIdx)?.title ||
                  `Chương ${progress.chapterIdx + 1}`}
              </div>
            </div>
            <div className="w-10 h-10 shrink-0 rounded-full flex items-center justify-center bg-[var(--color-accent)]/10">
              <PlayCircle size={22} weight="fill" className="text-[var(--color-accent)] translate-x-[1px]" />
            </div>
          </div>
        </Link>
      )}

      {progress && (
        <div className="flex items-center gap-2 mb-3 text-xs text-[var(--color-text-muted)]">
          <div className="flex-1 h-1 rounded-full bg-white/10 overflow-hidden">
            <div
              className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-700"
              style={{ width: `${Math.round(((progress.chapterIdx + 1) / chapters.length) * 100)}%` }}
            />
          </div>
          <span className="shrink-0 font-medium text-[var(--color-text-muted)]">
            {progress.chapterIdx + 1} / {chapters.length}
          </span>
        </div>
      )}

      {progress && !query && (
        <button
          onClick={() => {
            pendingJumpIdx.current = progress.chapterIdx;
            loadMoreArmedRef.current = false;
            const range = windowRangeForJump(chapters, progress.chapterIdx);
            setRangeStart(range.start);
            setVisibleCount(range.count);
          }}
          className="text-xs text-[var(--color-accent)] hover:underline mb-3 flex items-center gap-1 transition-opacity"
        >
          <CaretDown size={12} /> Đến chương đang đọc
        </button>
      )}

      <div className="relative mb-4">
        <input
          ref={searchBoxRef}
          type="search"
          value={query}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder="Tìm chương..."
          className="w-full pl-9 pr-9 py-2.5 rounded-lg bg-[var(--color-surface)] border border-[var(--color-border)] text-sm text-[var(--color-text)] placeholder:text-[var(--color-text-muted)] focus:outline-none focus:border-[var(--color-accent)]/50 transition-colors scroll-mt-20"
        />
        <MagnifyingGlass size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)]" />
        {query && (
          <button onClick={() => setSearchQuery("")} className="absolute right-3 top-1/2 -translate-y-1/2 text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors">
            <X size={14} />
          </button>
        )}
      </div>

      {filtered.length === 0 && query && (
        <p className="text-center text-[var(--color-text-muted)] py-8 text-sm">Không tìm thấy chương nào</p>
      )}

      {hasMoreBefore && (
        <div
          ref={topSentinelRef}
          className="py-4 flex items-center justify-center gap-1.5 text-xs text-[var(--color-text-muted)] italic"
        >
          <CircleNotch size={14} className="animate-spin" />
          Đang tải thêm...
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 md:gap-x-5">
        {visible.map((ch) => {
          const isRead = progress && progress.chapterIdx >= ch.index;
          const isCurrent = progress && progress.chapterIdx === ch.index;

          return (
            <Link
              key={ch.index}
              id={`ch-${ch.index}`}
              href={href(ch.index)}
              onMouseEnter={() => prefetchOnIntent(ch.index)}
              onFocus={() => prefetchOnIntent(ch.index)}
              className={`block px-4 py-3 sm:px-5 sm:py-4 rounded-2xl border transition-all duration-300 [content-visibility:auto] [contain-intrinsic-size:auto_64px] ${
                isCurrent
                  ? "bg-[var(--color-accent)]/10 border-[var(--color-accent)]/40"
                  : isRead
                    ? "border-[var(--color-border)] bg-[var(--color-surface)]/60 hover:bg-[var(--color-surface)]"
                    : "border-[var(--color-border)] bg-[var(--color-surface)] hover:bg-white/5 hover:-translate-y-0.5"
              }`}
            >
              <div className="flex items-center gap-3 sm:gap-4">
                <div className={`w-7 h-7 sm:w-8 sm:h-8 rounded-full flex items-center justify-center shrink-0 text-[10px] sm:text-xs font-bold transition-colors ${
                  isCurrent
                    ? "bg-[var(--color-accent)] text-black"
                    : isRead
                      ? "bg-white/5 text-[var(--color-text-muted)]"
                      : "bg-white/10 text-[var(--color-text)]"
                }`}>
                  {ch.index + 1}
                </div>
                <span
                  className={`block truncate flex-1 text-sm sm:text-base ${
                    isRead && !isCurrent ? "text-[var(--color-text-muted)] opacity-60 font-normal" : "font-medium text-[var(--color-text)]"
                  }`}
                >
                  {ch.title}
                </span>
                {isCurrent && <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)]"></span>}
              </div>
            </Link>
          );
        })}
      </div>
      {hasMoreAfter && (
        <div
          ref={bottomSentinelRef}
          className="py-4 flex items-center justify-center gap-1.5 text-xs text-[var(--color-text-muted)] italic"
        >
          <CircleNotch size={14} className="animate-spin" />
          Đang tải thêm...
        </div>
      )}
    </div>
  );
}
