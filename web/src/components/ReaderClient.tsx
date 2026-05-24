"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { adjacentChapterContentUrls, crawlChapterApiPath } from "@/lib/chapter-nav";
import { epubFilenameFromReaderSlug, chapterCacheUrlPath } from "@/lib/epub-urls";
import {
  getCachedChapter,
  loadChapterContent,
  prefetchChapterContent,
} from "@/lib/chapter-prefetch";
import { getChapterScrollY, loadProgress, useProgress } from "@/hooks/useProgress";
import { useTTS } from "@/hooks/useTTS";
import Player from "@/components/Player";
import {
  ReaderSettingsProvider,
  useReaderSettingsContext,
} from "@/context/ReaderSettingsContext";

interface ChapterMeta {
  index: number;
  title: string;
}

type ChapterState =
  | { status: "loading" }
  | { status: "ready"; paragraphs: string[] }
  | { status: "error"; message: string };

// Two content modes:
//  - `paragraphs` (sync): caller already has the chapter text — render immediately.
//  - `chapterContentUrl` (async): fetch a gzipped JSON payload client-side.
// Exactly one should be provided per page.
type ReaderClientProps = {
  slug: string;
  storyTitle: string;
  chapterIdx: number;
  totalChapters: number;
  title: string;
  chapters: ChapterMeta[];
  backHref?: string;
  readHref?: string;
} & (
  | { paragraphs: string[]; chapterContentUrl?: never }
  | { chapterContentUrl: string; paragraphs?: never }
);

export default function ReaderClient(props: ReaderClientProps) {
  return (
    <ReaderSettingsProvider>
      <ReaderClientInner {...props} />
    </ReaderSettingsProvider>
  );
}

function ReaderClientInner({
  slug,
  storyTitle,
  chapterIdx,
  totalChapters,
  title,
  paragraphs: paragraphsProp,
  chapterContentUrl,
  chapters,
  backHref,
  readHref,
}: ReaderClientProps) {
  const { shellStyle } = useReaderSettingsContext();
  const router = useRouter();
  const { saveChapter, saveScroll } = useProgress(slug);
  const topRef = useRef<HTMLDivElement>(null);
  const scrollSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tts = useTTS();
  const { prepare, setOnChapterComplete } = tts;

  const [activeChapterIdx, setActiveChapterIdx] = useState(chapterIdx);
  const [autoPlayNext, setAutoPlayNext] = useState(false);
  const [isScrollingDown, setIsScrollingDown] = useState(false);
  const lastScrollY = useRef(0);
  const touchStartY = useRef(0);
  const touchEndY = useRef(0);
  const isAtTopOnStart = useRef(false);
  const isAtBottomOnStart = useRef(false);

  useEffect(() => {
    setActiveChapterIdx(chapterIdx);
  }, [chapterIdx]);

  useEffect(() => {
    const handlePopState = () => {
      const pathParts = window.location.pathname.split("/");
      const idxStr = pathParts[pathParts.length - 1];
      const idx = parseInt(idxStr, 10);
      if (!isNaN(idx)) {
        setActiveChapterIdx(idx);
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  const chapterKey = useMemo(() => `${slug}:${activeChapterIdx}`, [slug, activeChapterIdx]);

  const activeChapterMeta = useMemo(() => {
    return chapters.find((c) => c.index === activeChapterIdx);
  }, [chapters, activeChapterIdx]);

  const activeTitle = activeChapterMeta ? activeChapterMeta.title : title;

  const [chapterState, setChapterState] = useState<ChapterState>(() =>
    paragraphsProp
      ? { status: "ready", paragraphs: paragraphsProp }
      : { status: "loading" },
  );
  const [retryNonce, setRetryNonce] = useState(0);

  const href = useCallback((idx: number) =>
    readHref ? `${readHref}/${idx}` : `/read/${slug}/${idx}`,
    [slug, readHref]
  );

  const prevHref = useMemo(
    () => href(activeChapterIdx - 1),
    [activeChapterIdx, href],
  );
  const nextHref = useMemo(
    () => href(activeChapterIdx + 1),
    [activeChapterIdx, href],
  );
  const [pickerOpen, setPickerOpen] = useState(false);
  const [filter, setFilter] = useState("");
  const pickerRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    const q = filter.trim().toLowerCase();
    if (!q) return chapters;
    return chapters.filter(
      (ch) =>
        ch.title.toLowerCase().includes(q) ||
        String(ch.index + 1).includes(q),
    );
  }, [chapters, filter]);

  useEffect(() => {
    if (!pickerOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node))
        setPickerOpen(false);
    };
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [pickerOpen]);

  useEffect(() => {
    if (pickerOpen) {
      const timer = setTimeout(() => {
        const container = pickerRef.current;
        if (container) {
          const activeEl = container.querySelector('[data-active-chapter="true"]');
          if (activeEl) {
            activeEl.scrollIntoView({ block: "nearest" });
          }
        }
      }, 0);
      return () => clearTimeout(timer);
    }
  }, [pickerOpen]);

  useEffect(() => {
    if (typeof history !== "undefined") {
      history.scrollRestoration = "manual";
    }
    if (typeof window !== "undefined") {
      lastScrollY.current = window.scrollY;
    }
  }, []);

  useEffect(() => {
    saveChapter(activeChapterIdx);
  }, [activeChapterIdx, saveChapter]);

  useEffect(() => {
    if (activeChapterMeta) {
      document.title = `${activeChapterMeta.title} - ${storyTitle}`;
    }
  }, [activeChapterMeta, storyTitle]);

  // Sync state to incoming `paragraphs` prop (sync mode) — covers chapter navigation
  // in the crawler-fed reader where each page renders with fresh paragraphs.
  useEffect(() => {
    if (paragraphsProp) {
      setChapterState({ status: "ready", paragraphs: paragraphsProp });
    }
  }, [paragraphsProp]);

  const activeChapterContentUrl = useMemo(() => {
    if (!chapterContentUrl) return undefined;
    const epubFile = epubFilenameFromReaderSlug(slug);
    if (epubFile) {
      return chapterCacheUrlPath(epubFile, activeChapterIdx);
    }
    return crawlChapterApiPath(slug, activeChapterIdx);
  }, [slug, activeChapterIdx, chapterContentUrl]);

  // Fetch chapter content (async mode) whenever URL changes or user retries.
  useEffect(() => {
    if (!activeChapterContentUrl) return;
    const controller = new AbortController();

    const cached = getCachedChapter(activeChapterContentUrl);
    if (cached) {
      setChapterState({ status: "ready", paragraphs: cached.paragraphs });
    } else {
      setChapterState({ status: "loading" });
    }

    loadChapterContent(activeChapterContentUrl, controller.signal)
      .then((payload) => {
        setChapterState({ status: "ready", paragraphs: payload.paragraphs });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : "Unknown error";
        setChapterState({ status: "error", message });
      });

    return () => controller.abort();
  }, [activeChapterContentUrl, retryNonce]);

  // Prefetch prev/next chapter JSON while reading (instant Sau/Trước when cached).
  useEffect(() => {
    const { prev, next } = adjacentChapterContentUrls(slug, chapters, activeChapterIdx);
    if (prev) prefetchChapterContent(prev).catch(() => {});
    if (next) prefetchChapterContent(next).catch(() => {});
  }, [slug, chapters, activeChapterIdx]);

  const paragraphs = chapterState.status === "ready" ? chapterState.paragraphs : null;

  // Restore scroll only after content renders (otherwise the page is empty).
  useLayoutEffect(() => {
    if (!paragraphs) return;
    const scrollY = getChapterScrollY(loadProgress(slug), activeChapterIdx);
    window.scrollTo({ top: scrollY, left: 0 });
  }, [slug, activeChapterIdx, paragraphs]);

  useEffect(() => {
    const flushScroll = () => {
      if (scrollSaveTimer.current) {
        clearTimeout(scrollSaveTimer.current);
        scrollSaveTimer.current = null;
      }
      saveScroll(activeChapterIdx, window.scrollY);
    };

    const onScroll = () => {
      const currentScrollY = window.scrollY;
      if (scrollSaveTimer.current) clearTimeout(scrollSaveTimer.current);
      scrollSaveTimer.current = setTimeout(
        () => saveScroll(activeChapterIdx, currentScrollY),
        200,
      );

      const isAtBottom = window.innerHeight + currentScrollY >= document.body.scrollHeight - 10;
      if (currentScrollY <= 0 || isAtBottom) {
        setIsScrollingDown(false);
      } else if (currentScrollY > lastScrollY.current + 10) {
        setIsScrollingDown(true);
      } else if (currentScrollY < lastScrollY.current - 10) {
        setIsScrollingDown(false);
      }
      lastScrollY.current = currentScrollY;
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pagehide", flushScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", flushScroll);
      flushScroll();
    };
  }, [activeChapterIdx, saveScroll]);

  useEffect(() => {
    if (paragraphs) prepare(chapterKey, paragraphs);
  }, [chapterKey, paragraphs, prepare]);

  const navigateToChapter = useCallback(
    (newIdx: number) => {
      if (newIdx < 0 || newIdx >= totalChapters) return;
      setActiveChapterIdx(newIdx);

      const newUrl = href(newIdx);
      window.history.pushState(null, "", newUrl);
    },
    [href, totalChapters],
  );

  const hasPrev = activeChapterIdx > 0;
  const hasNext = activeChapterIdx < totalChapters - 1;

  const goNext = useCallback(() => {
    if (hasNext) navigateToChapter(activeChapterIdx + 1);
  }, [hasNext, activeChapterIdx, navigateToChapter]);

  const goPrev = useCallback(() => {
    if (hasPrev) navigateToChapter(activeChapterIdx - 1);
  }, [hasPrev, activeChapterIdx, navigateToChapter]);

  const navRef = useRef({ goNext, goPrev });
  useEffect(() => {
    navRef.current = { goNext, goPrev };
  });

  useEffect(() => {
    setOnChapterComplete(() => {
      if (activeChapterIdx < totalChapters - 1) {
        setAutoPlayNext(true);
        navigateToChapter(activeChapterIdx + 1);
      }
    });
  }, [activeChapterIdx, totalChapters, navigateToChapter, setOnChapterComplete]);

  useEffect(() => {
    if (paragraphs && autoPlayNext) {
      setAutoPlayNext(false);
      tts.play(chapterKey, paragraphs);
    }
  }, [paragraphs, autoPlayNext, chapterKey, tts]);

  // Prefetch adjacent chapters so navigation feels instant
  useEffect(() => {
    if (hasNext) router.prefetch(nextHref);
    if (hasPrev) router.prefetch(prevHref);
  }, [hasNext, hasPrev, nextHref, prevHref, router]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") navRef.current.goPrev();
      if (e.key === "ArrowRight") navRef.current.goNext();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  useEffect(() => {
    const handleTouchStart = (e: TouchEvent) => {
      touchStartY.current = e.touches[0].clientY;
      touchEndY.current = e.touches[0].clientY;
      isAtTopOnStart.current = window.scrollY <= 10;
      isAtBottomOnStart.current = window.innerHeight + window.scrollY >= document.documentElement.scrollHeight - 10;
    };
    
    const handleTouchMove = (e: TouchEvent) => {
      touchEndY.current = e.touches[0].clientY;
    };

    const handleTouchEnd = () => {
      if (!touchStartY.current || !touchEndY.current) return;
      
      const distance = touchStartY.current - touchEndY.current;
      const threshold = 100;

      if (distance > threshold && isAtBottomOnStart.current) {
        navRef.current.goNext();
      } else if (distance < -threshold && isAtTopOnStart.current) {
        navRef.current.goPrev();
      }

      touchStartY.current = 0;
      touchEndY.current = 0;
    };

    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchmove", handleTouchMove, { passive: true });
    window.addEventListener("touchend", handleTouchEnd);

    return () => {
      window.removeEventListener("touchstart", handleTouchStart);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
    };
  }, []);

  return (
    <div className="reader-shell min-h-dvh overscroll-y-none" style={shellStyle}>
      <main className="max-w-3xl mx-auto px-4 md:px-6 py-6 pb-32 reader-content">
        <div ref={topRef} />

        <div className="mb-6">
          <Link
            href={backHref ?? `/story/${slug}`}
            className="text-sm reader-muted"
          >
            ← Danh sách chương
          </Link>
          <p className="text-sm reader-muted mt-2">{storyTitle}</p>
          <h1 className="text-xl font-bold mt-2">{activeTitle}</h1>
          <div className="flex items-center gap-2 mt-2">
            <button
              onClick={() => { setPickerOpen((o) => !o); setFilter(""); }}
              className="text-sm reader-accent hover:underline cursor-pointer"
            >
              Chương {activeChapterIdx + 1} / {totalChapters} ▾
            </button>
          </div>
          {pickerOpen && (
            <div ref={pickerRef} className="mt-2 rounded-lg border border-[var(--color-surface)] bg-[var(--color-bg)] max-h-64 flex flex-col">
              <input
                autoFocus
                type="text"
                placeholder="Tìm chương..."
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="px-3 py-2 text-sm bg-transparent border-b border-[var(--color-surface)] outline-none"
              />
              <div className="overflow-y-auto flex-1">
                {filtered.map((ch) => (
                  <a
                    key={ch.index}
                    href={href(ch.index)}
                    onClick={(e) => {
                      e.preventDefault();
                      setPickerOpen(false);
                      navigateToChapter(ch.index);
                    }}
                    data-active-chapter={ch.index === activeChapterIdx ? "true" : "false"}
                    className={`block px-3 py-2 text-sm truncate hover:bg-[var(--color-surface)] cursor-pointer ${
                      ch.index === activeChapterIdx
                        ? "text-[var(--color-accent)] font-medium"
                        : ""
                    }`}
                  >
                    {ch.title}
                  </a>
                ))}
                {filtered.length === 0 && (
                  <p className="px-3 py-4 text-sm text-[var(--color-text-muted)] text-center">
                    Không tìm thấy
                  </p>
                )}
              </div>
            </div>
          )}
        </div>

        {chapterState.status === "loading" && (
          <div className="space-y-3" aria-busy="true">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-4 rounded reader-surface animate-pulse"
                style={{ width: `${70 + ((i * 13) % 25)}%` }}
              />
            ))}
          </div>
        )}

        {chapterState.status === "error" && (
          <div className="p-4 rounded-lg reader-surface">
            <p className="text-sm reader-muted mb-3">
              Không tải được chương: {chapterState.message}
            </p>
            <button
              onClick={() => setRetryNonce((n) => n + 1)}
              className="px-3 py-1.5 text-sm rounded reader-accent hover:underline cursor-pointer"
            >
              Thử lại
            </button>
          </div>
        )}

        {chapterState.status === "ready" && (
          <div className="space-y-0">
            {chapterState.paragraphs.map((p, i) => (
              <p
                key={i}
                className={`reader-paragraph ${
                  tts.activeRange &&
                  i >= tts.activeRange.start &&
                  i <= tts.activeRange.end
                    ? "speaking"
                    : ""
                }`}
              >
                {p}
              </p>
            ))}
          </div>
        )}

        <div className="flex justify-between items-center mt-8 pt-4 border-t reader-border">
          <button
            onClick={goPrev}
            disabled={!hasPrev}
            className="px-4 py-2 rounded-lg reader-surface disabled:opacity-30 hover:opacity-80"
          >
            ← Trước
          </button>
          <button
            onClick={goNext}
            disabled={!hasNext}
            className="px-4 py-2 rounded-lg reader-surface disabled:opacity-30 hover:opacity-80"
          >
            Sau →
          </button>
        </div>
      </main>

      <Player
        hidden={isScrollingDown}
        playing={tts.playing}
        paused={tts.paused}
        loading={tts.loading}
        rate={tts.rate}
        currentIdx={tts.currentIdx}
        totalParagraphs={paragraphs?.length ?? 0}
        viVoices={tts.viVoices}
        selectedVoiceName={tts.selectedVoiceName}
        onPlay={() => paragraphs && tts.play(chapterKey, paragraphs)}
        onPause={tts.pause}
        onResume={tts.resume}
        onStop={tts.stop}
        onSkipForward={tts.skipForward}
        onSkipBackward={tts.skipBackward}
        onRateChange={tts.setRate}
        onVoiceChange={tts.setVoice}
      />
    </div>
  );
}
