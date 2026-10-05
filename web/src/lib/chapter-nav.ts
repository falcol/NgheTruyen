import type { VolumeRange } from "./data";
import { chapterCacheUrlPath, epubFilenameFromReaderSlug } from "./epub-urls";

/** Resolve the static volume URL holding a chapter (0-based index). */
export function volUrlForChapter(
  vols: VolumeRange[],
  chapterIdx: number,
): string | null {
  // Filename ranges are 1-based chapter numbers; chapter.index is 0-based.
  const n = chapterIdx + 1;
  return vols.find((v) => n >= v.first && n <= v.last)?.url ?? null;
}

export interface AdjacentChapter {
  url: string;
  chapterIdx: number;
}

/** Content location of the chapters neighbouring `chapterIdx`. Epub slugs get
 *  per-chapter cache URLs; crawler slugs get their volume's static URL. */
export function adjacentChapterContentUrls(
  slug: string,
  chapters: { index: number }[],
  chapterIdx: number,
  vols?: VolumeRange[],
): { prev?: AdjacentChapter; next?: AdjacentChapter } {
  const pos = chapters.findIndex((c) => c.index === chapterIdx);
  if (pos === -1) return {};

  const epubFile = epubFilenameFromReaderSlug(slug);
  const prevChapter = chapters[pos - 1];
  const nextChapter = chapters[pos + 1];

  if (epubFile) {
    return {
      prev: prevChapter
        ? { url: chapterCacheUrlPath(epubFile, prevChapter.index), chapterIdx: prevChapter.index }
        : undefined,
      next: nextChapter
        ? { url: chapterCacheUrlPath(epubFile, nextChapter.index), chapterIdx: nextChapter.index }
        : undefined,
    };
  }

  const toAdjacent = (ch: { index: number } | undefined): AdjacentChapter | undefined => {
    if (!ch) return undefined;
    const url = volUrlForChapter(vols ?? [], ch.index);
    return url ? { url, chapterIdx: ch.index } : undefined;
  };

  return {
    prev: toAdjacent(prevChapter),
    next: toAdjacent(nextChapter),
  };
}

/**
 * Index-arithmetic fallback for prefetch: resolves neighbour content locations
 * from `idx ± 1` without needing the full chapter catalog. The catalog arrives
 * after the open chapter paints (`chapterIndexUrl`), so catalog-only lookup
 * returns {} on the first chapters and the next chapter is never prefetched —
 * every early navigation pays a cold volume/chapter fetch. Callers should try
 * `adjacentChapterContentUrls` first (handles non-contiguous indices) and fall
 * back to this.
 */
export function adjacentChapterContentUrlsByIndex(
  slug: string,
  chapterIdx: number,
  totalChapters: number,
  vols?: VolumeRange[],
): { prev?: AdjacentChapter; next?: AdjacentChapter } {
  const toAdjacent = (idx: number): AdjacentChapter | undefined => {
    if (idx < 0 || idx >= totalChapters) return undefined;
    const epubFile = epubFilenameFromReaderSlug(slug);
    if (epubFile) {
      return { url: chapterCacheUrlPath(epubFile, idx), chapterIdx: idx };
    }
    const url = volUrlForChapter(vols ?? [], idx);
    return url ? { url, chapterIdx: idx } : undefined;
  };

  return {
    prev: toAdjacent(chapterIdx - 1),
    next: toAdjacent(chapterIdx + 1),
  };
}
