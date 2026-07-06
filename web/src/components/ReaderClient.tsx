"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { flushSync } from "react-dom";
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
import {
  MagnifyingGlass,
  CaretUp,
  CaretDown,
  CaretLeft,
  CaretRight,
  CircleNotch,
  X,
} from "@/components/icons";

interface ChapterMeta {
  index: number;
  title: string;
}

type ChapterState =
  | { status: "loading" }
  | { status: "ready"; paragraphs: string[]; idx: number }
  | { status: "error"; message: string };

// Picker windowing: render only chapters near the current one so opening the list
// stays fast on novels with hundreds/thousands of chapters.
const PICKER_WINDOW_HALF = 40;
const PICKER_LOAD_STEP = 40;

// Two content modes:
//  - `paragraphs` (sync): caller already has the chapter text, render immediately.
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
      {/* eslint-disable-next-line no-use-before-define -- hoisted function declaration, defined below */}
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
  const scrollSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tts = useTTS();
  const { prepare, setOnChapterComplete } = tts;

  const [activeChapterIdx, setActiveChapterIdx] = useState(chapterIdx);
  const [autoPlayNext, setAutoPlayNext] = useState(false);
  const [isScrollingDown, setIsScrollingDown] = useState(false);
  const lastScrollY = useRef(0);
  const touchStartY = useRef(0);
  const touchEndY = useRef(0);
  const touchedTopDuringGesture = useRef(false);
  const touchedBottomDuringGesture = useRef(false);
  const overscrollNavigating = useRef(false);
  const [overscrollDelta, setOverscrollDelta] = useState(0);
  const [overscrollDir, setOverscrollDir] = useState<"up" | "down" | null>(null);
  const [chapterFade, setChapterFade] = useState(false);

  // DOM refs for paragraphs (auto-follow + "play from here").
  const paragraphRefs = useRef<(HTMLParagraphElement | null)[]>([]);
  // Pause auto-follow briefly while the user scrolls manually during playback.
  const followPausedUntilRef = useRef(0);
  // Chapter scroll-progress bar, updated directly to avoid re-renders.
  const progressRef = useRef<HTMLDivElement>(null);
  // Latest values for the keyboard handler (avoids stale closure + listener churn).
  const latestRef = useRef<{
    tts: typeof tts;
    paragraphs: string[] | null;
    chapterKey: string;
  }>({ tts, paragraphs: null, chapterKey: "" });

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

  const activeChapterMeta = useMemo(() => {
    return chapters.find((c) => c.index === activeChapterIdx);
  }, [chapters, activeChapterIdx]);

  const activeTitle = activeChapterMeta ? activeChapterMeta.title : title;

  const [chapterState, setChapterState] = useState<ChapterState>(() =>
    paragraphsProp
      ? { status: "ready", paragraphs: paragraphsProp, idx: chapterIdx }
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
  const pickerContainerRef = useRef<HTMLDivElement>(null);
  // Extra chapters the user has loaded beyond the initial window (each direction).
  const [pickerExtraBefore, setPickerExtraBefore] = useState(0);
  const [pickerExtraAfter, setPickerExtraAfter] = useState(0);

  const pickerList = useMemo(() => {
    const q = filter.trim().toLowerCase();
    const list = q
      ? chapters.filter(
          (ch) =>
            ch.title.toLowerCase().includes(q) ||
            String(ch.index + 1).includes(q),
        )
      : chapters;

    if (list.length === 0) {
      return {
        items: [] as ChapterMeta[],
        startIdx: 0,
        endIdx: 0,
        hasMoreBefore: false,
        hasMoreAfter: false,
        total: 0,
      };
    }

    const foundPos = list.findIndex((c) => c.index === activeChapterIdx);
    const anchorPos = q ? 0 : foundPos === -1 ? 0 : foundPos;
    const startIdx = Math.max(0, anchorPos - (PICKER_WINDOW_HALF + pickerExtraBefore));
    const endIdx = Math.min(
      list.length,
      anchorPos + 1 + (PICKER_WINDOW_HALF + pickerExtraAfter),
    );

    return {
      items: list.slice(startIdx, endIdx),
      startIdx,
      endIdx,
      hasMoreBefore: startIdx > 0,
      hasMoreAfter: endIdx < list.length,
      total: list.length,
    };
  }, [chapters, filter, activeChapterIdx, pickerExtraBefore, pickerExtraAfter]);

  useEffect(() => {
    if (!pickerOpen) return;
    const handleClick = (e: MouseEvent) => {
      if (pickerContainerRef.current && !pickerContainerRef.current.contains(e.target as Node))
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

  // Sync state to incoming `paragraphs` prop (sync mode): covers chapter navigation
  // in the crawler-fed reader where each page renders with fresh paragraphs.
  useEffect(() => {
    if (paragraphsProp) {
      setChapterState({ status: "ready", paragraphs: paragraphsProp, idx: activeChapterIdx });
    }
  }, [paragraphsProp, activeChapterIdx]);

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
      if (typeof document !== 'undefined' && document.startViewTransition) {
        const transition = document.startViewTransition(() => {
          flushSync(() => {
            setChapterState({ status: "ready", paragraphs: cached.paragraphs, idx: activeChapterIdx });
          });
        });
        transition.ready.catch(() => {});
        transition.finished.catch(() => {});
      } else {
        setChapterState({ status: "ready", paragraphs: cached.paragraphs, idx: activeChapterIdx });
      }
    } else {
      setChapterState({ status: "loading" });
    }

    loadChapterContent(activeChapterContentUrl, controller.signal)
      .then((payload) => {
        if (typeof document !== 'undefined' && document.startViewTransition) {
          const transition = document.startViewTransition(() => {
            flushSync(() => {
              setChapterState({ status: "ready", paragraphs: payload.paragraphs, idx: activeChapterIdx });
            });
          });
          transition.ready.catch(() => {});
          transition.finished.catch(() => {});
        } else {
          setChapterState({ status: "ready", paragraphs: payload.paragraphs, idx: activeChapterIdx });
        }
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : "Unknown error";
        setChapterState({ status: "error", message });
      });

    return () => controller.abort();
  }, [activeChapterContentUrl, retryNonce, activeChapterIdx]);

  // Prefetch prev/next chapter JSON while reading (instant Sau/Trước when cached).
  useEffect(() => {
    const { prev, next } = adjacentChapterContentUrls(slug, chapters, activeChapterIdx);
    if (prev) prefetchChapterContent(prev).catch(() => {});
    if (next) prefetchChapterContent(next).catch(() => {});
  }, [slug, chapters, activeChapterIdx]);

  // paragraphs is non-null only when the loaded content belongs to the active
  // chapter (idx match). This kills the stale-content flash on navigation: during
  // the one render where activeChapterIdx advanced but chapterState still holds the
  // previous chapter, paragraphs is null, so neither display nor TTS prepare runs
  // against stale text.
  const paragraphs =
    chapterState.status === "ready" && chapterState.idx === activeChapterIdx
      ? chapterState.paragraphs
      : null;

  // Content signature in the key defeats stale-paragraph caching in useTTS: on nav,
  // the first render still holds the old paragraphs under the new index, so an
  // index-only key would cache the wrong content and skip rebuild when the real
  // text arrives. The signature forces prepare/play to rebuild with correct text.
  const chapterKey = useMemo(() => {
    const sig = paragraphs
      ? `${paragraphs.length}:${paragraphs[0]?.slice(0, 40)}:${paragraphs[paragraphs.length - 1]?.slice(0, 40)}`
      : "pending";
    return `${slug}:${activeChapterIdx}:${sig}`;
  }, [slug, activeChapterIdx, paragraphs]);

  // Restore scroll only after content renders (otherwise the page is empty).
  useLayoutEffect(() => {
    if (!paragraphs) return;
    const scrollY = getChapterScrollY(loadProgress(slug), activeChapterIdx);
    // instant: skip smooth-scroll CSS animation between chapters
    window.scrollTo({ top: scrollY, left: 0, behavior: "instant" });
    const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
    if (progressRef.current) {
      const pct = maxScroll > 0 ? Math.min(100, (scrollY / maxScroll) * 100) : 0;
      progressRef.current.style.width = `${pct}%`;
    }
    // Sync ref so the scroll-direction detector starts fresh at the new position
    lastScrollY.current = scrollY;
    // Always show header when entering a new chapter
    setIsScrollingDown(false);
    requestAnimationFrame(() => {
      lastScrollY.current = window.scrollY;
      setIsScrollingDown(false);
      overscrollNavigating.current = false;
    });
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

      const maxScroll = document.documentElement.scrollHeight - window.innerHeight;
      const pct = maxScroll > 0 ? Math.min(100, (currentScrollY / maxScroll) * 100) : 0;
      if (progressRef.current) progressRef.current.style.width = `${pct}%`;

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

  // Keep latest values for the keyboard handler without re-binding listeners.
  useEffect(() => {
    latestRef.current = { tts, paragraphs, chapterKey };
  });

  // Index of the paragraph closest to the viewport center (for "Đọc từ đây").
  const centerParagraphIdx = useCallback((count: number): number => {
    const center = window.innerHeight / 2;
    let bestIdx = -1;
    let bestDist = Infinity;
    for (let i = 0; i < count; i++) {
      const el = paragraphRefs.current[i];
      if (!el) continue;
      const rect = el.getBoundingClientRect();
      const dist = Math.abs(rect.top + rect.height / 2 - center);
      if (dist < bestDist) {
        bestDist = dist;
        bestIdx = i;
      }
    }
    return bestIdx;
  }, []);

  const handlePlayFromHere = () => {
    if (!paragraphs) return;
    const idx = centerParagraphIdx(paragraphs.length);
    if (idx < 0) tts.play(chapterKey, paragraphs);
    else tts.playFromParagraph(chapterKey, paragraphs, idx);
  };

  // Auto-follow: keep the speaking paragraph inside the comfortable reading band.
  useEffect(() => {
    if (!tts.activeRange) return;
    const el = paragraphRefs.current[tts.activeRange.start];
    if (!el) return;
    if (Date.now() < followPausedUntilRef.current) return;
    const rect = el.getBoundingClientRect();
    const viewH = window.innerHeight;
    if (rect.top >= viewH * 0.15 && rect.bottom <= viewH * 0.85) return;
    el.scrollIntoView({ block: "center", behavior: "smooth" });
  }, [tts.activeRange]);

  // Respect manual scrolling during playback: pause auto-follow for ~4s.
  useEffect(() => {
    if (!tts.playing) return;
    const pauseFollow = () => {
      followPausedUntilRef.current = Date.now() + 4000;
    };
    window.addEventListener("wheel", pauseFollow, { passive: true });
    window.addEventListener("touchmove", pauseFollow, { passive: true });
    return () => {
      window.removeEventListener("wheel", pauseFollow);
      window.removeEventListener("touchmove", pauseFollow);
    };
  }, [tts.playing]);

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
      const tgt = e.target as HTMLElement | null;
      if (
        tgt &&
        (tgt.tagName === "INPUT" ||
          tgt.tagName === "TEXTAREA" ||
          tgt.isContentEditable)
      ) {
        return;
      }
      if (e.key === "ArrowLeft") {
        navRef.current.goPrev();
      } else if (e.key === "ArrowRight") {
        navRef.current.goNext();
      } else if (e.key === " " || e.code === "Space") {
        e.preventDefault();
        const { tts: t, paragraphs: p, chapterKey: k } = latestRef.current;
        if (t.playing && !t.paused) t.pause();
        else if (t.playing && t.paused) t.resume();
        else if (p) t.play(k, p);
      } else if (e.key === "f" || e.key === "F") {
        const { tts: t, paragraphs: p, chapterKey: k } = latestRef.current;
        if (!p) return;
        const idx = centerParagraphIdx(p.length);
        if (idx < 0) t.play(k, p);
        else t.playFromParagraph(k, p, idx);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [centerParagraphIdx]);

  useEffect(() => {
    const OVERSCROLL_THRESHOLD = 56;
    const EDGE_THRESHOLD = 48;
    const HEADER_HIDE_TOUCH_DELTA = 8;

    const isNearTop = () => window.scrollY <= EDGE_THRESHOLD;
    const isNearBottom = () =>
      window.innerHeight + window.scrollY >=
      document.documentElement.scrollHeight - EDGE_THRESHOLD;

    const handleTouchStart = (e: TouchEvent) => {
      touchStartY.current = e.touches[0].clientY;
      touchEndY.current = e.touches[0].clientY;
      touchedTopDuringGesture.current = isNearTop();
      touchedBottomDuringGesture.current = isNearBottom();
    };

    const handleTouchMove = (e: TouchEvent) => {
      touchEndY.current = e.touches[0].clientY;
      const delta = touchStartY.current - touchEndY.current;
      const atTopNow = isNearTop();
      const atBottomNow = isNearBottom();

      if (atTopNow) touchedTopDuringGesture.current = true;
      if (atBottomNow) touchedBottomDuringGesture.current = true;

      // Mobile fallback: some Android browsers delay/skip scroll direction events
      // right after programmatic chapter navigation.
      if (delta > HEADER_HIDE_TOUCH_DELTA && !atTopNow && !atBottomNow) {
        setIsScrollingDown(true);
      } else if (delta < -HEADER_HIDE_TOUCH_DELTA) {
        setIsScrollingDown(false);
      }

      if (delta > 8 && touchedBottomDuringGesture.current) {
        setOverscrollDir("down");
        setOverscrollDelta(Math.min(delta / OVERSCROLL_THRESHOLD, 1));
      } else if (delta < -8 && touchedTopDuringGesture.current) {
        setOverscrollDir("up");
        setOverscrollDelta(Math.min(Math.abs(delta) / OVERSCROLL_THRESHOLD, 1));
      } else {
        setOverscrollDelta(0);
        setOverscrollDir(null);
      }
    };

    const handleTouchEnd = () => {
      if (!touchStartY.current || !touchEndY.current) return;

      const delta = touchStartY.current - touchEndY.current;

      if (!overscrollNavigating.current && delta > OVERSCROLL_THRESHOLD && touchedBottomDuringGesture.current && hasNext) {
        overscrollNavigating.current = true;
        setChapterFade(true);
        setTimeout(() => { navRef.current.goNext(); setChapterFade(false); }, 120);
      } else if (!overscrollNavigating.current && delta < -OVERSCROLL_THRESHOLD && touchedTopDuringGesture.current && hasPrev) {
        overscrollNavigating.current = true;
        setChapterFade(true);
        setTimeout(() => { navRef.current.goPrev(); setChapterFade(false); }, 120);
      }

      touchStartY.current = 0;
      touchEndY.current = 0;
      touchedTopDuringGesture.current = false;
      touchedBottomDuringGesture.current = false;
      setOverscrollDelta(0);
      setOverscrollDir(null);
    };

    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchmove", handleTouchMove, { passive: true });
    window.addEventListener("touchend", handleTouchEnd);

    return () => {
      window.removeEventListener("touchstart", handleTouchStart);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
    };
  }, [hasNext, hasPrev]);

  return (
    <div className={`reader-shell min-h-dvh overscroll-y-none transition-opacity duration-150 ${chapterFade ? "opacity-0" : "opacity-100"}`} style={shellStyle}>
      {/* Overscroll indicator: top (prev chapter) */}
      {overscrollDir === "up" && (
        <div
          className="fixed top-0 left-0 right-0 z-50 flex flex-col items-center justify-start pt-8 h-32 pointer-events-none transition-opacity"
          style={{ opacity: Math.min(overscrollDelta * 1.5, 1) }}
        >
          <div className={`flex flex-col items-center justify-center transition-transform ${overscrollDelta >= 1 ? 'scale-110' : ''}`}>
            <div className="w-10 h-10 rounded-full bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-center relative overflow-hidden mb-2">
              <CaretUp size={20} weight="bold" className="text-[var(--color-text-muted)] absolute z-10" />
              <div
                className="absolute bottom-0 left-0 right-0 bg-[var(--color-accent)]/20 transition-all duration-75"
                style={{ height: `${Math.min(overscrollDelta * 100, 100)}%` }}
              />
            </div>
            <span className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-accent)]">
              {overscrollDelta >= 1 ? "Thả ra để lùi" : "Kéo thêm..."}
            </span>
          </div>
        </div>
      )}
      {/* Overscroll indicator: bottom (next chapter) */}
      {overscrollDir === "down" && (
        <div
          className="fixed bottom-0 left-0 right-0 z-50 flex flex-col items-center justify-end pb-8 h-32 pointer-events-none transition-opacity"
          style={{ opacity: Math.min(overscrollDelta * 1.5, 1) }}
        >
          <div className={`flex flex-col items-center justify-center transition-transform ${overscrollDelta >= 1 ? 'scale-110' : ''}`}>
            <span className="text-[10px] uppercase tracking-wider font-bold text-[var(--color-accent)] mb-2">
              {overscrollDelta >= 1 ? "Thả ra để sang trang" : "Kéo thêm..."}
            </span>
            <div className="w-10 h-10 rounded-full bg-[var(--color-surface)] border border-[var(--color-border)] flex items-center justify-center relative overflow-hidden">
              <CaretDown size={20} weight="bold" className="text-[var(--color-text-muted)] absolute z-10" />
              <div
                className="absolute top-0 left-0 right-0 bg-[var(--color-accent)]/20 transition-all duration-75"
                style={{ height: `${Math.min(overscrollDelta * 100, 100)}%` }}
              />
            </div>
          </div>
        </div>
      )}
      {/* Chapter scroll progress: fixed top, above header */}
      <div className="fixed top-0 left-0 right-0 h-1 z-50 bg-[var(--color-border)] pointer-events-none">
        <div
          ref={progressRef}
          className="h-full bg-[var(--color-accent)] transition-[width] duration-150 ease-out"
          style={{ width: "0%" }}
        />
      </div>
      <div className={`fixed top-0 left-0 right-0 z-40 bg-[var(--color-surface)] border-b border-[var(--color-border)] smart-header ${isScrollingDown && !pickerOpen ? "-translate-y-full" : "translate-y-0"}`}>
        <div className="max-w-3xl mx-auto px-4 md:px-6 py-4">
          <div className="flex items-start justify-between gap-4">
            <div className="flex-1">
              <p className="text-[10px] md:text-xs reader-accent opacity-80 font-bold tracking-widest uppercase mb-1 break-words leading-snug">{storyTitle}</p>
              <h1 className="text-lg md:text-xl font-extrabold break-words leading-snug">{activeTitle}</h1>
            </div>
            <Link
              href={backHref ?? `/story/${slug}`}
              aria-label="Đóng và quay lại danh sách"
              className="shrink-0 w-9 h-9 rounded-full bg-black/20 border border-white/5 flex items-center justify-center hover:bg-black/40 active:scale-90 transition-all duration-200"
            >
              <X size={16} />
            </Link>
          </div>
          <div className="mt-3 relative" ref={pickerContainerRef}>
            <button
              onClick={() => { setPickerOpen((o) => !o); setFilter(""); setPickerExtraBefore(0); setPickerExtraAfter(0); }}
              className="text-xs font-medium px-3 py-1.5 rounded-full bg-black/20 border border-white/5 hover:bg-white/10 transition-colors flex items-center justify-between gap-1 cursor-pointer w-full"
            >
              <span>Chương {activeChapterIdx + 1} / {totalChapters}</span>
              <CaretDown size={14} className={`transition-transform duration-200 ${pickerOpen ? "rotate-180" : ""}`} />
            </button>
            {pickerOpen && (
              <>
                <div className="fixed inset-0 top-16 bg-black/50 backdrop-blur-sm z-40" onClick={() => setPickerOpen(false)} />
                <div ref={pickerRef} className="absolute top-full left-0 right-0 mt-2 rounded-2xl max-h-[60vh] flex flex-col z-50 overflow-hidden shadow-2xl bg-[var(--color-surface)] border border-[var(--color-border)]">
                  <div className="relative p-3 border-b border-white/5">
                    <MagnifyingGlass size={16} className="absolute left-6 top-1/2 -translate-y-1/2 opacity-40" />
                    <input
                      autoFocus
                      type="text"
                      placeholder="Tìm chương..."
                      value={filter}
                      onChange={(e) => { setFilter(e.target.value); setPickerExtraBefore(0); setPickerExtraAfter(0); }}
                      className="pl-9 pr-4 py-2.5 text-sm rounded-lg bg-black/20 border border-white/5 outline-none w-full placeholder-white/40 focus:border-[var(--color-accent)]/50 transition-colors"
                    />
                  </div>
                <div 
                  className="overflow-y-auto flex-1 scrollbar-hide"
                  style={{
                    maskImage: "linear-gradient(to bottom, transparent 0%, black 5%, black 95%, transparent 100%)",
                    WebkitMaskImage: "linear-gradient(to bottom, transparent 0%, black 5%, black 95%, transparent 100%)"
                  }}
                  onScroll={(e) => {
                    const el = e.currentTarget;
                    if (el.scrollTop <= 10 && pickerList.hasMoreBefore) {
                      setPickerExtraBefore((x) => x + PICKER_LOAD_STEP);
                    }
                    if (el.scrollHeight - el.scrollTop - el.clientHeight <= 10 && pickerList.hasMoreAfter) {
                      setPickerExtraAfter((x) => x + PICKER_LOAD_STEP);
                    }
                  }}
                >
                  {pickerList.hasMoreBefore && (
                    <div className="py-2 flex items-center justify-center gap-1.5 text-xs text-white/40 italic">
                      <CircleNotch size={14} className="animate-spin" />
                      Đang tải thêm...
                    </div>
                  )}
                  {pickerList.items.map((ch) => (
                    <a
                      key={ch.index}
                      href={href(ch.index)}
                      onClick={(e) => {
                        e.preventDefault();
                        setPickerOpen(false);
                        navigateToChapter(ch.index);
                      }}
                      data-active-chapter={ch.index === activeChapterIdx ? "true" : "false"}
                      className={`block px-4 py-3 text-sm truncate hover:bg-white/10 transition-colors cursor-pointer ${
                        ch.index === activeChapterIdx
                          ? "text-[var(--color-accent)] font-medium bg-[var(--color-accent)]/10"
                          : ""
                      }`}
                    >
                      {ch.title}
                    </a>
                  ))}
                  {pickerList.hasMoreAfter && (
                    <div className="py-2 flex items-center justify-center gap-1.5 text-xs text-white/40 italic">
                      <CircleNotch size={14} className="animate-spin" />
                      Đang tải thêm...
                    </div>
                  )}
                  {pickerList.items.length === 0 && (
                    <p className="px-4 py-6 text-sm text-[var(--color-text-muted)] text-center italic">
                      Không tìm thấy
                    </p>
                  )}
                </div>
              </div>
              </>
            )}
          </div>
        </div>
      </div>

      <main className="max-w-3xl mx-auto px-4 md:px-6 pt-48 md:pt-36 pb-40 reader-content relative">

        {chapterState.status === "loading" && (
          <div className="space-y-3" aria-busy="true">
            {Array.from({ length: 6 }).map((_, i) => (
              <div
                key={i}
                className="h-4 rounded reader-surface animate-shimmer"
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

        {paragraphs && (
          <div className="space-y-0 animate-fade-in">
            {paragraphs.map((p, i) => (
              <p
                key={i}
                ref={(el) => {
                  if (el) paragraphRefs.current[i] = el;
                }}
                className={`reader-paragraph ${i === 0 ? "drop-cap" : ""} ${
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

        <div className="flex justify-between items-center mt-12 pt-8 border-t reader-border">
          <button
            onClick={goPrev}
            disabled={!hasPrev}
            aria-label="Chương trước"
            className="btn-spring px-5 py-3 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] disabled:opacity-30 disabled:active:scale-100 hover:bg-white/5 transition-colors font-medium flex items-center gap-2 group"
          >
            <CaretLeft size={16} className="group-hover:-translate-x-0.5 transition-transform duration-200" /> Trước
          </button>
          <button
            onClick={goNext}
            disabled={!hasNext}
            aria-label="Chương sau"
            className="btn-spring px-5 py-3 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] disabled:opacity-30 disabled:active:scale-100 hover:bg-white/5 transition-colors font-medium flex items-center gap-2 group"
          >
            Sau <CaretRight size={16} className="group-hover:translate-x-0.5 transition-transform" />
          </button>
        </div>

        {hasNext && (
          <div className="text-center mt-16 pb-8 opacity-50 reader-muted text-sm flex flex-col items-center gap-2">
            <CaretDown size={14} />
            <span>Kéo lên để sang chương sau</span>
          </div>
        )}
      </main>

      <Player
        hidden={isScrollingDown && !tts.playing}
        playing={tts.playing}
        paused={tts.paused}
        loading={tts.loading}
        rate={tts.rate}
        currentIdx={tts.currentIdx}
        totalParagraphs={paragraphs?.length ?? 0}
        viVoices={tts.viVoices}
        selectedVoiceName={tts.selectedVoiceName}
        onPlay={() => paragraphs && tts.play(chapterKey, paragraphs)}
        onPlayFromHere={handlePlayFromHere}
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
