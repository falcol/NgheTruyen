import Link from "next/link";
import { listEpubSummaries } from "@/lib/epub";
import { getGradientFromString } from "@/lib/color";

export const revalidate = 3600;

export default function EpubListPage() {
  const books = listEpubSummaries();

  return (
    <main className="max-w-5xl mx-auto px-4 py-12 md:py-16">
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-6 mb-12 border-b border-white/5 pb-6">
        <div>
          <h1 className="text-3xl md:text-5xl font-extrabold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-[var(--color-accent)] to-purple-400 drop-shadow-sm mb-2">
            Kho EPUB Cá Nhân
          </h1>
          <p className="text-[var(--color-text-muted)] font-medium">Sách chất lượng cao của bạn</p>
        </div>
        <Link
          href="/"
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl glass-panel hover:bg-white/10 transition-all font-medium group text-sm"
        >
          <span className="group-hover:-translate-x-1 transition-transform">←</span>
          <span>Thư Viện Nghe</span>
        </Link>
      </div>

      {books.length === 0 && (
        <div className="glass-panel p-10 rounded-3xl text-center border-dashed">
          <div className="text-4xl mb-4 opacity-50">📭</div>
          <p className="text-[var(--color-text-muted)] text-lg">
            Chưa có file EPUB nào. Thêm file .epub vào thư mục <code className="bg-black/30 px-1.5 py-0.5 rounded text-[var(--color-accent)]">epub/</code>.
          </p>
        </div>
      )}

      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4 md:gap-6">
        {books.map((book) => {
          const gradient = getGradientFromString(book.title || book.filename);
          
          return (
            <Link
              key={book.filename}
              href={`/epub/${encodeURIComponent(book.filename)}`}
              className="group block relative aspect-[2/3] rounded-xl overflow-hidden glass-panel shadow-[0_8px_30px_rgba(0,0,0,0.5)] hover:shadow-[0_15px_40px_rgba(56,189,248,0.2)] transition-all duration-500 hover:-translate-y-2 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
            >
              <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-90 group-hover:opacity-100 transition-opacity duration-500`}></div>
              <div className="absolute inset-0 bg-black/30 group-hover:bg-black/10 transition-colors duration-500"></div>
              
              {/* Book spine lighting effect */}
              <div className="absolute left-0 top-0 bottom-0 w-3 bg-gradient-to-r from-white/20 to-transparent z-10 pointer-events-none"></div>
              <div className="absolute left-0 top-0 bottom-0 w-[1px] bg-white/40 z-10 pointer-events-none"></div>
              <div className="absolute left-1.5 top-0 bottom-0 w-[1px] bg-black/20 z-10 pointer-events-none"></div>
              
              <div className="relative z-20 h-full flex flex-col p-4">
                <div className="flex-1 flex items-center justify-center">
                  <h2 className="font-serif font-bold text-center text-white/95 drop-shadow-[0_2px_4px_rgba(0,0,0,0.8)] text-lg md:text-xl leading-snug line-clamp-4">
                    {book.title || book.filename}
                  </h2>
                </div>
                <div className="mt-auto text-center border-t border-white/20 pt-3 relative">
                  <div className="absolute -top-[1px] left-1/4 right-1/4 h-[1px] bg-gradient-to-r from-transparent via-white/50 to-transparent"></div>
                  <span className="inline-block bg-black/40 backdrop-blur-md px-3 py-1 rounded-full text-[10px] md:text-xs font-bold text-white/90 uppercase tracking-widest border border-white/10 shadow-inner">
                    {book.chapterCount != null ? `${book.chapterCount} CH` : "MỞ..."}
                  </span>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </main>
  );
}
