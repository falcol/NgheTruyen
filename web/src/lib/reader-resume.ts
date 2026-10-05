import { getChapterScrollY, loadProgress } from "@/hooks/useProgress";
import { getCachedChapter } from "@/lib/chapter-prefetch";
import { peekVolChapter } from "@/lib/vol-content";

function peekParagraphs(url: string, chapterIdx: number): string[] | null {
  const cached = getCachedChapter(url);
  if (cached) return cached.paragraphs;
  // Crawler chapters are keyed as `${volUrl}#ch=${idx}` (see volChapterKey);
  // the epub cache never holds those keys, so consult the volume cache too.
  // Without this, same-volume navigation always flashes the loading skeleton
  // even though the volume is already parsed in RAM.
  const sep = url.lastIndexOf("#ch=");
  if (sep !== -1) {
    const vol = peekVolChapter(url.slice(0, sep), chapterIdx);
    if (vol) return vol.paragraphs;
  }
  return null;
}

/**
 * Synchronous resume for the open chapter. Scroll is returned only together
 * with stored paragraphs, so a loading shell never receives a stale offset.
 */
export function resumeReaderChapter(
  slug: string,
  chapterIdx: number,
  url: string,
): { paragraphs: string[] | null; scrollY: number } {
  const paragraphs = peekParagraphs(url, chapterIdx);
  if (!paragraphs) return { paragraphs: null, scrollY: 0 };
  return {
    paragraphs,
    scrollY: getChapterScrollY(loadProgress(slug), chapterIdx),
  };
}
