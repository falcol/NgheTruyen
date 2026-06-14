import Link from "next/link";
import { listStories, getChapterIndex, getStoryTitle } from "@/lib/data";
import { getGradientFromString } from "@/lib/color";
import CardProgressOverlay from "@/components/CardProgressOverlay";
import ContinueReadingSection, {
  type StoryMeta,
} from "@/components/ContinueReadingSection";

export default function HomePage() {
  const stories = listStories();

  const storyMetas: StoryMeta[] = stories.map((slug) => {
    let title = slug;
    let totalChapters = 0;
    try {
      title = getStoryTitle(slug);
      const idx = getChapterIndex(slug);
      if (idx) totalChapters = idx.length;
    } catch {
      // fallback
    }
    return {
      slug,
      title,
      totalChapters,
      readHref: `/read/${slug}`,
      detailHref: `/story/${slug}`,
    };
  });

  return (
    <main className="max-w-5xl mx-auto px-4 py-12 md:py-16">
      {/* Hero header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-12 pb-8 border-b border-[var(--color-border)]">
        <div>
          {/* Decorative label */}
          <div className="flex items-center gap-2 mb-3">
            <span className="w-6 h-[1.5px] bg-gradient-to-r from-[var(--color-accent)] to-transparent rounded-full" />
            <span className="text-[10px] font-bold tracking-[0.2em] uppercase text-[var(--color-accent)] opacity-80">
              Thư Viện Cá Nhân
            </span>
          </div>
          <h1 className="text-3xl md:text-5xl font-extrabold tracking-tight mb-2 leading-tight">
            <span className="sakura-text">Nghe</span>
            <span className="text-[var(--color-text)]"> Truyện</span>
          </h1>
          <p className="text-[var(--color-text-muted)] text-sm font-medium">
            Trải nghiệm đọc cá nhân — yên tĩnh, không quảng cáo
          </p>
        </div>

        <Link
          href="/epub"
          className="group inline-flex items-center gap-2.5 px-5 py-2.5 rounded-xl glass-panel hover:bg-[var(--color-accent)]/5 hover:border-[var(--color-accent)]/30 transition-all duration-300 font-medium text-sm border border-[var(--color-border)] shrink-0"
        >
          <span className="text-base">📚</span>
          <span className="text-[var(--color-text-muted)] group-hover:text-[var(--color-text)] transition-colors">Kho EPUB</span>
          <span className="text-[var(--color-accent)] group-hover:translate-x-0.5 transition-transform duration-200">→</span>
        </Link>
      </div>

      {/* Continue reading section */}
      <ContinueReadingSection stories={storyMetas} />

      {stories.length === 0 && (
        <div className="glass-panel p-10 rounded-3xl text-center border border-dashed border-[var(--color-border)]">
          <div className="text-4xl mb-4 opacity-50">📭</div>
          <p className="text-[var(--color-text-muted)] text-lg">
            Kệ sách trống. Hãy crawl dữ liệu trước.
          </p>
        </div>
      )}

      {/* Story grid */}
      {stories.length > 0 && (
        <>
          {/* Section header */}
          <div className="ink-divider mb-6">
            <span className="text-xs font-bold text-[var(--color-text-muted)] uppercase tracking-[0.18em]">
              Tất cả truyện
            </span>
            <span className="text-[var(--color-accent)] text-xs opacity-60 ml-auto">
              {storyMetas.length} tác phẩm
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 md:gap-5">
            {storyMetas.map((meta) => (
              <StoryCard key={meta.slug} meta={meta} />
            ))}
          </div>
        </>
      )}
    </main>
  );
}

function StoryCard({ meta }: { meta: StoryMeta }) {
  const { slug, title, totalChapters } = meta;
  const gradient = getGradientFromString(slug);

  return (
    <Link
      href={`/story/${slug}`}
      className="anime-card group block relative aspect-[2/3] rounded-xl overflow-hidden
        shadow-[0_8px_32px_rgba(0,0,0,0.6)]
        hover:shadow-[0_16px_48px_rgba(232,121,160,0.2),0_8px_32px_rgba(0,0,0,0.5)]
        hover:-translate-y-2 transition-all duration-400
        focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/60
        border border-white/5 hover:border-[var(--color-accent)]/20"
    >
      {/* Gradient background */}
      <div
        className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-85 group-hover:opacity-100 transition-opacity duration-400`}
      />
      {/* Depth overlay */}
      <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/20 to-transparent" />

      {/* Book spine */}
      <div className="absolute left-0 top-0 bottom-0 w-3 bg-gradient-to-r from-white/15 to-transparent z-10 pointer-events-none" />
      <div className="absolute left-0 top-0 bottom-0 w-[1px] bg-white/30 z-10 pointer-events-none" />

      {/* Sakura glow on hover — top edge */}
      <div className="absolute top-0 left-1/4 right-1/4 h-[1px] bg-gradient-to-r from-transparent via-[var(--color-accent)]/0 to-transparent group-hover:via-[var(--color-accent)]/50 transition-all duration-500 z-10 pointer-events-none" />

      {/* Content */}
      <div className="relative z-20 h-full flex flex-col p-3.5">
        <div className="flex-1 flex items-center justify-center">
          <h2 className="font-serif font-bold text-center text-white/95 drop-shadow-[0_2px_8px_rgba(0,0,0,0.9)] text-base md:text-lg leading-snug line-clamp-4">
            {title}
          </h2>
        </div>

        {/* Bottom: chapter count */}
        <div className="mt-auto pt-3 flex justify-center">
          <span className="anime-badge">
            <span className="opacity-70">✦</span>
            {totalChapters > 0 ? `${totalChapters} CH` : "···"}
          </span>
        </div>
      </div>

      {/* Progress overlay */}
      <CardProgressOverlay slug={slug} totalChapters={totalChapters} />
    </Link>
  );
}
