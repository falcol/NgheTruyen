"use client";

import { useState, useEffect, useCallback } from "react";

export interface ReadingProgress {
  chapterIdx: number;
  scrollByChapter: Record<string, number>;
  timestamp: number;
}

function progressKey(slug: string) {
  return `progress-${slug}`;
}

export function loadProgress(slug: string): ReadingProgress | null {
  if (typeof window === "undefined") return null;
  try {
    const saved = localStorage.getItem(progressKey(slug));
    if (!saved) return null;
    return parseProgress(JSON.parse(saved));
  } catch {
    return null;
  }
}

/** Supports legacy `{ chapterIdx, scrollY? }` payloads. */
export function parseProgress(raw: unknown): ReadingProgress | null {
  if (!raw || typeof raw !== "object") return null;
  const o = raw as Record<string, unknown>;
  if (typeof o.chapterIdx !== "number") return null;

  const scrollByChapter: Record<string, number> = {};
  if (o.scrollByChapter && typeof o.scrollByChapter === "object") {
    for (const [k, v] of Object.entries(o.scrollByChapter as Record<string, unknown>)) {
      if (typeof v === "number" && v >= 0) scrollByChapter[k] = v;
    }
  } else if (typeof o.scrollY === "number" && o.scrollY > 0) {
    scrollByChapter[String(o.chapterIdx)] = o.scrollY;
  }

  return {
    chapterIdx: o.chapterIdx,
    scrollByChapter,
    timestamp: typeof o.timestamp === "number" ? o.timestamp : Date.now(),
  };
}

export function getChapterScrollY(
  progress: ReadingProgress | null,
  chapterIdx: number,
): number {
  if (!progress) return 0;
  return progress.scrollByChapter[String(chapterIdx)] ?? 0;
}

export function useProgress(slug: string) {
  const key = progressKey(slug);
  const [progress, setProgress] = useState<ReadingProgress | null>(null);

  useEffect(() => {
    setProgress(loadProgress(slug));
  }, [slug]);

  const saveChapter = useCallback(
    (chapterIdx: number) => {
      setProgress((prev) => {
        const next: ReadingProgress = {
          chapterIdx,
          scrollByChapter: prev?.scrollByChapter ?? {},
          timestamp: Date.now(),
        };
        localStorage.setItem(key, JSON.stringify(next));
        return next;
      });
    },
    [key],
  );

  const saveScroll = useCallback(
    (chapterIdx: number, scrollY: number) => {
      setProgress((prev) => {
        const next: ReadingProgress = {
          chapterIdx,
          scrollByChapter: {
            ...(prev?.scrollByChapter ?? {}),
            [String(chapterIdx)]: Math.max(0, Math.round(scrollY)),
          },
          timestamp: Date.now(),
        };
        localStorage.setItem(key, JSON.stringify(next));
        return next;
      });
    },
    [key],
  );

  return { progress, saveChapter, saveScroll };
}
