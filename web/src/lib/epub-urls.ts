import crypto from "crypto";

export function bookCacheKey(filename: string): string {
  return crypto.createHash("sha256").update(filename).digest("hex").slice(0, 32);
}

function withCacheBase(path: string): string {
  if (process.env.NEXT_PUBLIC_EPUB_CACHE_URL) {
    const baseUrl = process.env.NEXT_PUBLIC_EPUB_CACHE_URL.replace(/\/$/, "");
    return `${baseUrl}${path}`;
  }
  return path;
}

export function chapterCacheUrlPath(filename: string, chapterIdx: number): string {
  const idx = String(chapterIdx).padStart(5, "0");
  return withCacheBase(`/epub-cache/${bookCacheKey(filename)}/ch/${idx}.json.gz`);
}

/** Title index for the picker. Fetched after the chapter body can paint. */
export function epubMetaPublicPath(filename: string): string {
  return withCacheBase(`/epub-cache/${bookCacheKey(filename)}.json`);
}

export function epubFilenameFromReaderSlug(slug: string): string | null {
  if (!slug.startsWith("epub-")) return null;
  return slug.slice("epub-".length);
}
