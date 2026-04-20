import { notFound } from "next/navigation";
import {
  getChapter,
  getChapterIndex,
  getStoryTitle,
  getTotalChapters,
  listStories,
} from "@/lib/data";
import ReaderClient from "@/components/ReaderClient";

export function generateStaticParams() {
  const params: { slug: string; chapterIdx: string }[] = [];
  for (const slug of listStories()) {
    const chapters = getChapterIndex(slug);
    for (const ch of chapters) {
      params.push({ slug, chapterIdx: String(ch.index) });
    }
  }
  return params;
}

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
