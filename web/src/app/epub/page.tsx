import Link from "next/link";
import { listEpubSummaries } from "@/lib/epub";
import { getGradientFromString } from "@/lib/color";
import CardProgressOverlay from "@/components/CardProgressOverlay";
import SiteFooter from "@/components/SiteFooter";
import { ArrowLeft } from "@/components/icons";
import ContinueReadingSection, {
  type StoryMeta,
} from "@/components/ContinueReadingSection";

export const revalidate = 3600;

export default function EpubListPage() {
  const books = listEpubSummaries();

  const storyMetas: StoryMeta[] = books.map((book) => ({
    slug: `epub-${book.filename}`,
    title: book.title || book.filename,
    totalChapters: book.chapterCount ?? 0,
    readHref: `/epub/${encodeURIComponent(book.filename)}/read`,
    detailHref: `/epub/${encodeURIComponent(book.filename)}`,
  }));

  return (
    <main className="max-w-5xl mx-auto px-4 py-12 md:py-16">
      {/* Hero header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-12 pb-8 border-b border-[var(--color-border)] animate-slide-up stagger-1">
        <div>
          <p className="text-[10px] font-bold tracking-[0.3em] uppercase text-[var(--color-accent)] mb-3 opacity-80">
            <span aria-hidden="true" className="mr-1 inline-block w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] align-middle" />
            Kho Sách Chất Lượng
          </p>
          <h1
            style={{ fontFamily: "var(--font-ui-serif)" }}
            className="text-3xl md:text-5xl font-bold tracking-tight mb-2 leading-tight text-[var(--color-text)]"
          >
            Kho <span className="text-[var(--color-accent)]">EPUB</span>
          </h1>
          <p className="text-[var(--color-text-muted)] text-sm font-medium">
            Sách chất lượng cao, định dạng chuẩn.
          </p>
        </div>

        <Link
          href="/"
          className="group inline-flex items-center gap-2.5 px-5 py-3 rounded-xl bg-gradient-to-b from-[var(--color-surface)] to-[var(--color-bg)] border border-[var(--color-border)] hover:border-[var(--color-accent)]/50 transition-all duration-300 font-medium text-sm min-h-[44px] shrink-0 btn-spring"
        >
          <ArrowLeft size={16} className="text-[var(--color-accent)] group-hover:-translate-x-0.5 transition-transform duration-200" />
          <span className="text-[var(--color-text-muted)] group-hover:text-[var(--color-text)] transition-colors">Thư Viện</span>
        </Link>
      </div>

      {/* Continue reading section */}
      <div className="animate-slide-up stagger-2">
        <ContinueReadingSection stories={storyMetas} />
      </div>

      {books.length === 0 && (
        <div className="p-10 rounded-2xl text-center border border-dashed border-[var(--color-border)]">
          <p className="text-[var(--color-text-muted)] text-lg">
            Chưa có sách nào trong kho.
          </p>
        </div>
      )}

      {books.length > 0 && (
        <>
          {/* Section header — ornamental divider */}
          <div className="ornament-divider mb-8 animate-slide-up stagger-3">
            <span className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] candle-glow" />
              <span
                style={{ fontFamily: "var(--font-ui-serif)" }}
                className="text-[11px] font-semibold text-[var(--color-text-muted)] tracking-[0.25em]"
              >
                Tất Cả Sách
              </span>
              <span className="text-[var(--color-accent)] text-[10px] opacity-50">
                {storyMetas.length}
              </span>
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5 md:gap-5 animate-slide-up stagger-4">
            {storyMetas.map((meta) => {
              const gradient = getGradientFromString(meta.title);
              return (
                <Link
                  key={meta.slug}
                  href={meta.detailHref}
                  className="book-card block rounded-xl"
                >
                  <div
                    className="book-card-inner aspect-[2/3] border border-[var(--color-border)] group
                      hover:border-[var(--color-accent)]/40 transition-colors duration-300 active:scale-[0.98]"
                  >
                    <div className={`absolute inset-0 bg-gradient-to-br ${gradient}`} />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/85 via-black/25 to-black/15" />

                    <div className="card-sheen rounded-[inherit]" />

                    <div className="relative z-20 h-full flex flex-col p-3.5">
                      <div className="flex-1" />
                      <div>
                        <h2
                          style={{ fontFamily: "var(--font-ui-serif)" }}
                          className="font-bold text-left text-white/95 drop-shadow-[0_2px_8px_rgba(0,0,0,0.9)] text-sm md:text-[15px] leading-snug line-clamp-4 mb-2"
                        >
                          {meta.title}
                        </h2>
                        <div className="flex items-center gap-1.5">
                          <span className="h-px w-4 bg-[var(--color-accent)]/70" />
                          <span className="text-[10px] font-semibold tracking-wide text-white/60">
                            {meta.totalChapters > 0
                              ? `${meta.totalChapters} chương`
                              : "Mở sách"}
                          </span>
                        </div>
                      </div>
                    </div>

                    <CardProgressOverlay
                      slug={meta.slug}
                      totalChapters={meta.totalChapters}
                    />
                  </div>
                </Link>
              );
            })}
          </div>
        </>
      )}

      <SiteFooter />
    </main>
  );
}
