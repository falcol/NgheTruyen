import Link from "next/link";
import { listEpubSummaries } from "@/lib/epub";
import { getGradientFromString } from "@/lib/color";
import CardProgressOverlay from "@/components/CardProgressOverlay";
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
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-12 pb-8 border-b border-[var(--color-border)]">
        <div>
          <h1 className="text-3xl md:text-5xl font-extrabold tracking-tight mb-2 leading-tight text-[var(--color-text)]">
            Kho EPUB
          </h1>
          <p className="text-[var(--color-text-muted)] text-sm font-medium">
            Sách chất lượng cao, định dạng chuẩn.
          </p>
        </div>

        <Link
          href="/"
          className="group inline-flex items-center gap-2.5 px-5 py-2.5 rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-[var(--color-accent)]/30 transition-colors duration-200 font-medium text-sm shrink-0"
        >
          <ArrowLeft size={16} className="text-[var(--color-accent)] group-hover:-translate-x-0.5 transition-transform duration-200" />
          <span className="text-[var(--color-text-muted)] group-hover:text-[var(--color-text)] transition-colors">Thư Viện</span>
        </Link>
      </div>

      {/* Continue reading section */}
      <ContinueReadingSection stories={storyMetas} />

      {books.length === 0 && (
        <div className="p-10 rounded-2xl text-center border border-dashed border-[var(--color-border)]">
          <p className="text-[var(--color-text-muted)] text-lg">
            Chưa có file EPUB nào. Thêm file{" "}
            <code className="bg-black/30 px-1.5 py-0.5 rounded text-[var(--color-accent)]">
              .epub
            </code>{" "}
            vào thư mục{" "}
            <code className="bg-black/30 px-1.5 py-0.5 rounded text-[var(--color-accent)]">
              epub/
            </code>
            .
          </p>
        </div>
      )}

      {books.length > 0 && (
        <>
          {/* Section header */}
          <div className="flex items-center gap-3 mb-6">
            <span className="w-2 h-2 rounded-full bg-[var(--color-accent)]" />
            <span className="text-xs font-bold text-[var(--color-text-muted)] uppercase tracking-[0.18em]">
              Tất cả sách
            </span>
            <span className="text-[var(--color-accent)] text-xs opacity-60 ml-auto">
              {storyMetas.length} tác phẩm
            </span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-5 md:gap-5">
            {storyMetas.map((meta) => {
              const gradient = getGradientFromString(meta.title);
              return (
                <Link
                  key={meta.slug}
                  href={meta.detailHref}
                  className="group block relative aspect-[2/3] rounded-2xl overflow-hidden
                    border border-[var(--color-border)] hover:border-[var(--color-accent)]/40
                    hover:-translate-y-1 active:scale-[0.98] transition-all duration-200
                    focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]/60"
                >
                  <div className={`absolute inset-0 bg-gradient-to-br ${gradient}`} />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/60 via-black/15 to-transparent" />

                  <div className="relative z-20 h-full flex flex-col p-3.5">
                    <div className="flex-1 flex items-center justify-center">
                      <h2 className="font-serif font-bold text-center text-white/95 drop-shadow-[0_2px_8px_rgba(0,0,0,0.9)] text-base md:text-lg leading-snug line-clamp-4">
                        {meta.title}
                      </h2>
                    </div>
                    <div className="mt-auto pt-3 flex justify-center">
                      <span className="inline-flex items-center bg-black/40 text-white/90 text-[11px] font-bold tracking-wide px-2.5 py-1 rounded-full">
                        {meta.totalChapters > 0 ? `${meta.totalChapters} CH` : "MỞ"}
                      </span>
                    </div>
                  </div>

                  <CardProgressOverlay
                    slug={meta.slug}
                    totalChapters={meta.totalChapters}
                  />
                </Link>
              );
            })}
          </div>
        </>
      )}
    </main>
  );
}
