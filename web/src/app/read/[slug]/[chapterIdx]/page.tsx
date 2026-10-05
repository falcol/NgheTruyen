import { notFound } from "next/navigation";
import {
  getChapterIndex,
  getStoryTitle,
  getTotalChapters,
  getVolumeManifest,
} from "@/lib/data";
import { readerFirstChapters } from "@/lib/reader-shell";
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

  // Chapters are fetched client-side from static volume files; without a
  // manifest there is nothing to serve, so treat it as a missing story.
  const manifest = getVolumeManifest(slug);
  if (!manifest) return notFound();

  return (
    <ReaderClient
      slug={slug}
      storyTitle={storyTitle}
      chapterIdx={chapterIdx}
      totalChapters={totalChapters}
      title={chapterMeta.title}
      chapterVols={manifest.vols}
      chapters={readerFirstChapters(chapterMeta)}
      chapterIndexUrl={manifest.indexUrl}
    />
  );
}
