import { Epub } from "@smoores/epub";
import fs from "fs";
import path from "path";

export interface EpubChapterMeta {
  index: number;
  title: string;
}

export interface EpubChapter extends EpubChapterMeta {
  paragraphs: string[];
}

export interface EpubBookMeta {
  filename: string;
  title: string;
  chapters: EpubChapterMeta[];
}

const EPUB_DIR = path.join(process.cwd(), "..", "epub");
const MAX_CACHE = 3;

interface CachedMeta {
  meta: EpubBookMeta;
  spineIds: string[];
}

const epubCache = new Map<string, Epub>();
const metaCache = new Map<string, CachedMeta>();

function evictOldest() {
  if (epubCache.size <= MAX_CACHE) return;
  const oldest = epubCache.keys().next().value;
  if (oldest === undefined) return;
  const oldEpub = epubCache.get(oldest);
  oldEpub?.close().catch(() => {});
  epubCache.delete(oldest);
  metaCache.delete(oldest);
}

async function getEpub(filename: string): Promise<Epub | null> {
  const cached = epubCache.get(filename);
  if (cached) return cached;
  const filepath = path.join(EPUB_DIR, filename);
  if (!fs.existsSync(filepath)) return null;
  const epub = await Epub.from(filepath);
  epubCache.set(filename, epub);
  evictOldest();
  return epub;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function isManifestItem(m: any): m is { id: string; href: string; properties?: string[] } {
  return m && typeof m.id === "string";
}

async function parseTocTitles(epub: Epub): Promise<Map<string, string>> {
  const titles = new Map<string, string>();
  const manifest = await epub.getManifest();
  const navEntry = Object.values(manifest).find(
    (m) => isManifestItem(m) && m.properties?.includes("nav"),
  );
  if (!navEntry || !isManifestItem(navEntry)) return titles;

  const raw = await epub.readItemContents(navEntry.id);
  const html = Buffer.from(raw as Uint8Array).toString("utf-8");
  const linkRegex = /<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;
  let match;
  while ((match = linkRegex.exec(html)) !== null) {
    const href = decodeURIComponent(match[1].split("#")[0]);
    const title = match[2].replace(/<[^>]+>/g, "").trim();
    if (href && title && !titles.has(href)) titles.set(href, title);
  }
  return titles;
}

async function loadMeta(filename: string): Promise<CachedMeta | null> {
  const cached = metaCache.get(filename);
  if (cached) return cached;

  const epub = await getEpub(filename);
  if (!epub) return null;

  const bookTitle = (await epub.getTitle()) || filename.replace(".epub", "");
  const spine = await epub.getSpineItems();
  const tocTitles = await parseTocTitles(epub);

  const chapters: EpubChapterMeta[] = [];
  const spineIds: string[] = [];

  for (let i = 0; i < spine.length; i++) {
    const item = spine[i];
    const title =
      tocTitles.get(item.href) ||
      tocTitles.get(decodeURIComponent(item.href)) ||
      `Chương ${i + 1}`;
    chapters.push({ index: i, title });
    spineIds.push(item.id);
  }

  const result: CachedMeta = {
    meta: { filename, title: bookTitle, chapters },
    spineIds,
  };
  metaCache.set(filename, result);
  return result;
}

export function listEpubFiles(): string[] {
  if (!fs.existsSync(EPUB_DIR)) return [];
  return fs.readdirSync(EPUB_DIR).filter((f) => f.endsWith(".epub"));
}

export async function getEpubMeta(
  filename: string,
): Promise<EpubBookMeta | null> {
  const cached = await loadMeta(filename);
  return cached?.meta ?? null;
}

export async function getEpubChapters(
  filename: string,
): Promise<EpubChapterMeta[] | null> {
  const meta = await getEpubMeta(filename);
  return meta?.chapters ?? null;
}

export async function getEpubChapter(
  filename: string,
  chapterIdx: number,
): Promise<EpubChapter | null> {
  const cached = await loadMeta(filename);
  if (!cached) return null;

  const spineId = cached.spineIds[chapterIdx];
  if (spineId === undefined) return null;

  const epub = await getEpub(filename);
  if (!epub) return null;

  const text = await epub.readXhtmlItemContents(spineId, "text");
  const chapterTitle = cached.meta.chapters[chapterIdx].title;

  // Deduplicate title from content (EPUB often repeats it as first line)
  const paragraphs = text
    .split("\n")
    .map((l) => l.trim())
    .filter((l) => l && l !== chapterTitle);

  return {
    index: chapterIdx,
    title: chapterTitle,
    paragraphs,
  };
}
