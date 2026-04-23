"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useProgress } from "@/hooks/useProgress";
import { useTTS } from "@/hooks/useTTS";
import Player from "@/components/Player";

interface ChapterMeta {
  index: number;
  title: string;
}

export default function ReaderClient({
  slug,
  storyTitle,
  chapterIdx,
  totalChapters,
  title,
  paragraphs,
  chapters,
}: {
  slug: string;
  storyTitle: string;
  chapterIdx: number;
  totalChapters: number;
  title: string;
  paragraphs: string[];
  chapters: ChapterMeta[];
}) {
  const router = useRouter();
  const { save } = useProgress(slug);
  const topRef = useRef<HTMLDivElement>(null);
  const tts = useTTS();
  const chapterKey = useMemo(() => `${slug}:${chapterIdx}`, [slug, chapterIdx]);
  const prevHref = useMemo(
    () => `/read/${slug}/${chapterIdx - 1}`,
    [chapterIdx, slug],
  );
  const nextHref = useMemo(
    () => `/read/${slug}/${chapterIdx + 1}`,
    [chapterIdx, slug],
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
    save(chapterIdx);
  }, [chapterIdx, save]);

  useEffect(() => {
    topRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chapterIdx]);

  useEffect(() => {
    tts.setOnChapterComplete(() => {
      if (chapterIdx < totalChapters - 1) {
        router.push(nextHref);
      }
    });
  }, [chapterIdx, totalChapters, nextHref, router, tts.setOnChapterComplete]);

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

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") navRef.current.goPrev();
      if (e.key === "ArrowRight") navRef.current.goNext();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <>
      <main className="max-w-3xl mx-auto px-6 py-6 pb-32">
        <div ref={topRef} />

        <div className="mb-6">
          <Link
            href={`/story/${slug}`}
            className="text-sm text-(--color-text-muted) hover:text-(--color-accent)"
          >
            ← Danh sách chương
          </Link>
          <p className="text-sm text-(--color-text-muted) mt-2">{storyTitle}</p>
          <h1 className="text-xl font-bold mt-2">{title}</h1>
          <div className="flex items-center gap-2 mt-2">
            <button
              onClick={() => { setPickerOpen((o) => !o); setFilter(""); }}
              className="text-sm text-(--color-accent) hover:underline cursor-pointer"
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
                    href={`/read/${slug}/${ch.index}`}
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

        <div className="space-y-0">
          {paragraphs.map((p, i) => (
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

        <div className="flex justify-between items-center mt-8 pt-4 border-t border-(--color-surface)">
          <button
            onClick={goPrev}
            disabled={!hasPrev}
            className="px-4 py-2 rounded-lg bg-(--color-surface) disabled:opacity-30 hover:bg-(--color-surface)/80"
          >
            ← Trước
          </button>
          <button
            onClick={goNext}
            disabled={!hasNext}
            className="px-4 py-2 rounded-lg bg-(--color-surface) disabled:opacity-30 hover:bg-(--color-surface)/80"
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
        totalParagraphs={paragraphs.length}
        onPlay={() => tts.play(chapterKey, paragraphs)}
        onPause={tts.pause}
        onResume={tts.resume}
        onStop={tts.stop}
        onSkipForward={tts.skipForward}
        onSkipBackward={tts.skipBackward}
        onRateChange={tts.setRate}
      />
    </>
  );
}
