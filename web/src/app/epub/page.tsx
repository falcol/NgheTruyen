import Link from "next/link";
import { listEpubSummaries } from "@/lib/epub";

export const revalidate = 3600;

export default function EpubListPage() {
  const books = listEpubSummaries();

  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <Link
        href="/"
        className="text-sm text-(--color-text-muted) hover:text-(--color-accent) mb-4 inline-block"
      >
        ← Trang chủ
      </Link>

      <h1 className="text-2xl font-bold mb-6">EPUB</h1>

      {books.length === 0 && (
        <p className="text-(--color-text-muted)">
          Chưa có file EPUB nào. Thêm file .epub vào thư mục <code>epub/</code>.
        </p>
      )}

      <div className="space-y-3">
        {books.map((book) => (
          <Link
            key={book.filename}
            href={`/epub/${encodeURIComponent(book.filename)}`}
            className="block p-4 rounded-lg bg-(--color-surface) hover:bg-(--color-surface)/80 transition-colors"
          >
            <div className="font-semibold text-lg truncate">{book.title}</div>
            <p className="text-sm text-(--color-text-muted) mt-1">
              {book.chapterCount != null
                ? `${book.chapterCount} chương`
                : "Mở để tải mục lục"}
              {" · "}
              {book.filename}
            </p>
          </Link>
        ))}
      </div>
    </main>
  );
}
