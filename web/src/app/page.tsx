import Link from "next/link";
import { listStories, getChapterIndex, getStoryTitle } from "@/lib/data";
import { getGradientFromString } from "@/lib/color";
import CardProgressOverlay from "@/components/CardProgressOverlay";
import { BookOpen, CaretRight } from "@/components/icons";
import ContinueReadingSection, {
  type StoryMeta,
} from "@/components/ContinueReadingSection";

import SiteFooter from "@/components/SiteFooter";

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
            <span aria-hidden="true" className="mr-1 inline-block w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] align-middle" />
            Thư Viện Cá Nhân
          </p>
          <h1
            style={{ fontFamily: "var(--font-ui-serif)" }}
            className="text-4xl md:text-6xl font-bold tracking-tight mb-3 leading-[1.1] text-[var(--color-text)]"
          >
            Nghe
            <span className="text-[var(--color-accent)]"> Truyện</span>
          </h1>
          <p className="text-[var(--color-text-muted)] text-sm leading-relaxed max-w-xs mb-5">
            Trải nghiệm đọc cá nhân.&ensp;Yên tĩnh, không quảng cáo.
          </p>

          {/* Stats strip */}
          <div className="flex flex-wrap gap-2">
            <span className="stat-pill">
              <span className="stat-value">{storyMetas.length}</span>
              <span className="stat-label">truyện</span>
            </span>
            <span className="stat-pill">
              <span className="stat-value">
                {storyMetas.reduce((sum, s) => sum + s.totalChapters, 0)}
              </span>
              <span className="stat-label">chương</span>
            </span>
          </div>
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

      <SiteFooter />
    </main>
  );
}

function StoryCard({ meta }: { meta: StoryMeta }) {
  const { slug, title, totalChapters } = meta;
  const gradient = getGradientFromString(slug);

  return (
    <Link href={`/story/${slug}`} className="book-card block rounded-xl">
      <div
        className="book-card-inner aspect-[2/3] border border-[var(--color-border)] group
          hover:border-[var(--color-accent)]/40 transition-colors duration-300 active:scale-[0.98]"
      >
        {/* Gradient background */}
        <div className={`absolute inset-0 bg-gradient-to-br ${gradient}`} />
        {/* Depth overlay — darker at bottom for title legibility */}
        <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/25 to-black/15" />

        {/* Light sheen sweep on hover */}
        <div className="card-sheen rounded-[inherit]" />

        {/* Content */}
        <div className="relative z-20 h-full flex flex-col p-3.5">
          {/* Top: floating spine tag */}
          <div className="flex justify-start">
            <span className="text-[9px] font-bold tracking-[0.2em] uppercase text-white/50">
              {slug.length > 18 ? `${slug.slice(0, 18)}…` : slug}
            </span>
          </div>

          <div className="flex-1" />

          {/* Bottom: title + chapter count — like a real cover */}
          <div>
            <h2
              style={{ fontFamily: "var(--font-ui-serif)" }}
              className="font-bold text-left text-white/95 drop-shadow-[0_2px_8px_rgba(0,0,0,0.95)] text-sm md:text-[15px] leading-snug line-clamp-4 mb-2"
            >
              {title}
            </h2>
            <div className="flex items-center gap-1.5">
              <span className="h-px w-4 bg-[var(--color-accent)]/70" />
              <span className="text-[10px] font-semibold tracking-wide text-white/60">
                {totalChapters > 0 ? `${totalChapters} chương` : "Đang cập nhật"}
              </span>
            </div>
          </div>
        </div>

        {/* Progress overlay */}
        <CardProgressOverlay slug={slug} totalChapters={totalChapters} />
      </div>
    </Link>
  );
}
