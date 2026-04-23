import Link from "next/link";
import { listStories, getChapterIndex, getStoryTitle } from "@/lib/data";

export default function HomePage() {
  const stories = listStories();

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <h1 className="text-2xl font-bold mb-6">Nghe Truyện</h1>

      {stories.length === 0 && (
        <p className="text-(--color-text-muted)">
          Chưa có truyện nào. Hãy crawl dữ liệu trước.
        </p>
      )}

      <div className="space-y-3">
        {stories.map((slug) => (
          <StoryCard key={slug} slug={slug} />
        ))}
      </div>
    </main>
  );
}

function StoryCard({ slug }: { slug: string }) {
  let title = slug;
  let chapterCount = 0;

  try {
    const index = getChapterIndex(slug);
    if (index) chapterCount = index.length;
    title = getStoryTitle(slug);
  } catch {
    // fallback to slug
  }

  return (
    <Link
      href={`/story/${slug}`}
      className="block p-4 rounded-lg bg-(--color-surface) hover:bg-(--color-surface)/80 transition-colors"
    >
      <div className="font-semibold text-lg truncate">{title}</div>
      <div className="text-sm text-(--color-text-muted) mt-1">
        {chapterCount} chương · {slug}
      </div>
    </Link>
  );
}
