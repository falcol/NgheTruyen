"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { loadProgress } from "@/hooks/useProgress";
import { getGradientFromString } from "@/lib/color";
import { Play } from "@/components/icons";

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
    // eslint-disable-next-line react-hooks/set-state-in-effect -- derives from localStorage post-mount to avoid SSR hydration mismatch
    setItems(result.slice(0, 6));
  }, [stories]);

  if (items.length === 0) return null;

  return (
    <section className="mb-12">
      <div className="ornament-divider mb-6">
        <span className="flex items-center gap-2">
          <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] candle-glow" />
          <span
            style={{ fontFamily: "var(--font-ui-serif)" }}
            className="text-[11px] font-semibold text-[var(--color-text-muted)] tracking-[0.25em]"
          >
            Tiếp Tục Đọc
          </span>
        </span>
      </div>

      <div className="flex gap-4 overflow-x-auto pb-4 -mx-1 px-1 snap-x snap-mandatory scrollbar-hide scroll-px-1">
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
              <div className="relative aspect-[2/3] rounded-2xl overflow-hidden border border-[var(--color-border)] group-hover:border-[var(--color-accent)]/40 transition-all duration-200 group-hover:-translate-y-1 mb-2.5">
                {/* Gradient bg */}
                <div className={`absolute inset-0 bg-gradient-to-br ${gradient}`} />
                <div className="absolute inset-0 bg-black/25 group-hover:bg-black/10 transition-colors duration-200" />

                {/* Title */}
                <div className="relative z-20 h-full flex flex-col p-3">
                  <div className="flex-1 flex items-center justify-center">
                    <p
                      style={{ fontFamily: "var(--font-ui-serif)" }}
                      className="font-bold text-center text-white/95 drop-shadow-[0_2px_6px_rgba(0,0,0,0.9)] text-sm leading-snug line-clamp-4 px-1"
                    >
                      {item.title}
                    </p>
                  </div>
                </div>

                {/* Progress bar */}
                <div className="absolute bottom-0 left-0 right-0 h-[3px] bg-black/50 z-30">
                  <div
                    className="h-full bg-[var(--color-accent)]"
                    style={{ width: `${item.pct}%` }}
                  />
                </div>

                {/* Play button overlay on hover */}
                <div className="absolute inset-0 z-30 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-300">
                  <div className="w-12 h-12 rounded-full bg-black/40 backdrop-blur-xl flex items-center justify-center border border-white/20 shadow-[0_0_16px_rgba(0,0,0,0.5)] transform scale-90 group-hover:scale-100 transition-transform duration-300">
                    <Play weight="fill" size={20} className="text-white translate-x-[2px]" />
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
                <div className="mt-1.5 h-[3px] rounded-full bg-[var(--color-border)] overflow-hidden">
                  <div
                    className="h-full rounded-full bg-[var(--color-accent)] transition-all duration-300 group-hover:shadow-[0_0_8px_var(--color-accent)]"
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
