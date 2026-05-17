import { notFound } from "next/navigation";
import {
  getEpubChapter,
  getEpubMeta,
  isEpubChapterReady,
} from "@/lib/epub";
import EpubCacheMissing from "@/components/EpubCacheMissing";
import ReaderClient from "@/components/ReaderClient";

export const revalidate = 86400;

export default async function EpubReaderPage({
  params,
}: {
  params: Promise<{ filename: string; chapterIdx: string }>;
}) {
  const { filename, chapterIdx: idxStr } = await params;
  const decodedFilename = decodeURIComponent(filename);
  const chapterIdx = parseInt(idxStr, 10);
  if (isNaN(chapterIdx)) return notFound();

  const meta = getEpubMeta(decodedFilename);
  if (!meta) return notFound();

  const readHref = `/epub/${encodeURIComponent(decodedFilename)}/read`;
  const backHref = `/epub/${encodeURIComponent(decodedFilename)}`;

  if (!isEpubChapterReady(decodedFilename, chapterIdx)) {
    return (
      <EpubCacheMissing
        filename={decodedFilename}
        chapterIdx={chapterIdx}
        backHref={backHref}
      />
    );
  }

  const chapter = getEpubChapter(decodedFilename, chapterIdx);
  if (!chapter) return notFound();

  return (
    <ReaderClient
      slug={`epub-${decodedFilename}`}
      storyTitle={meta.title}
      chapterIdx={chapterIdx}
      totalChapters={meta.chapters.length}
      title={chapter.title}
      paragraphs={chapter.paragraphs}
      chapters={meta.chapters}
      backHref={backHref}
      readHref={readHref}
    />
  );
}
