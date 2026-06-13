import Link from "next/link";
import { notFound } from "next/navigation";
import { getEpubMeta } from "@/lib/epub";
import ChapterList from "@/components/ChapterList";
import { getGradientFromString } from "@/lib/color";

export const revalidate = 86400;

export default async function EpubBookPage({
  params,
}: {
  params: Promise<{ filename: string }>;
}) {
  const { filename } = await params;
  const decodedFilename = decodeURIComponent(filename);
  const meta = getEpubMeta(decodedFilename);
  if (!meta) return notFound();

  const readHref = `/epub/${encodeURIComponent(decodedFilename)}/read`;
  const gradient = getGradientFromString(meta.title || meta.filename);

  return (
    <main className="max-w-4xl mx-auto px-4 py-8 md:py-12">
      <Link
        href="/epub"
        className="inline-flex items-center gap-2 px-4 py-2 rounded-xl glass-panel hover:bg-white/10 text-sm text-[var(--color-text-muted)] hover:text-white transition-all mb-8 group font-medium"
      >
        <span className="group-hover:-translate-x-1 transition-transform">←</span> Kho EPUB
      </Link>

      <div className={`relative overflow-hidden rounded-[2rem] mb-12 shadow-2xl glass-panel border border-white/10`}>
        <div className={`absolute inset-0 bg-gradient-to-br ${gradient} opacity-50 mix-blend-overlay`}></div>
        <div className="absolute inset-0 bg-black/50 backdrop-blur-sm"></div>
        
        <div className="relative z-10 p-8 md:p-12 flex flex-col md:flex-row gap-8 items-center md:items-start">
          {/* Big book cover representation */}
          <div className={`w-40 md:w-56 aspect-[2/3] shrink-0 rounded-xl shadow-[0_15px_40px_rgba(0,0,0,0.5)] bg-gradient-to-br ${gradient} relative overflow-hidden flex items-center justify-center p-5 border border-white/10`}>
            <div className="absolute left-0 top-0 bottom-0 w-3 bg-gradient-to-r from-white/20 to-transparent"></div>
            <div className="absolute left-0 top-0 bottom-0 w-[1px] bg-white/40"></div>
            <div className="absolute left-1.5 top-0 bottom-0 w-[1px] bg-black/20"></div>
            <h2 className="font-serif font-bold text-center text-white/95 drop-shadow-[0_4px_6px_rgba(0,0,0,0.8)] text-xl leading-snug line-clamp-6">
              {meta.title || meta.filename}
            </h2>
          </div>

          <div className="flex-1 text-center md:text-left flex flex-col h-full justify-center">
            <h1 className="text-3xl md:text-5xl font-extrabold mb-6 leading-tight text-white/95 drop-shadow-lg break-words">
              {meta.title}
            </h1>
            <div className="flex flex-wrap items-center justify-center md:justify-start gap-3 text-sm text-[var(--color-text-muted)] mb-8">
              <span className="bg-white/10 backdrop-blur-md px-4 py-2 rounded-xl font-bold text-white/90 border border-white/10 shadow-inner tracking-wider">
                {meta.chapters.length} CHƯƠNG
              </span>
              <span className="opacity-70 font-mono text-xs bg-black/20 px-4 py-2 rounded-xl border border-white/5 truncate max-w-full">{meta.filename}</span>
            </div>
            
            <div className="flex justify-center md:justify-start">
              <Link 
                href={`${readHref}?chapter=0`} 
                className="inline-flex items-center gap-3 px-8 py-4 bg-white text-black font-bold rounded-2xl hover:scale-105 transition-all shadow-[0_0_30px_rgba(255,255,255,0.3)] hover:shadow-[0_0_40px_rgba(255,255,255,0.5)] text-lg"
              >
                <span>▶</span> Đọc Từ Đầu
              </Link>
            </div>
          </div>
        </div>
      </div>

      <div className="max-w-2xl mx-auto">
        <h3 className="text-xl font-bold mb-6 flex items-center gap-3 text-white/90">
          <span className="w-8 h-[2px] bg-[var(--color-accent)] rounded-full"></span>
          Mục lục
        </h3>
        <ChapterList
          slug={`epub-${decodedFilename}`}
          chapters={meta.chapters}
          readHref={readHref}
        />
      </div>
    </main>
  );
}
