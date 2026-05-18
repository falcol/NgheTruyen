import { notFound } from "next/navigation";
import { crawlChapterApiPath } from "@/lib/chapter-nav";
import {
  getChapterIndex,
  getStoryTitle,
  getTotalChapters,
} from "@/lib/data";
import ReaderClient from "@/components/ReaderClient";

export const revalidate = 3600;

export default async function ReaderPage({
  params,
}: {
  params: Promise<{ slug: string; chapterIdx: string }>;
}) {
  const { slug, chapterIdx: idxStr } = await params;
  const chapterIdx = parseInt(idxStr, 10);

  if (isNaN(chapterIdx)) return notFound();

  const chapters = getChapterIndex(slug);
  if (!chapters) return notFound();

  const chapterMeta = chapters.find((c) => c.index === chapterIdx);
  if (!chapterMeta) return notFound();

  const storyTitle = getStoryTitle(slug);
  const totalChapters = getTotalChapters(slug);

  return (
    <ReaderClient
      slug={slug}
      storyTitle={storyTitle}
      chapterIdx={chapterIdx}
      totalChapters={totalChapters}
      title={chapterMeta.title}
      chapterContentUrl={crawlChapterApiPath(slug, chapterIdx)}
      chapters={chapters}
    />
  );
}
