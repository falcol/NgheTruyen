import fs from "fs";
import path from "path";
import zlib from "zlib";

// In-memory caches for static files
const volumeCache = new Map<string, Volume>();
const indexCache = new Map<string, ChapterMeta[]>();
const metadataCache = new Map<string, StoryMetadata>();
const volFileCache = new Map<string, string[]>();
const MAX_VOLUME_CACHE_SIZE = 10;

// Read .json or .json.gz transparently. Prefers .gz when both exist.
// Uses try/catch instead of existsSync to avoid redundant syscalls.
function readJsonAny<T>(filePath: string): T | null {
  try {
    const buf = fs.readFileSync(filePath + ".gz");
    return JSON.parse(zlib.gunzipSync(buf).toString("utf-8")) as T;
  } catch { /* .gz not found */ }
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8")) as T;
  } catch { return null; }
}

function existsAny(filePath: string): boolean {
  return fs.existsSync(filePath) || fs.existsSync(filePath + ".gz");
}

export interface ChapterMeta {
  index: number;
  title: string;
}

export interface StoryMetadata {
  story_title: string;
}

export interface Chapter extends ChapterMeta {
  paragraphs: string[];
}

export interface Volume {
  volume: number;
  chapterRange: [number, number];
  chapters: Chapter[];
}

export function makeDataDir(baseDir: string) {
  const dataDir = path.join(process.cwd(), baseDir);

  function isSafeSlug(slug: string): boolean {
    return !slug.includes("/") && !slug.includes("\\") && !slug.includes("..");
  }

  function listStories(): string[] {
    if (!fs.existsSync(dataDir)) return [];
    return fs
      .readdirSync(dataDir)
      .filter((d) => {
        const storyDir = path.join(dataDir, d);
        if (!fs.statSync(storyDir).isDirectory()) return false;

        // Only expose story folders that contain expected story data files
        // (either plain or gzipped variant).
        const hasChapterIndex = existsAny(path.join(storyDir, "chapters_index.json"));
        const hasMetadata = existsAny(path.join(storyDir, "metadata.json"));
        return hasChapterIndex || hasMetadata;
      });
  }

  function getChapterIndex(slug: string): ChapterMeta[] | null {
    if (!isSafeSlug(slug)) return null;
    const filePath = path.join(dataDir, slug, "chapters_index.json");
    
    const cached = indexCache.get(filePath);
    if (cached) return cached;

    const data = readJsonAny<ChapterMeta[]>(filePath);
    if (data) {
      indexCache.set(filePath, data);
    }
    return data;
  }

  function getStoryMetadata(slug: string): StoryMetadata | null {
    if (!isSafeSlug(slug)) return null;
    const filePath = path.join(dataDir, slug, "metadata.json");

    const cached = metadataCache.get(filePath);
    if (cached) return cached;

    const data = readJsonAny<StoryMetadata>(filePath);
    if (data) {
      metadataCache.set(filePath, data);
    }
    return data;
  }

  function getStoryTitle(slug: string): string {
    if (!isSafeSlug(slug)) return slug;
    return getStoryMetadata(slug)?.story_title || slug;
  }

  function getChapter(slug: string, chapterIdx: number): Chapter | null {
    if (!isSafeSlug(slug)) return null;

    // Find position in index first — chapter indices may not start at 0
    const index = getChapterIndex(slug);
    if (!index) return null;
    const position = index.findIndex((ch) => ch.index === chapterIdx);
    if (position === -1) return null;

    // Calculate volume from position, not from index
    // Volumes may have fewer than 50 chapters, so search neighbors on miss
    const volNum = Math.floor(position / 50) + 1;
    const storyDir = path.join(dataDir, slug);
    if (!fs.existsSync(storyDir)) return null;

    // Match both vol-NNN-*.json and vol-NNN-*.json.gz (cached per storyDir)
    let files = volFileCache.get(storyDir);
    if (!files) {
      files = fs
        .readdirSync(storyDir)
        .filter(
          (f) =>
            f.startsWith("vol-") &&
            (f.endsWith(".json") || f.endsWith(".json.gz"))
        );
      volFileCache.set(storyDir, files);
    }

    for (let delta = 0; delta <= 2; delta++) {
      const candidates =
        delta === 0 ? [volNum] : [volNum + delta, volNum - delta];
      for (const tryVol of candidates) {
        if (tryVol < 1) continue;
        const prefix = `vol-${String(tryVol).padStart(3, "0")}-`;
        const volFile = files.find((f) => f.startsWith(prefix));
        if (!volFile) continue;
        
        // Strip .gz suffix so readJsonAny can probe both variants
        const logicalPath = path
          .join(storyDir, volFile)
          .replace(/\.gz$/, "");
        
        let volData = volumeCache.get(logicalPath);
        if (!volData) {
          volData = readJsonAny<Volume>(logicalPath) || undefined;
          if (volData) {
            // Evict if cache exceeds max size
            if (volumeCache.size >= MAX_VOLUME_CACHE_SIZE) {
              const oldestKey = volumeCache.keys().next().value;
              if (oldestKey) volumeCache.delete(oldestKey);
            }
            volumeCache.set(logicalPath, volData);
          }
        }

        if (!volData) continue;
        const chapter = volData.chapters.find((c) => c.index === chapterIdx);
        if (chapter) return chapter;
      }
    }
    return null;
  }

  function getTotalChapters(slug: string): number {
    if (!isSafeSlug(slug)) return 0;
    const index = getChapterIndex(slug);
    if (!index || index.length === 0) return 0;
    return index[index.length - 1].index + 1;
  }

  return {
    listStories,
    getChapterIndex,
    getStoryMetadata,
    getStoryTitle,
    getChapter,
    getTotalChapters,
  };
}

// Aggregate across all source directories (truyenqq, metruyenchu, metruyencv, ...)
function makeAllSources() {
  const baseDir = path.join(process.cwd(), "public", "data");
  
  if (!fs.existsSync(baseDir)) {
    const singleInst = makeDataDir(path.join("public", "data"));
    const slugMap = new Map<string, typeof singleInst>();
    
    try {
      singleInst.listStories().forEach((slug) => {
        slugMap.set(slug, singleInst);
      });
    } catch {
      // ignore
    }

    return {
      listStories: () => Array.from(slugMap.keys()),
      getChapterIndex: (slug: string) => slugMap.get(slug)?.getChapterIndex(slug) ?? null,
      getStoryMetadata: (slug: string) => slugMap.get(slug)?.getStoryMetadata(slug) ?? null,
      getStoryTitle: (slug: string) => slugMap.get(slug)?.getStoryTitle(slug) ?? slug,
      getChapter: (slug: string, chapterIdx: number) => slugMap.get(slug)?.getChapter(slug, chapterIdx) ?? null,
      getTotalChapters: (slug: string) => slugMap.get(slug)?.getTotalChapters(slug) ?? 0,
    };
  }

  const sources = fs
    .readdirSync(baseDir)
    .filter((d) => fs.statSync(path.join(baseDir, d)).isDirectory());

  const instances = sources.map((s) =>
    makeDataDir(path.join("public", "data", s))
  );

  const slugMap = new Map<string, typeof instances[number]>();
  instances.forEach((inst) => {
    try {
      inst.listStories().forEach((slug) => {
        slugMap.set(slug, inst);
      });
    } catch {
      // ignore
    }
  });

  function listStories(): string[] {
    return Array.from(slugMap.keys());
  }

  function findInstance(slug: string) {
    return slugMap.get(slug);
  }

  function getChapterIndex(slug: string) {
    return findInstance(slug)?.getChapterIndex(slug) ?? null;
  }
  function getStoryMetadata(slug: string) {
    return findInstance(slug)?.getStoryMetadata(slug) ?? null;
  }
  function getStoryTitle(slug: string) {
    return findInstance(slug)?.getStoryTitle(slug) ?? slug;
  }
  function getChapter(slug: string, chapterIdx: number) {
    return findInstance(slug)?.getChapter(slug, chapterIdx) ?? null;
  }
  function getTotalChapters(slug: string) {
    return findInstance(slug)?.getTotalChapters(slug) ?? 0;
  }

  return {
    listStories,
    getChapterIndex,
    getStoryMetadata,
    getStoryTitle,
    getChapter,
    getTotalChapters,
  };
}

const defaultData = makeAllSources();

export function estimateReadingTime(chapterCount: number): string {
  const minutes = chapterCount * 15;
  if (minutes < 60) return `${minutes} phút`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `~${hours} giờ`;
  const days = Math.round(hours / 8);
  return `~${days} ngày đọc`;
}

export const listStories = defaultData.listStories;
export const getChapterIndex = defaultData.getChapterIndex;
export const getStoryMetadata = defaultData.getStoryMetadata;
export const getStoryTitle = defaultData.getStoryTitle;
export const getChapter = defaultData.getChapter;
export const getTotalChapters = defaultData.getTotalChapters;

