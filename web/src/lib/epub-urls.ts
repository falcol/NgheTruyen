import crypto from "crypto";

export function bookCacheKey(filename: string): string {
  return crypto.createHash("sha256").update(filename).digest("hex").slice(0, 32);
}

export function chapterCacheUrlPath(filename: string, chapterIdx: number): string {
  const idx = String(chapterIdx).padStart(5, "0");
  return `/epub-cache/${bookCacheKey(filename)}/ch/${idx}.json.gz`;
}

export function epubFilenameFromReaderSlug(slug: string): string | null {
  if (!slug.startsWith("epub-")) return null;
  return slug.slice("epub-".length);
}
