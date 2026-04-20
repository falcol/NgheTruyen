import fs from "fs";
import path from "path";

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

  function listStories(): string[] {
    if (!fs.existsSync(dataDir)) return [];
    return fs
      .readdirSync(dataDir)
      .filter((d) => fs.statSync(path.join(dataDir, d)).isDirectory());
  }

  function getChapterIndex(slug: string): ChapterMeta[] {
    const filePath = path.join(dataDir, slug, "chapters_index.json");
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  }

  function getStoryMetadata(slug: string): StoryMetadata | null {
    const filePath = path.join(dataDir, slug, "metadata.json");
    if (!fs.existsSync(filePath)) return null;
    return JSON.parse(fs.readFileSync(filePath, "utf-8"));
  }

  function getStoryTitle(slug: string): string {
    return getStoryMetadata(slug)?.story_title || slug;
  }

  function getChapter(slug: string, chapterIdx: number): Chapter | null {
    // Find position in index first — chapter indices may not start at 0
    const index = getChapterIndex(slug);
    const position = index.findIndex((ch) => ch.index === chapterIdx);
    if (position === -1) return null;

    // Calculate volume from position, not from index
    const volNum = Math.floor(position / 50) + 1;
    const storyDir = path.join(dataDir, slug);
    if (!fs.existsSync(storyDir)) return null;

    const files = fs.readdirSync(storyDir);
    const prefix = `vol-${String(volNum).padStart(3, "0")}-`;
    const volFile = files.find(
      (f) => f.startsWith(prefix) && f.endsWith(".json")
    );
    if (!volFile) return null;

    const volData: Volume = JSON.parse(
      fs.readFileSync(path.join(storyDir, volFile), "utf-8")
    );
    return volData.chapters.find((c) => c.index === chapterIdx) || null;
  }

  function getTotalChapters(slug: string): number {
    const index = getChapterIndex(slug);
    if (index.length === 0) return 0;
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

// Default instance for production use
const defaultData = makeDataDir(
  path.relative(process.cwd(), path.join("public", "data", "truyenqq"))
);

export const listStories = defaultData.listStories;
export const getChapterIndex = defaultData.getChapterIndex;
export const getStoryMetadata = defaultData.getStoryMetadata;
export const getStoryTitle = defaultData.getStoryTitle;
export const getChapter = defaultData.getChapter;
export const getTotalChapters = defaultData.getTotalChapters;
