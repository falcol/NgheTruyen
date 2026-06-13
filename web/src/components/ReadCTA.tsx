"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { loadProgress } from "@/hooks/useProgress";

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
        className="inline-flex items-center gap-3 px-8 py-4 bg-white text-black font-bold rounded-2xl hover:scale-105 transition-all shadow-[0_0_30px_rgba(255,255,255,0.3)] hover:shadow-[0_0_40px_rgba(255,255,255,0.5)] text-lg"
      >
        <span>▶</span>
        {hasProgress ? "Đọc Tiếp" : "Đọc Từ Đầu"}
      </Link>
      {hasProgress && chapterTitle && (
        <div className="flex items-center gap-2 text-xs text-[var(--color-text-muted)]">
          <div className="w-24 h-0.5 rounded-full bg-white/10 overflow-hidden">
            <div className="h-full bg-gradient-to-r from-[var(--color-accent)] to-purple-400" style={{ width: `${pct}%` }} />
          </div>
          <span className="truncate max-w-[160px]" title={chapterTitle}>{chapterTitle}</span>
          <span>·</span>
          <span>{pct}%</span>
        </div>
      )}
    </div>
  );
}
