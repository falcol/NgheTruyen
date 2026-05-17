import { notFound } from "next/navigation";
import { chapterCacheUrlPath, getEpubMeta } from "@/lib/epub";
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

  const chapter = meta.chapters[chapterIdx];
  if (!chapter) return notFound();

  const readHref = `/epub/${encodeURIComponent(decodedFilename)}/read`;
  const backHref = `/epub/${encodeURIComponent(decodedFilename)}`;

  return (
    <ReaderClient
      slug={`epub-${decodedFilename}`}
      storyTitle={meta.title}
      chapterIdx={chapterIdx}
      totalChapters={meta.chapters.length}
      title={chapter.title}
      chapterContentUrl={chapterCacheUrlPath(decodedFilename, chapterIdx)}
      chapters={meta.chapters}
      backHref={backHref}
      readHref={readHref}
    />
  );
}
