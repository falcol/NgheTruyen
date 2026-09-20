import type { ChapterMeta } from "@/lib/data";

export const CHAPTER_LIST_PAGE = 80;

const PRINTED_CHAPTER_RE = /chương\s*(\d+)/i;

export function printedChapterNumber(title: string): number | null {
  const match = title.match(PRINTED_CHAPTER_RE);
  if (!match) return null;
  return Number(match[1]);
}

export function filterChapters(
  chapters: ChapterMeta[],
  query: string,
): ChapterMeta[] {
  const q = query.trim().toLowerCase();
  if (!q) return chapters;
  if (/^\d+$/.test(q)) {
    const n = Number(q);
    return chapters.filter((ch) => printedChapterNumber(ch.title) === n);
  }
  return chapters.filter((ch) => ch.title.toLowerCase().includes(q));
}

export function visibleChapterWindow(
  filtered: ChapterMeta[],
  start: number,
  visibleCount: number,
): { items: ChapterMeta[]; hasMoreBefore: boolean; hasMoreAfter: boolean } {
  const s = Math.max(0, start);
  const count = Math.max(0, visibleCount);
  return {
    items: filtered.slice(s, s + count),
    hasMoreBefore: s > 0,
    hasMoreAfter: s + count < filtered.length,
  };
}

export function windowRangeForJump(
  chapters: ChapterMeta[],
  chapterIdx: number,
  page = CHAPTER_LIST_PAGE,
): { start: number; count: number } {
  const pos = chapters.findIndex((ch) => ch.index === chapterIdx);
  if (pos < 0) return { start: 0, count: page };
  const half = Math.floor(page / 2);
  const start = Math.min(
    Math.max(0, pos - half),
    Math.max(0, chapters.length - page),
  );
  return { start, count: page };
}
