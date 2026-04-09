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
