import { notFound } from "next/navigation";
import {
  getChapter,
  getChapterIndex,
  getStoryTitle,
  getTotalChapters,
} from "@/lib/data";
import ReaderClient from "@/components/ReaderClient";

export const dynamic = "force-dynamic";

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

  const storyTitle = getStoryTitle(slug);
  const totalChapters = getTotalChapters(slug);
  const chapters = getChapterIndex(slug);
  if (!chapters) return notFound();

  return (
    <ReaderClient
      slug={slug}
      storyTitle={storyTitle}
      chapterIdx={chapterIdx}
      totalChapters={totalChapters}
      title={chapter.title}
      paragraphs={chapter.paragraphs}
      chapters={chapters}
    />
  );
}
