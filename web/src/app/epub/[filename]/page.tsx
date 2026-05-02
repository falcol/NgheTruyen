import Link from "next/link";
import { notFound } from "next/navigation";
import { getEpubMeta, listEpubFiles } from "@/lib/epub";
import ChapterList from "@/components/ChapterList";

export const dynamic = "force-dynamic";

export default async function EpubBookPage({
  params,
}: {
  params: Promise<{ filename: string }>;
}) {
  const { filename } = await params;
  const decodedFilename = decodeURIComponent(filename);
  const meta = await getEpubMeta(decodedFilename);
  if (!meta) return notFound();

  const readHref = `/epub/${encodeURIComponent(decodedFilename)}/read`;

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <Link
        href="/epub"
        className="text-sm text-(--color-text-muted) hover:text-(--color-accent) mb-4 inline-block"
      >
        ← EPUB
      </Link>

      <h1 className="text-xl font-bold mb-2 truncate">{meta.title}</h1>
      <p className="text-sm text-(--color-text-muted) mb-2 truncate">
        {meta.filename}
      </p>
      <p className="text-sm text-(--color-text-muted) mb-6">
        {meta.chapters.length} chương
      </p>

      <ChapterList
        slug={`epub-${decodedFilename}`}
        chapters={meta.chapters}
        readHref={readHref}
      />
    </main>
  );
}
