import Link from "next/link";
import { listStories, getChapterIndex, getStoryTitle } from "@/lib/data";
import { getGradientFromString } from "@/lib/color";
import CardProgressOverlay from "@/components/CardProgressOverlay";
import { BookOpen, CaretRight } from "@/components/icons";
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
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-14 pb-10 border-b border-[var(--color-border)] animate-slide-up stagger-1">
        <div>
          {/* Eyebrow */}
          <p className="text-[10px] font-bold tracking-[0.3em] uppercase text-[var(--color-accent)] mb-3 opacity-80">
            ✦ Thư Viện Cá Nhân
          </p>
          <h1
            style={{ fontFamily: "var(--font-ui-serif)" }}
            className="text-4xl md:text-6xl font-bold tracking-tight mb-3 leading-[1.1] text-[var(--color-text)]"
          >
            Nghe
            <span className="text-[var(--color-accent)]"> Truyện</span>
          </h1>
          <p className="text-[var(--color-text-muted)] text-sm leading-relaxed max-w-xs">
            Trải nghiệm đọc cá nhân.&ensp;Yên tĩnh, không quảng cáo.
          </p>
        </div>

        <Link
          href="/epub"
          className="group inline-flex items-center gap-2.5 px-5 py-3 rounded-xl bg-gradient-to-b from-[var(--color-surface)] to-[var(--color-bg)] border border-[var(--color-border)] hover:border-[var(--color-accent)]/50 transition-all duration-300 font-medium text-sm min-h-[44px] shrink-0 btn-spring"
        >
          <BookOpen size={18} className="text-[var(--color-accent)]" />
          <span className="text-[var(--color-text-muted)] group-hover:text-[var(--color-text)] transition-colors">Kho EPUB</span>
          <CaretRight size={14} className="text-[var(--color-accent)] group-hover:translate-x-0.5 transition-transform duration-200" />
        </Link>
      </div>

      {/* Continue reading section */}
      <div className="animate-slide-up stagger-2">
        <ContinueReadingSection stories={storyMetas} />
      </div>

      {stories.length === 0 && (
        <div className="p-10 rounded-2xl text-center border border-dashed border-[var(--color-border)]">
          <p className="text-[var(--color-text-muted)] text-lg">
            Chưa có truyện nào trong thư viện.
          </p>
        </div>
      )}

      {/* Story grid */}
      {stories.length > 0 && (
        <>
          {/* Section header — ornamental divider */}
          <div className="ornament-divider mb-8 animate-slide-up stagger-3">
            <span className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] candle-glow" />
              <span
                style={{ fontFamily: "var(--font-ui-serif)" }}
                className="text-[11px] font-semibold text-[var(--color-text-muted)] tracking-[0.25em]"
              >
                Tất Cả Truyện
              </span>
              <span className="text-[var(--color-accent)] text-[10px] opacity-50">
                {storyMetas.length}
              </span>
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5 md:gap-5 animate-slide-up stagger-4">
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
    <Link href={`/story/${slug}`} className="book-card block focus:outline-none">
      <div
        className="book-card-inner aspect-[2/3] border border-[var(--color-border)] group
          hover:border-[var(--color-accent)]/40 transition-colors duration-300 active:scale-[0.98]"
      >
        {/* Gradient background */}
        <div className={`absolute inset-0 bg-gradient-to-br ${gradient}`} />
        {/* Depth overlay — darker at top for title visibility */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-black/30" />

        {/* Content */}
        <div className="relative z-20 h-full flex flex-col p-3.5">
          <div className="flex-1 flex items-center justify-center">
            <h2
              style={{ fontFamily: "var(--font-ui-serif)" }}
              className="font-bold text-center text-white/95 drop-shadow-[0_2px_8px_rgba(0,0,0,0.95)] text-sm md:text-base leading-snug line-clamp-5 px-1"
            >
              {title}
            </h2>
          </div>

          {/* Bottom: chapter count */}
          <div className="mt-auto pt-2 flex justify-center">
            <span className="inline-flex items-center bg-black/50 backdrop-blur-md text-white/80 text-[10px] font-bold tracking-widest px-3 py-1 rounded-full border border-white/10">
              {totalChapters > 0 ? `${totalChapters} CH` : "···"}
            </span>
          </div>
        </div>

        {/* Progress overlay */}
        <CardProgressOverlay slug={slug} totalChapters={totalChapters} />
      </div>
    </Link>
  );
}
