"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export default function TopNav() {
  const pathname = usePathname();
  const isLibraryActive = pathname === "/" || pathname.startsWith("/story/");
  const isEpubActive = pathname.startsWith("/epub");

  return (
    <header className="fixed top-0 left-0 right-0 z-50 smart-header [padding-top:env(safe-area-inset-top)]">
      <div className="glass-panel border-b border-[var(--color-border)]">
        <nav className="max-w-5xl mx-auto px-4 h-14 flex items-center justify-between gap-4">
          {/* Logo */}
          <Link href="/" className="flex items-center gap-2.5 group shrink-0">
            {/* Bookmark-shaped icon */}
            <div
              className="w-7 h-9 rounded-t-sm relative flex items-center justify-center overflow-hidden shrink-0
                bg-gradient-to-b from-[var(--color-accent)] to-[var(--color-accent-strong)]
                shadow-[inset_0_1px_0_rgba(255,255,255,0.2)] group-hover:shadow-[0_0_14px_color-mix(in_srgb,var(--color-accent)_45%,transparent)] transition-shadow duration-300"
              style={{
                clipPath: "polygon(0 0, 100% 0, 100% 80%, 50% 100%, 0 80%)"
              }}
            >
              <span className="text-[var(--color-bg)] text-xs font-black z-10 tracking-tighter -mt-1">N</span>
            </div>
            <div className="hidden sm:flex flex-col leading-none gap-0.5">
              <span
                style={{ fontFamily: "var(--font-ui-serif)" }}
                className="font-bold text-[15px] text-[var(--color-text)] group-hover:text-[var(--color-accent)] transition-colors duration-300 leading-none"
              >
                Nghe<span className="text-[var(--color-accent)]">Truyện</span>
              </span>
              <span className="text-[8px] tracking-[0.2em] uppercase text-[var(--color-text-dim)] leading-none">
                Đọc Sách
              </span>
            </div>
          </Link>

          {/* Nav links */}
          <div className="flex items-center gap-1">
            <Link
              href="/"
              className={`relative px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 min-h-[44px] flex items-center justify-center ${
                isLibraryActive
                  ? "bg-[var(--color-accent)]/15 text-[var(--color-accent)] shadow-[0_0_12px_color-mix(in_srgb,var(--color-accent)_20%,transparent)]"
                  : "text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-text)]"
              }`}
            >
              Thư Viện
            </Link>
            <Link
              href="/epub"
              className={`relative px-4 py-2.5 rounded-xl text-sm font-medium transition-all duration-300 min-h-[44px] flex items-center justify-center ${
                isEpubActive
                  ? "bg-[var(--color-accent)]/15 text-[var(--color-accent)] shadow-[0_0_12px_color-mix(in_srgb,var(--color-accent)_20%,transparent)]"
                  : "text-[var(--color-text-muted)] hover:bg-white/5 hover:text-[var(--color-text)]"
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
