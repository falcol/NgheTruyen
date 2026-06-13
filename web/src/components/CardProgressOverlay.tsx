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
    if (p) setChapterIdx(p.chapterIdx);
  }, [slug]);

  if (chapterIdx === null || totalChapters === 0) return null;

  const pct = Math.min(100, Math.round(((chapterIdx + 1) / totalChapters) * 100));

  return (
    <>
      {/* Progress bar at bottom */}
      <div className="absolute bottom-0 left-0 right-0 h-1 bg-black/40 z-30 pointer-events-none">
        <div
          className="h-full bg-gradient-to-r from-[var(--color-accent)] to-purple-400 transition-all duration-500"
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* Chapter badge top-right */}
      <div className="absolute top-2 right-2 z-30 pointer-events-none">
        <span className="bg-black/60 backdrop-blur-md text-[var(--color-accent)] text-[9px] font-bold px-2 py-0.5 rounded-full border border-[var(--color-accent)]/30 shadow-[0_0_8px_rgba(56,189,248,0.2)]">
          CH {chapterIdx + 1}
        </span>
      </div>
    </>
  );
}
