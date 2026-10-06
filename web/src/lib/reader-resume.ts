import { getChapterScrollY, loadProgress } from "@/hooks/useProgress";
import { getCachedChapter } from "@/lib/chapter-prefetch";

/**
 * Synchronous resume for the open chapter. Scroll is returned only together
 * with stored paragraphs, so a loading shell never receives a stale offset.
 */
export function resumeReaderChapter(
  slug: string,
  chapterIdx: number,
  url: string,
): { paragraphs: string[] | null; scrollY: number } {
  const cached = getCachedChapter(url);
  if (!cached) return { paragraphs: null, scrollY: 0 };
  return {
    paragraphs: cached.paragraphs,
    scrollY: getChapterScrollY(loadProgress(slug), chapterIdx),
  };
}
