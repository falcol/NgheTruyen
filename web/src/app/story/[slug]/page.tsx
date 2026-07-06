import Link from "next/link";
import { notFound } from "next/navigation";
import { estimateReadingTime, getChapterIndex, getStoryTitle, listStories } from "@/lib/data";
import ChapterList from "@/components/ChapterList";
import ReadCTA from "@/components/ReadCTA";
import { getGradientFromString } from "@/lib/color";
import { ArrowLeft, Clock } from "@/components/icons";

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
  if (!chapters) return notFound();
  const storyTitle = getStoryTitle(slug);
  const gradient = getGradientFromString(slug);

  return (
    <main className="max-w-4xl mx-auto px-4 py-8 md:py-12">
      <Link
        href="/"
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-[var(--color-accent)]/30 text-sm text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-colors duration-200 mb-8 group font-medium"
      >
        <ArrowLeft size={16} className="group-hover:-translate-x-1 transition-transform duration-200" /> Thư Viện Nghe
      </Link>

      <div className="relative overflow-hidden rounded-2xl mb-12 border border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-50 mix-blend-overlay`}></div>
        <div className="absolute inset-0 bg-black/50"></div>

        <div className="relative z-10 p-8 md:p-12 flex flex-col md:flex-row gap-8 items-center md:items-start">
          {/* Big book cover representation */}
          <div className={`w-40 md:w-56 aspect-[2/3] shrink-0 rounded-2xl bg-gradient-to-br ${gradient} relative overflow-hidden flex items-center justify-center p-5 border border-white/10`}>
            <h2 className="font-serif font-bold text-center text-white/95 drop-shadow-[0_4px_6px_rgba(0,0,0,0.8)] text-xl leading-snug line-clamp-6">
              {storyTitle}
            </h2>
          </div>

          <div className="flex-1 text-center md:text-left flex flex-col h-full justify-center">
            <h1 className="text-3xl md:text-5xl font-extrabold mb-6 leading-tight text-white/95 drop-shadow-lg">
              {storyTitle}
            </h1>
            <div className="flex flex-wrap items-center justify-center md:justify-start gap-3 text-sm text-[var(--color-text-muted)] mb-8">
              <span className="bg-white/10 px-4 py-2 rounded-xl font-bold text-white/90 border border-white/10 tracking-wider">
                {chapters.length} CHƯƠNG
              </span>
              <span className="bg-white/10 px-4 py-2 rounded-xl font-medium text-white/70 border border-white/10 text-sm flex items-center gap-1.5">
                <Clock size={14} className="text-[var(--color-accent)]" />
                {estimateReadingTime(chapters.length)}
              </span>
            </div>
            
            <div className="flex justify-center md:justify-start">
              <ReadCTA
                slug={slug}
                totalChapters={chapters.length}
                chaptersInfo={chapters}
                readHrefBase={`/read/${slug}`}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-2xl mx-auto">
        <h3 className="text-xl font-bold mb-6 flex items-center gap-3 text-white/90">
          <span className="w-8 h-[2px] bg-[var(--color-accent)] rounded-full"></span>
          Mục lục
        </h3>
        <ChapterList slug={slug} chapters={chapters} />
      </div>
    </main>
  );
}
