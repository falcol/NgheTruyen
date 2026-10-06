import { chapterCacheUrlPath, epubFilenameFromReaderSlug } from "./epub-urls";

export function crawlChapterApiPath(slug: string, chapterIdx: number): string {
  return `/api/chapter/${encodeURIComponent(slug)}/${chapterIdx}`;
}

export function adjacentChapterContentUrls(
  slug: string,
  chapters: { index: number }[],
  chapterIdx: number,
): { prev?: string; next?: string } {
  const pos = chapters.findIndex((c) => c.index === chapterIdx);
  if (pos === -1) return {};

  const epubFile = epubFilenameFromReaderSlug(slug);
  const prevChapter = chapters[pos - 1];
  const nextChapter = chapters[pos + 1];

  if (epubFile) {
    return {
      prev: prevChapter
        ? chapterCacheUrlPath(epubFile, prevChapter.index)
        : undefined,
      next: nextChapter
        ? chapterCacheUrlPath(epubFile, nextChapter.index)
        : undefined,
    };
  }

  return {
    prev: prevChapter ? crawlChapterApiPath(slug, prevChapter.index) : undefined,
    next: nextChapter ? crawlChapterApiPath(slug, nextChapter.index) : undefined,
  };
}
