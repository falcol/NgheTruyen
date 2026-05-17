import Link from "next/link";

export default function EpubCacheMissing({
  filename,
  chapterIdx,
  backHref,
}: {
  filename: string;
  chapterIdx: number;
  backHref: string;
}) {
  return (
    <main className="max-w-2xl mx-auto px-4 py-8">
      <Link
        href={backHref}
        className="text-sm text-(--color-text-muted) hover:text-(--color-accent) mb-4 inline-block"
      >
        ← Quay lại
      </Link>
      <h1 className="text-xl font-bold mb-2">Chưa có nội dung chương</h1>
      <p className="text-(--color-text-muted) mb-4">
        Chương {chapterIdx + 1} của <span className="truncate">{filename}</span> chưa
        được extract. Trên server chỉ đọc file cache — không parse EPUB khi đọc.
      </p>
      <pre className="text-sm p-3 rounded-lg bg-(--color-surface) overflow-x-auto">
        cd web{"\n"}npm run epub:cache
      </pre>
    </main>
  );
}
