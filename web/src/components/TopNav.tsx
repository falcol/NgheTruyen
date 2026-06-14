import Link from "next/link";

export default function TopNav() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 smart-header">
      <div className="glass-panel border-b border-[var(--color-border)]">
        <nav className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group shrink-0">
            <div className="relative w-8 h-8 rounded-xl bg-gradient-to-br from-[var(--color-accent)] via-rose-500 to-[var(--color-accent-dim)] flex items-center justify-center shadow-[0_0_16px_rgba(232,121,160,0.4)] group-hover:shadow-[0_0_24px_rgba(232,121,160,0.6)] transition-all duration-300 group-hover:scale-110">
              <span className="text-white text-xs font-black tracking-tighter">N</span>
              {/* Inner shine */}
              <div className="absolute inset-0 rounded-xl bg-gradient-to-br from-white/20 to-transparent pointer-events-none" />
            </div>
            <div className="hidden sm:block">
              <span className="font-bold text-sm tracking-wide text-[var(--color-text)] group-hover:text-[var(--color-accent)] transition-colors duration-200">
                Nghe<span className="text-[var(--color-accent)]">Truyen</span>
              </span>
            </div>
          </Link>

          {/* Nav links */}
          <div className="flex items-center gap-1">
            <Link
              href="/"
              className="relative px-3 py-1.5 rounded-lg text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-white/5 transition-all duration-200"
            >
              Thư Viện
            </Link>
            <Link
              href="/epub"
              className="relative px-3 py-1.5 rounded-lg text-sm font-medium text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-white/5 transition-all duration-200"
            >
              EPUB
            </Link>
          </div>
        </nav>
      </div>
    </header>
  );
}
