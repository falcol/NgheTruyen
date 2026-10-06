import { afterEach, describe, expect, it, vi } from "vitest";
import { loadProgress } from "@/hooks/useProgress";
import {
  durableChapterKey,
  forgetChapterMemory,
  loadChapterContent,
  rememberDurableChapter,
  type ChapterPayload,
} from "@/lib/chapter-prefetch";
import { resumeReaderChapter } from "@/lib/reader-resume";

const crawlUrl = "/api/chapter/durable-story/4";
const epubUrl = "/epub-cache/abc/ch/00004.json.gz";

function payload(title: string): ChapterPayload {
  return {
    index: 4,
    title,
    paragraphs: [`Đoạn mở của ${title}.`, "Đoạn thứ hai vẫn còn trên máy."],
  };
}

function seedScroll(slug: string, chapterIdx: number, scrollY: number) {
  localStorage.setItem(
    `progress-${slug}`,
    JSON.stringify({
      chapterIdx,
      scrollByChapter: { [String(chapterIdx)]: scrollY },
      timestamp: 1,
    }),
  );
}

describe("durable chapter resume", () => {
  afterEach(() => {
    forgetChapterMemory();
    localStorage.clear();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("returns stored crawl and epub paragraphs plus scroll when the body request is blocked", async () => {
    const fetchMock = vi.fn(() => Promise.reject(new Error("offline")));
    vi.stubGlobal("fetch", fetchMock);

    const cases = [
      { slug: "durable-story", url: crawlUrl, scrollY: 640, title: "Chương 5: Lửa" },
      { slug: "epub-book.epub", url: epubUrl, scrollY: 880, title: "Chương 5: EPUB" },
    ];

    for (const item of cases) {
      rememberDurableChapter(item.url, payload(item.title));
      seedScroll(item.slug, 4, item.scrollY);
    }
    forgetChapterMemory();

    for (const item of cases) {
      const loaded = await loadChapterContent(item.url, new AbortController().signal);
      expect(loaded.paragraphs).toEqual(payload(item.title).paragraphs);
      const resume = resumeReaderChapter(item.slug, 4, item.url);
      expect(resume.paragraphs).toEqual(payload(item.title).paragraphs);
      expect(resume.scrollY).toBe(item.scrollY);
      expect(loadProgress(item.slug)?.scrollByChapter["4"]).toBe(item.scrollY);
    }

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("loads a cache miss from the network", async () => {
    const network = payload("Từ mạng");
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify(network), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const url = "/api/chapter/miss-story/1";
    const loaded = await loadChapterContent(url, new AbortController().signal);
    expect(loaded.paragraphs).toEqual(network.paragraphs);
    expect(fetchMock).toHaveBeenCalledWith(url, expect.anything());

    forgetChapterMemory();
    const resume = resumeReaderChapter("miss-story", 1, url);
    expect(resume.paragraphs).toEqual(network.paragraphs);
  });

  it("falls through to the network when the stored entry is corrupt", async () => {
    const url = "/api/chapter/corrupt-story/2";
    localStorage.setItem(durableChapterKey(url), "{not-json");
    const network = payload("Sau bản hỏng");
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify(network), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const loaded = await loadChapterContent(url, new AbortController().signal);
    expect(loaded.paragraphs).toEqual(network.paragraphs);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(resumeReaderChapter("corrupt-story", 2, url).scrollY).toBe(0);
  });
});
