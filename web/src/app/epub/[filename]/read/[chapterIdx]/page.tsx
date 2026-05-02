import { notFound } from "next/navigation";
import { getEpubChapter, getEpubChapters, getEpubMeta } from "@/lib/epub";
import ReaderClient from "@/components/ReaderClient";

export const dynamic = "force-dynamic";

export default async function EpubReaderPage({
  params,
}: {
  params: Promise<{ filename: string; chapterIdx: string }>;
}) {
  const { filename, chapterIdx: idxStr } = await params;
  const decodedFilename = decodeURIComponent(filename);
  const chapterIdx = parseInt(idxStr, 10);
  if (isNaN(chapterIdx)) return notFound();

  const chapter = await getEpubChapter(decodedFilename, chapterIdx);
  if (!chapter) return notFound();

  const meta = await getEpubMeta(decodedFilename);
  const chapters = await getEpubChapters(decodedFilename);
  if (!meta || !chapters) return notFound();

  const readHref = `/epub/${encodeURIComponent(decodedFilename)}/read`;
  const backHref = `/epub/${encodeURIComponent(decodedFilename)}`;

  return (
    <ReaderClient
      slug={`epub-${decodedFilename}`}
      storyTitle={meta.title}
      chapterIdx={chapterIdx}
      totalChapters={chapters.length}
      title={chapter.title}
      paragraphs={chapter.paragraphs}
      chapters={chapters}
      backHref={backHref}
      readHref={readHref}
    />
  );
}
