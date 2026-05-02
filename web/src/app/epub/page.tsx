import Link from "next/link";
import { listEpubFiles, getEpubMeta } from "@/lib/epub";

export const dynamic = "force-dynamic";

export default async function EpubListPage() {
  const files = listEpubFiles();
  const books = await Promise.all(
    files.map(async (filename) => {
      const meta = await getEpubMeta(filename);
      return {
        filename,
        title: meta?.title || filename.replace(".epub", ""),
        chapterCount: meta?.chapters.length ?? 0,
      };
    })
  );

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
            <div className="text-sm text-(--color-text-muted) mt-1">
              {book.chapterCount} chương · {book.filename}
            </div>
          </Link>
        ))}
      </div>
    </main>
  );
}
