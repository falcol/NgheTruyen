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
          Tiếp tục đọc: {chapters.find((ch) => ch.index === progress.chapterIdx)?.title || `Chương ${progress.chapterIdx + 1}`}
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
