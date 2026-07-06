"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function TopNav() {
  const pathname = usePathname();
  const isLibraryActive = pathname === "/" || pathname.startsWith("/story/");
  const isEpubActive = pathname.startsWith("/epub");

  return (
    <header className="fixed top-0 left-0 right-0 z-50 smart-header">
      <div className="glass-panel border-b border-[var(--color-border)]">
        <nav className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group shrink-0">
            <div className="w-8 h-8 rounded-xl bg-[var(--color-accent)] group-hover:bg-[var(--color-accent-strong)] flex items-center justify-center transition-colors duration-200">
              <span className="text-[var(--color-bg)] text-xs font-black tracking-tighter">N</span>
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
              className={`relative px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-white/5 transition-all duration-200 ${
                isLibraryActive
                  ? "nav-link-active"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
              }`}
            >
              Thư Viện
            </Link>
            <Link
              href="/epub"
              className={`relative px-3 py-1.5 rounded-lg text-sm font-medium hover:bg-white/5 transition-all duration-200 ${
                isEpubActive
                  ? "nav-link-active"
                  : "text-[var(--color-text-muted)] hover:text-[var(--color-text)]"
              }`}
            >
              EPUB
            </Link>
          </div>
        </nav>
      </div>
    </header>
  );
}
