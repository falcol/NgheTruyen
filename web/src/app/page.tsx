import Link from "next/link";
import { listStories, getChapterIndex, getStoryTitle } from "@/lib/data";
import { getGradientFromString } from "@/lib/color";

export default function HomePage() {
  const stories = listStories();

  return (
    <main className="max-w-5xl mx-auto px-4 py-12 md:py-16">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-12 border-b border-white/5 pb-6">
        <div>
          <h1 className="text-3xl md:text-5xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-[var(--color-accent)] to-purple-400 drop-shadow-sm mb-2">
            Thư Viện Nghe
          </h1>
          <p className="text-[var(--color-text-muted)] font-medium">Trải nghiệm đọc cá nhân cao cấp</p>
        </div>
        <Link
          href="/epub"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl glass-panel hover:bg-white/10 transition-all font-medium group text-sm"
        >
          <span className="group-hover:animate-bounce">📚</span>
          <span>Kho EPUB</span>
          <span className="group-hover:translate-x-1 transition-transform">→</span>
        </Link>
      </div>

      {stories.length === 0 && (
        <div className="glass-panel p-10 rounded-3xl text-center border-dashed">
          <div className="text-4xl mb-4 opacity-50">📭</div>
          <p className="text-[var(--color-text-muted)] text-lg">
            Kệ sách trống. Hãy crawl dữ liệu trước.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 md:gap-6">
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

  const gradient = getGradientFromString(slug);

  return (
    <Link
      href={`/story/${slug}`}
      className="group block relative aspect-[2/3] rounded-xl overflow-hidden glass-panel shadow-[0_8px_30px_rgba(0,0,0,0.5)] hover:shadow-[0_15px_40px_rgba(56,189,248,0.2)] transition-all duration-500 hover:-translate-y-2 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
    >
      <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-90 group-hover:opacity-100 transition-opacity duration-500`}></div>
      <div className="absolute inset-0 bg-black/30 group-hover:bg-black/10 transition-colors duration-500"></div>
      
      {/* Book spine lighting effect */}
      <div className="absolute left-0 top-0 bottom-0 w-3 bg-gradient-to-r from-white/20 to-transparent z-10 pointer-events-none"></div>
      <div className="absolute left-0 top-0 bottom-0 w-[1px] bg-white/40 z-10 pointer-events-none"></div>
      <div className="absolute left-1.5 top-0 bottom-0 w-[1px] bg-black/20 z-10 pointer-events-none"></div>
      
      <div className="relative z-20 h-full flex flex-col p-4">
        <div className="flex-1 flex items-center justify-center">
          <h2 className="font-serif font-bold text-center text-white/95 drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)] text-lg md:text-xl leading-snug line-clamp-4">
            {title}
          </h2>
        </div>
        <div className="mt-auto text-center border-t border-white/20 pt-3 relative">
          <div className="absolute -top-[1px] left-1/4 right-1/4 h-[1px] bg-gradient-to-r from-transparent via-white/50 to-transparent"></div>
          <span className="inline-block bg-black/40 backdrop-blur-md px-3 py-1 rounded-full text-[10px] md:text-xs font-bold text-white/90 uppercase tracking-widest border border-white/10 shadow-inner">
            {chapterCount} CH
          </span>
        </div>
      </div>
    </Link>
  );
}
