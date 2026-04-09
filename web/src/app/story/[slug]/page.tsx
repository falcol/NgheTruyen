import Link from "next/link";
import { getChapterIndex, listStories } from "@/lib/data";
import ChapterList from "@/components/ChapterList";

export function generateStaticParams() {
  return listStories().map((slug) => ({ slug }));
}

export default async function StoryPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const chapters = getChapterIndex(slug);

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <Link
        href="/"
        className="text-sm text-[var(--color-text-muted)] hover:text-[var(--color-accent)] mb-4 inline-block"
      >
        ← Trang chủ
      </Link>

      <h1 className="text-xl font-bold mb-2 truncate">{slug}</h1>
      <p className="text-sm text-[var(--color-text-muted)] mb-6">
        {chapters.length} chương
      </p>

      <ChapterList slug={slug} chapters={chapters} />
    </main>
  );
}
