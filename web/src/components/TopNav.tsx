import Link from "next/link";

export default function TopNav() {
  return (
    <header className="fixed top-0 left-0 right-0 z-50 smart-header">
      <div className="glass-panel border-b border-white/5">
        <nav className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          <Link href="/" className="flex items-center gap-2.5 group shrink-0">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-[var(--color-accent)] to-purple-500 flex items-center justify-center shadow-[0_0_12px_rgba(56,189,248,0.3)] group-hover:shadow-[0_0_18px_rgba(56,189,248,0.5)] transition-shadow">
              <span className="text-black text-xs font-black">N</span>
            </div>
            <span className="font-bold text-white/90 text-sm tracking-wide group-hover:text-white transition-colors hidden sm:block">
              NgheTruyen
            </span>
          </Link>
          <div className="flex items-center gap-1">
            <Link href="/" className="px-3 py-1.5 rounded-lg text-sm font-medium text-[var(--color-text-muted)] hover:text-white hover:bg-white/8 transition-all">
              Thư Viện
            </Link>
            <Link href="/epub" className="px-3 py-1.5 rounded-lg text-sm font-medium text-[var(--color-text-muted)] hover:text-white hover:bg-white/8 transition-all">
              EPUB
            </Link>
          </div>
        </nav>
      </div>
    </header>
  );
}
