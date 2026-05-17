/**
 * EPUB parsing — only for build/CLI (npm run epub:cache).
 * Do not import from app routes; use @/lib/epub for runtime reads.
 */
import { Epub } from "@smoores/epub";
import fs from "fs";
import path from "path";
import {
  hasChapterCache,
  isMetaCacheCurrent,
  readMetaCache,
  writeCacheIndex,
  writeChapterCache,
  writeMetaCache,
  type EpubListSummary,
} from "./epub-cache";
import type { EpubBookMeta, EpubChapter, EpubChapterMeta } from "./epub-types";

const EPUB_DIR = path.join(process.cwd(), "..", "epub");
const META_CACHE_DIR = path.join(process.cwd(), "public", "epub-cache");

interface CachedMeta {
  meta: EpubBookMeta;
  spineIds: string[];
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

async function parseMetaFromEpub(
  filename: string,
  epubPath: string,
  epub: Epub,
): Promise<CachedMeta> {
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

    chapters.push({
      index: chapters.length,
      title: title || `Chương ${chapters.length + 1}`,
    });
    spineIds.push(item.id);
  }

  const meta: EpubBookMeta = { filename, title: bookTitle, chapters };
  writeMetaCache(META_CACHE_DIR, epubPath, filename, meta, spineIds);
  return { meta, spineIds };
}

async function extractChapter(
  cached: CachedMeta,
  chapterIdx: number,
  epub: Epub,
): Promise<EpubChapter | null> {
  const spineId = cached.spineIds[chapterIdx];
  if (spineId === undefined) return null;

  const chapterTitle = cached.meta.chapters[chapterIdx].title;
  const text = await epub.readXhtmlItemContents(spineId, "text");

  let paragraphs = textToParagraphs(text, chapterTitle);
  if (paragraphs.length === 0) {
    const raw = await epub.readItemContents(spineId);
    paragraphs = xhtmlToParagraphs(contentsToString(raw as Uint8Array), chapterTitle);
  }

  return { index: chapterIdx, title: chapterTitle, paragraphs };
}

export function listEpubFiles(): string[] {
  if (!fs.existsSync(EPUB_DIR)) return [];
  return fs.readdirSync(EPUB_DIR).filter((f) => f.endsWith(".epub"));
}

export async function warmEpubFile(filename: string): Promise<EpubListSummary | null> {
  const epubPath = path.join(EPUB_DIR, filename);
  if (!fs.existsSync(epubPath)) {
    console.warn(`  skip (not found): ${filename}`);
    return null;
  }

  const epub = await Epub.from(epubPath);
  try {
    const existing = readMetaCache(META_CACHE_DIR, filename);
    let cached: CachedMeta;
    if (existing && isMetaCacheCurrent(existing, epubPath)) {
      cached = { meta: existing.meta, spineIds: existing.spineIds };
    } else {
      cached = await parseMetaFromEpub(filename, epubPath, epub);
    }

    const total = cached.meta.chapters.length;
    console.log(`  ${filename}: ${total} chapters`);

    for (let i = 0; i < total; i++) {
      if (hasChapterCache(META_CACHE_DIR, filename, i)) continue;

      const chapter = await extractChapter(cached, i, epub);
      if (!chapter) continue;

      writeChapterCache(META_CACHE_DIR, filename, chapter);
      if ((i + 1) % 100 === 0 || i + 1 === total) {
        console.log(`    ${i + 1}/${total}`);
      }
    }

    return {
      filename,
      title: cached.meta.title,
      chapterCount: cached.meta.chapters.length,
    };
  } finally {
    await epub.close().catch(() => {});
  }
}

export async function warmAllEpubCaches(): Promise<void> {
  const summaries: EpubListSummary[] = [];
  for (const filename of listEpubFiles()) {
    const summary = await warmEpubFile(filename);
    if (summary) summaries.push(summary);
  }
  writeCacheIndex(META_CACHE_DIR, summaries);
}
