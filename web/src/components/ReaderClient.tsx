"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
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

interface ChapterPayload {
  index: number;
  title: string;
  paragraphs: string[];
}

type ChapterState =
  | { status: "loading" }
  | { status: "ready"; paragraphs: string[] }
  | { status: "error"; message: string };

// Browser-side gunzip — keeps dev/prod identical regardless of Content-Encoding header.
async function fetchChapterContent(
  url: string,
  signal: AbortSignal,
): Promise<ChapterPayload> {
  const res = await fetch(url, { signal });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  if (!res.body) throw new Error("Empty response body");

  const decompressed = res.body.pipeThrough(new DecompressionStream("gzip"));
  const text = await new Response(decompressed).text();
  return JSON.parse(text) as ChapterPayload;
}

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
  const chapterKey = useMemo(() => `${slug}:${chapterIdx}`, [slug, chapterIdx]);

  const [chapterState, setChapterState] = useState<ChapterState>(() =>
    paragraphsProp
      ? { status: "ready", paragraphs: paragraphsProp }
      : { status: "loading" },
  );
  const [retryNonce, setRetryNonce] = useState(0);

  const href = (idx: number) =>
    readHref ? `${readHref}/${idx}` : `/read/${slug}/${idx}`;

  const prevHref = useMemo(
    () => href(chapterIdx - 1),
    [chapterIdx, slug, readHref],
  );
  const nextHref = useMemo(
    () => href(chapterIdx + 1),
    [chapterIdx, slug, readHref],
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
    if (typeof history !== "undefined") {
      history.scrollRestoration = "manual";
    }
  }, []);

  useEffect(() => {
    saveChapter(chapterIdx);
  }, [chapterIdx, saveChapter]);

  // Sync state to incoming `paragraphs` prop (sync mode) — covers chapter navigation
  // in the crawler-fed reader where each page renders with fresh paragraphs.
  useEffect(() => {
    if (paragraphsProp) {
      setChapterState({ status: "ready", paragraphs: paragraphsProp });
    }
  }, [paragraphsProp]);

  // Fetch chapter content (async mode) whenever URL changes or user retries.
  useEffect(() => {
    if (!chapterContentUrl) return;
    const controller = new AbortController();
    setChapterState({ status: "loading" });

    fetchChapterContent(chapterContentUrl, controller.signal)
      .then((payload) => {
        setChapterState({ status: "ready", paragraphs: payload.paragraphs });
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        const message = err instanceof Error ? err.message : "Unknown error";
        setChapterState({ status: "error", message });
      });

    return () => controller.abort();
  }, [chapterContentUrl, retryNonce]);

  const paragraphs = chapterState.status === "ready" ? chapterState.paragraphs : null;

  // Restore scroll only after content renders (otherwise the page is empty).
  useLayoutEffect(() => {
    if (!paragraphs) return;
    const scrollY = getChapterScrollY(loadProgress(slug), chapterIdx);
    window.scrollTo({ top: scrollY, left: 0 });
  }, [slug, chapterIdx, paragraphs]);

  useEffect(() => {
    const flushScroll = () => {
      if (scrollSaveTimer.current) {
        clearTimeout(scrollSaveTimer.current);
        scrollSaveTimer.current = null;
      }
      saveScroll(chapterIdx, window.scrollY);
    };

    const onScroll = () => {
      if (scrollSaveTimer.current) clearTimeout(scrollSaveTimer.current);
      scrollSaveTimer.current = setTimeout(
        () => saveScroll(chapterIdx, window.scrollY),
        200,
      );
    };

    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("pagehide", flushScroll);
    return () => {
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("pagehide", flushScroll);
      flushScroll();
    };
  }, [chapterIdx, saveScroll]);

  useEffect(() => {
    if (paragraphs) prepare(chapterKey, paragraphs);
  }, [chapterKey, paragraphs, prepare]);

  useEffect(() => {
    setOnChapterComplete(() => {
      if (chapterIdx < totalChapters - 1) {
        router.push(nextHref);
      }
    });
  }, [chapterIdx, totalChapters, nextHref, router, setOnChapterComplete]);

  const hasPrev = chapterIdx > 0;
  const hasNext = chapterIdx < totalChapters - 1;

  const goNext = useCallback(() => {
    if (hasNext) router.push(nextHref);
  }, [hasNext, nextHref, router]);

  const goPrev = useCallback(() => {
    if (hasPrev) router.push(prevHref);
  }, [hasPrev, prevHref, router]);

  const navRef = useRef({ goNext, goPrev });
  useEffect(() => {
    navRef.current = { goNext, goPrev };
  });

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

  return (
    <div className="reader-shell min-h-dvh" style={shellStyle}>
      <main className="max-w-3xl mx-auto px-6 py-6 pb-32 reader-content">
        <div ref={topRef} />

        <div className="mb-6">
          <Link
            href={backHref ?? `/story/${slug}`}
            className="text-sm reader-muted"
          >
            ← Danh sách chương
          </Link>
          <p className="text-sm reader-muted mt-2">{storyTitle}</p>
          <h1 className="text-xl font-bold mt-2">{title}</h1>
          <div className="flex items-center gap-2 mt-2">
            <button
              onClick={() => { setPickerOpen((o) => !o); setFilter(""); }}
              className="text-sm reader-accent hover:underline cursor-pointer"
            >
              Chương {chapterIdx + 1} / {totalChapters} ▾
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
                  <Link
                    key={ch.index}
                    href={href(ch.index)}
                    onClick={() => setPickerOpen(false)}
                    className={`block px-3 py-2 text-sm truncate hover:bg-[var(--color-surface)] ${
                      ch.index === chapterIdx
                        ? "text-[var(--color-accent)] font-medium"
                        : ""
                    }`}
                  >
                    {ch.title}
                  </Link>
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
