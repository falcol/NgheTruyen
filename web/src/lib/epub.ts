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

type ManifestItem = {
  id: string;
  href: string;
  properties?: string[] | string;
  mediaType?: string;
  "media-type"?: string;
};

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function isManifestItem(m: any): m is ManifestItem {
  return m && typeof m.id === "string" && typeof m.href === "string";
}

function contentsToString(raw: Uint8Array | string): string {
  if (typeof raw === "string") return raw;
  return Buffer.from(raw).toString("utf-8");
}

function normalizeHref(href: string): string {
  return decodeURIComponent(href.split("#")[0]).replace(/\\/g, "/").replace(/^\/+/, "");
}

function decodeHtmlEntities(text: string): string {
  return text
    .replace(/&nbsp;/gi, " ")
    .replace(/&amp;/gi, "&")
    .replace(/&lt;/gi, "<")
    .replace(/&gt;/gi, ">")
    .replace(/&quot;/gi, '"')
    .replace(/&#39;/gi, "'")
    .replace(/&#(\d+);/g, (_, code) => String.fromCodePoint(Number(code)))
    .replace(/&#x([0-9a-f]+);/gi, (_, code) => String.fromCodePoint(parseInt(code, 16)));
}

function normalizeTitleText(text: string): string {
  return text.replace(/\s*:\s*/g, ":").replace(/\s+/g, " ").trim().toLowerCase();
}

function textToParagraphs(text: string, chapterTitle: string): string[] {
  const normalizedTitle = normalizeTitleText(chapterTitle);
  return text
    .split(/\n+/)
    .map((line) => decodeHtmlEntities(line).replace(/\s+/g, " ").trim())
    .filter((line) => line && normalizeTitleText(line) !== normalizedTitle);
}

function xhtmlToParagraphs(html: string, chapterTitle: string): string[] {
  const body = html.match(/<body\b[^>]*>([\s\S]*?)<\/body>/i)?.[1] ?? html;
  const text = body
    .replace(/<script[\s\S]*?<\/script>/gi, "")
    .replace(/<style[\s\S]*?<\/style>/gi, "")
    .replace(/<br\b[^>]*\/?>/gi, "\n")
    .replace(/<\/(p|div|h[1-6]|li|blockquote|section|article)>/gi, "\n")
    .replace(/<[^>]+>/g, "");

  return textToParagraphs(text, chapterTitle);
}

function findTocTitle(titles: Map<string, string>, href: string): string | undefined {
  const normalized = normalizeHref(href);
  return (
    titles.get(normalized) ||
    titles.get(path.basename(normalized)) ||
    titles.get(href) ||
    titles.get(decodeURIComponent(href))
  );
}

async function parseTocTitles(epub: Epub): Promise<Map<string, string>> {
  const titles = new Map<string, string>();
  const manifest = await epub.getManifest();
  const navEntry = Object.values(manifest).find(
    (m) => isManifestItem(m) && m.properties?.includes("nav"),
  );
  const ncxEntry = Object.values(manifest).find(
    (m) =>
      isManifestItem(m) &&
      m.mediaType === "application/x-dtbncx+xml",
  );

  if (navEntry && isManifestItem(navEntry)) {
    const raw = await epub.readItemContents(navEntry.id);
    const html = contentsToString(raw as Uint8Array);
    const linkRegex = /<a[^>]+href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/gi;
    for (const match of html.matchAll(linkRegex)) {
      const href = normalizeHref(match[1]);
      const title = match[2].replace(/<[^>]+>/g, "").trim();
      if (href && title && !titles.has(href)) titles.set(href, title);
    }
  }

  if (titles.size === 0 && ncxEntry && isManifestItem(ncxEntry)) {
    const raw = await epub.readItemContents(ncxEntry.id);
    const xml = contentsToString(raw as Uint8Array);
    const navPointRegex = /<navPoint\b[\s\S]*?<navLabel>\s*<text>([\s\S]*?)<\/text>\s*<\/navLabel>[\s\S]*?<content[^>]+src="([^"]+)"/gi;
    for (const match of xml.matchAll(navPointRegex)) {
      const title = decodeHtmlEntities(match[1].replace(/<[^>]+>/g, "").trim());
      const href = normalizeHref(match[2]);
      if (href && title && !titles.has(href)) titles.set(href, title);
    }
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
  const shouldUseToc = tocTitles.size > 0;

  const chapters: EpubChapterMeta[] = [];
  const spineIds: string[] = [];

  for (let i = 0; i < spine.length; i++) {
    const item = spine[i];
    const title = findTocTitle(tocTitles, item.href);
    if (shouldUseToc && !title) continue;

    chapters.push({ index: chapters.length, title: title || `Chương ${chapters.length + 1}` });
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

  const chapterTitle = cached.meta.chapters[chapterIdx].title;
  const text = await epub.readXhtmlItemContents(spineId, "text");

  // Deduplicate title from content (EPUB often repeats it as first line).
  let paragraphs = textToParagraphs(text, chapterTitle);
  if (paragraphs.length === 0) {
    const raw = await epub.readItemContents(spineId);
    paragraphs = xhtmlToParagraphs(contentsToString(raw as Uint8Array), chapterTitle);
  }

  return {
    index: chapterIdx,
    title: chapterTitle,
    paragraphs,
  };
}
