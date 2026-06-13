"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { loadProgress } from "@/hooks/useProgress";
import { getGradientFromString } from "@/lib/color";

export interface StoryMeta {
  slug: string;
  title: string;
  totalChapters: number;
  /** href prefix, e.g. "/read/slug" or "/epub/file/read" */
  readHref: string;
  /** href to detail page */
  detailHref: string;
}

interface RecentItem extends StoryMeta {
  chapterIdx: number;
  chapterTitle?: string;
  timestamp: number;
  pct: number;
}

function timeAgo(ts: number): string {
  const diffMs = Date.now() - ts;
  const diffMin = Math.floor(diffMs / 60_000);
  if (diffMin < 1) return "vừa xong";
  if (diffMin < 60) return `${diffMin} phút trước`;
  const diffH = Math.floor(diffMin / 60);
  if (diffH < 24) return `${diffH} giờ trước`;
  const diffD = Math.floor(diffH / 24);
  if (diffD < 7) return `${diffD} ngày trước`;
  return `${Math.floor(diffD / 7)} tuần trước`;
}

export default function ContinueReadingSection({
  stories,
}: {
  stories: StoryMeta[];
}) {
  const [items, setItems] = useState<RecentItem[]>([]);

  useEffect(() => {
    const result: RecentItem[] = [];
    for (const s of stories) {
      const p = loadProgress(s.slug);
      if (!p) continue;
      const pct =
        s.totalChapters > 0
          ? Math.min(100, Math.round(((p.chapterIdx + 1) / s.totalChapters) * 100))
          : 0;
      result.push({
        ...s,
        chapterIdx: p.chapterIdx,
        timestamp: p.timestamp,
        pct,
      });
    }
    // Sort most recently read first
    result.sort((a, b) => b.timestamp - a.timestamp);
    setItems(result.slice(0, 6));
  }, [stories]);

  if (items.length === 0) return null;

  return (
    <section className="mb-12">
      <h2 className="text-base font-bold text-[var(--color-text-muted)] uppercase tracking-widest mb-5 flex items-center gap-3">
        <span className="w-5 h-[2px] bg-[var(--color-accent)] rounded-full inline-block" />
        Tiếp tục đọc
      </h2>

      <div className="flex gap-4 overflow-x-auto pb-3 -mx-1 px-1 snap-x snap-mandatory scrollbar-hide">
        {items.map((item) => {
          const gradient = getGradientFromString(item.slug);
          const resumeHref = `${item.readHref}/${item.chapterIdx}`;

          return (
            <Link
              key={item.slug}
              href={resumeHref}
              className="group snap-start shrink-0 w-36 sm:w-40 md:w-44 block"
            >
              {/* Book cover */}
              <div className="relative aspect-[2/3] rounded-xl overflow-hidden glass-panel shadow-[0_8px_24px_rgba(0,0,0,0.5)] group-hover:shadow-[0_12px_32px_rgba(56,189,248,0.2)] transition-all duration-400 group-hover:-translate-y-1.5 mb-2.5">
                {/* Gradient bg */}
                <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-90 group-hover:opacity-100 transition-opacity duration-400`} />
                <div className="absolute inset-0 bg-black/30 group-hover:bg-black/10 transition-colors duration-400" />

                {/* Book spine */}
                <div className="absolute left-0 top-0 bottom-0 w-3 bg-gradient-to-r from-white/20 to-transparent z-10 pointer-events-none" />
                <div className="absolute left-0 top-0 bottom-0 w-[1px] bg-white/40 z-10 pointer-events-none" />

                {/* Title */}
                <div className="relative z-20 h-full flex flex-col p-3">
                  <div className="flex-1 flex items-center justify-center">
                    <p className="font-serif font-bold text-center text-white/95 drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)] text-sm leading-snug line-clamp-4">
                      {item.title}
                    </p>
                  </div>
                </div>

                {/* Progress bar */}
                <div className="absolute bottom-0 left-0 right-0 h-1 bg-black/50 z-30">
                  <div
                    className="h-full bg-gradient-to-r from-[var(--color-accent)] to-purple-400"
                    style={{ width: `${item.pct}%` }}
                  />
                </div>

                {/* Play button overlay on hover */}
                <div className="absolute inset-0 z-30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                  <div className="w-10 h-10 rounded-full bg-black/50 backdrop-blur-md flex items-center justify-center border border-white/20">
                    <span className="text-white text-sm translate-x-[1px]">▶</span>
                  </div>
                </div>
              </div>

              {/* Meta below card */}
              <div className="px-0.5">
                <p className="text-xs font-semibold text-white/80 truncate leading-tight mb-1">
                  {item.title}
                </p>
                <div className="flex items-center justify-between">
                  <span className="text-[10px] text-[var(--color-accent)] font-bold">
                    CH {item.chapterIdx + 1}
                    {item.totalChapters > 0 && (
                      <span className="text-[var(--color-text-muted)] font-normal">
                        /{item.totalChapters}
                      </span>
                    )}
                  </span>
                  <span className="text-[10px] text-[var(--color-text-muted)]">
                    {timeAgo(item.timestamp)}
                  </span>
                </div>

                {/* Thin progress track */}
                <div className="mt-1.5 h-0.5 rounded-full bg-white/10 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-[var(--color-accent)] to-purple-400 transition-all"
                    style={{ width: `${item.pct}%` }}
                  />
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}
