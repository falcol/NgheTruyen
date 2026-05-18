"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect } from "react";
import {
  adjacentChapterContentUrls,
  crawlChapterApiPath,
} from "@/lib/chapter-nav";
import { prefetchChapterContent } from "@/lib/chapter-prefetch";
import { chapterCacheUrlPath, epubFilenameFromReaderSlug } from "@/lib/epub-urls";
import { useProgress } from "@/hooks/useProgress";

interface ChapterMeta {
  index: number;
  title: string;
}

function chapterContentUrl(slug: string, chapterIdx: number): string | null {
  const epubFile = epubFilenameFromReaderSlug(slug);
  if (epubFile) return chapterCacheUrlPath(epubFile, chapterIdx);
  return crawlChapterApiPath(slug, chapterIdx);
}

export default function ChapterList({
  slug,
  chapters,
  readHref,
}: {
  slug: string;
  chapters: ChapterMeta[];
  readHref?: string;
}) {
  const router = useRouter();
  const { progress } = useProgress(slug);

  const href = (idx: number) =>
    readHref ? `${readHref}/${idx}` : `/read/${slug}/${idx}`;

  const prefetchOnIntent = useCallback(
    (chapterIdx: number) => {
      router.prefetch(href(chapterIdx));

      const main = chapterContentUrl(slug, chapterIdx);
      if (main) prefetchChapterContent(main).catch(() => {});

      const { prev, next } = adjacentChapterContentUrls(slug, chapters, chapterIdx);
      if (prev) prefetchChapterContent(prev).catch(() => {});
      if (next) prefetchChapterContent(next).catch(() => {});
    },
    [slug, chapters, router, readHref],
  );

  useEffect(() => {
    if (progress) prefetchOnIntent(progress.chapterIdx);
  }, [progress, prefetchOnIntent]);

  return (
    <div className="space-y-1">
      {progress && (
        <Link
          href={href(progress.chapterIdx)}
          onMouseEnter={() => prefetchOnIntent(progress.chapterIdx)}
          onFocus={() => prefetchOnIntent(progress.chapterIdx)}
          className="block p-3 mb-4 rounded-lg bg-[var(--color-accent-dim)] text-white font-medium"
        >
          Tiếp tục đọc:{" "}
          {chapters.find((ch) => ch.index === progress.chapterIdx)?.title ||
            `Chương ${progress.chapterIdx + 1}`}
        </Link>
      )}

      {chapters.map((ch) => {
        const isRead = progress && progress.chapterIdx >= ch.index;
        const isCurrent = progress && progress.chapterIdx === ch.index;

        return (
          <Link
            key={ch.index}
            href={href(ch.index)}
            onMouseEnter={() => prefetchOnIntent(ch.index)}
            onFocus={() => prefetchOnIntent(ch.index)}
            className={`block p-3 rounded-lg transition-colors ${
              isCurrent
                ? "bg-[var(--color-accent)]/20 text-[var(--color-accent)]"
                : "hover:bg-[var(--color-surface)]"
            }`}
          >
            <span
              className={
                isRead && !isCurrent ? "text-[var(--color-text-muted)]" : ""
              }
            >
              {ch.title}
            </span>
          </Link>
        );
      })}
    </div>
  );
}
