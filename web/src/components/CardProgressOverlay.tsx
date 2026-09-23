"use client";

import { useEffect, useState } from "react";
import { loadProgress } from "@/hooks/useProgress";

interface CardProgressOverlayProps {
  slug: string;
  totalChapters: number;
}

export default function CardProgressOverlay({
  slug,
  totalChapters,
}: CardProgressOverlayProps) {
  const [chapterIdx, setChapterIdx] = useState<number | null>(null);

  useEffect(() => {
    const p = loadProgress(slug);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage read must run post-mount to avoid SSR hydration mismatch
    if (p) setChapterIdx(p.chapterIdx);
  }, [slug]);

  if (chapterIdx === null || totalChapters === 0) return null;

  const pct = Math.min(100, Math.round(((chapterIdx + 1) / totalChapters) * 100));

  return (
    <>
      {/* Progress bar at bottom — floating rounded strip */}
      <div className="absolute bottom-0 left-0 right-0 h-[4px] bg-black/50 z-30 pointer-events-none">
        <div
          className="h-full bg-[var(--color-accent)] transition-all duration-500 shadow-[0_0_6px_var(--color-accent)]"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Chapter badge — floating pill, top-right */}
      <div className="absolute top-2 right-2 z-30 pointer-events-none">
        <span className="inline-flex items-center gap-0.5 bg-black/70 backdrop-blur-xl text-[var(--color-accent)] text-[10px] font-bold px-2 py-0.5 rounded-full border border-[var(--color-accent)]/40 shadow-[0_0_8px_rgba(0,0,0,0.4)]">
          CH {chapterIdx + 1}
          {totalChapters > 0 && (
            <span className="text-white/40 font-normal">/{totalChapters}</span>
          )}
        </span>
      </div>
    </>
  );
}
