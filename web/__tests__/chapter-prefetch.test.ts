import { afterEach, describe, expect, it, vi } from "vitest";
import { loadChapterContent } from "@/lib/chapter-prefetch";

// Reproduces the shared-inflight race: two readers request the SAME chapter URL,
// the first one's AbortController fires (component unmounts / navigates away), and
// the second reader — whose own signal never aborted — must still receive content.
// Before the fix, loadChapterContent handed both callers the SAME fetch promise,
// bound to the first caller's signal, so aborting the first rejected the second too.
describe("loadChapterContent shared-inflight abort isolation", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function mockSlowFetch() {
    // Resolves after a tick UNLESS the caller's signal aborts first.
    vi.stubGlobal(
      "fetch",
      vi.fn((_url: string, opts?: { signal?: AbortSignal }) => {
        const signal = opts?.signal;
        return new Promise<Response>((resolve, reject) => {
          if (signal) {
            signal.addEventListener("abort", () =>
              reject(new DOMException("The operation was aborted.", "AbortError")),
            );
          }
          setTimeout(
            () =>
              resolve(
                new Response(
                  JSON.stringify({ index: 0, title: "t", paragraphs: ["hello"] }),
                  { status: 200 },
                ),
              ),
            10,
          );
        });
      }),
    );
  }

  it("does not fail a second consumer when the first consumer aborts", async () => {
    mockSlowFetch();
    const url = "/api/chapter/race-story/0"; // unique url => fresh inflight entry

    const c1 = new AbortController();
    const c2 = new AbortController();

    const p1 = loadChapterContent(url, c1.signal);
    c1.abort(); // first reader navigates away mid-fetch
    const p2 = loadChapterContent(url, c2.signal); // second reader, still on the page

    await expect(p1).rejects.toThrow(); // first is expected to reject (it aborted)

    // The second reader never aborted, so it must receive the chapter payload.
    const payload = await p2;
    expect(payload.paragraphs).toEqual(["hello"]);
  });
});
