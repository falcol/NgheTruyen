import Link from "next/link";

export default function NotFound() {
  return (
    <main className="max-w-2xl mx-auto px-4 py-20 md:py-28 text-center">
      <p className="text-[10px] font-bold tracking-[0.3em] uppercase text-[var(--color-accent)] mb-4 opacity-80">
        <span
          aria-hidden="true"
          className="mr-1 inline-block w-1.5 h-1.5 rounded-full bg-[var(--color-accent)] align-middle"
        />
        Không tìm thấy
      </p>
      <h1
        style={{ fontFamily: "var(--font-ui-serif)" }}
        className="text-5xl md:text-7xl font-bold tracking-tight mb-4 text-[var(--color-text)]"
      >
        404
      </h1>
      <p className="text-[var(--color-text-muted)] text-sm leading-relaxed max-w-xs mx-auto mb-8">
        Trang hoặc chương bạn tìm không tồn tại, hoặc đã được di chuyển.
      </p>
      <div className="flex items-center justify-center gap-3">
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-5 py-3 min-h-[44px] rounded-xl bg-[var(--color-accent)] text-[var(--color-bg)] font-bold text-sm hover:bg-[var(--color-accent-strong)] hover:-translate-y-0.5 active:scale-[0.98] transition-all duration-200"
        >
          Về Thư Viện
        </Link>
        <Link
          href="/epub"
          className="inline-flex items-center gap-2 px-5 py-3 min-h-[44px] rounded-xl bg-[var(--color-surface)] border border-[var(--color-border)] hover:border-[var(--color-accent)]/50 text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] transition-all duration-200"
        >
          Kho EPUB
        </Link>
      </div>
    </main>
  );
}
