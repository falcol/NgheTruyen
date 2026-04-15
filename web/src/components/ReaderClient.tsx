"use client";

import { useCallback, useEffect, useMemo, useRef } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { useProgress } from "@/hooks/useProgress";
import { useTTS } from "@/hooks/useTTS";
import Player from "@/components/Player";

export default function ReaderClient({
  slug,
  storyTitle,
  chapterIdx,
  totalChapters,
  title,
  paragraphs,
}: {
  slug: string;
  storyTitle: string;
  chapterIdx: number;
  totalChapters: number;
  title: string;
  paragraphs: string[];
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

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") goPrev();
      if (e.key === "ArrowRight") goNext();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [goNext, goPrev]);

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
          <p className="text-sm text-(--color-text-muted)">
            Chương {chapterIdx + 1} / {totalChapters}
          </p>
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
        onRateChange={tts.setRate}
      />
    </>
  );
}
