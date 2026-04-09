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

  useEffect(() => {
    save(chapterIdx);
  }, [chapterIdx, save]);

  useEffect(() => {
    topRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chapterIdx]);

  useEffect(() => {
    return () => {
      if (typeof window !== "undefined" && window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    };
  }, []);

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
      <main className="max-w-3xl mx-auto px-6 py-6 pb-32">
        <div ref={topRef} />

        <div className="mb-6">
          <Link
            href={`/story/${slug}`}
            className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-accent)]"
          >
            ← Danh s\u00E1ch ch\u01B0\u01A1ng
          </Link>
          <h1 className="text-xl font-bold mt-2">{title}</h1>
          <p className="text-sm text-[var(--color-text-muted)]">
            Ch\u01B0\u01A1ng {chapterIdx + 1} / {totalChapters}
          </p>
        </div>

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

        <div className="flex justify-between items-center mt-8 pt-4 border-t border-[var(--color-surface)]">
          <button
            onClick={goPrev}
            disabled={!hasPrev}
            className="px-4 py-2 rounded-lg bg-[var(--color-surface)] disabled:opacity-30 hover:bg-[var(--color-surface)]/80"
          >
            ← Tr\u01B0\u1EDBc
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
