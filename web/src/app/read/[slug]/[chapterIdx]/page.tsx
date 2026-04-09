import { notFound } from "next/navigation";
import { getChapter, getTotalChapters } from "@/lib/data";
import ReaderClient from "@/components/ReaderClient";

export default async function ReaderPage({
  params,
}: {
  params: Promise<{ slug: string; chapterIdx: string }>;
}) {
  const { slug, chapterIdx: idxStr } = await params;
  const chapterIdx = parseInt(idxStr, 10);

  if (isNaN(chapterIdx)) return notFound();

  const chapter = getChapter(slug, chapterIdx);
  if (!chapter) return notFound();

  const totalChapters = getTotalChapters(slug);

  return (
    <ReaderClient
      slug={slug}
      chapterIdx={chapterIdx}
      totalChapters={totalChapters}
      title={chapter.title}
      paragraphs={chapter.paragraphs}
    />
  );
}
