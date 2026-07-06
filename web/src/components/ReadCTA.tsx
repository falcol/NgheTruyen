"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { loadProgress } from "@/hooks/useProgress";
import { Play } from "@/components/icons";

interface ReadCTAProps {
  slug: string;
  totalChapters: number;
  chaptersInfo: { index: number; title: string }[];
  /** Base href before chapterIdx, e.g. "/read/slug" or "/epub/file/read" */
  readHrefBase: string;
}

export default function ReadCTA({ slug, totalChapters, chaptersInfo, readHrefBase }: ReadCTAProps) {
  const [chapterIdx, setChapterIdx] = useState<number | null>(null);

  useEffect(() => {
    const p = loadProgress(slug);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage read must run post-mount to avoid SSR hydration mismatch
    if (p) setChapterIdx(p.chapterIdx);
  }, [slug]);

  const hasProgress = chapterIdx !== null && chapterIdx > 0;
  const href = hasProgress ? `${readHrefBase}/${chapterIdx}` : `${readHrefBase}/0`;
  const chapterTitle = hasProgress
    ? (chaptersInfo.find((c) => c.index === chapterIdx)?.title ?? `Chương ${chapterIdx! + 1}`)
    : null;
  const pct = hasProgress && totalChapters > 0
    ? Math.round(((chapterIdx! + 1) / totalChapters) * 100)
    : 0;

  return (
    <div className="flex flex-col items-center md:items-start gap-2">
      <Link
        href={href}
        className="inline-flex items-center gap-3 px-8 py-4 bg-[var(--color-accent)] text-[var(--color-bg)] font-bold rounded-xl hover:bg-[var(--color-accent-strong)] hover:-translate-y-0.5 active:scale-[0.98] transition-all duration-200 text-lg"
      >
        <Play weight="fill" size={20} />
        {hasProgress ? "Đọc Tiếp" : "Đọc Từ Đầu"}
      </Link>
      {hasProgress && chapterTitle && (
        <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <div className="w-24 h-[3px] rounded-full bg-[var(--color-border)] overflow-hidden">
            <div className="h-full bg-[var(--color-accent)]" style={{ width: `${pct}%` }} />
          </div>
          <span className="truncate max-w-[220px]" title={chapterTitle}>{chapterTitle}</span>
          <span>·</span>
          <span>{pct}%</span>
        </div>
      )}
    </div>
  );
}
