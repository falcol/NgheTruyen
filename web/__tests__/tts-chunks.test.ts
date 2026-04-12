import { describe, expect, it } from "vitest";
import { buildTTSChunks, findChunkIndexForParagraph } from "@/lib/tts-chunks";

describe("tts chunking", () => {
  it("keeps chunks inside the same paragraph", () => {
    const chunks = buildTTSChunks([
      "Xin chao.",
      "Day la doan ngan.",
      "Doan nay cung ngan.",
      "Mot doan dai hon mot chut de chunk duoc gop lai tu nhieu cau nho va tranh viec goi api qua nhieu lan.",
    ]);

    expect(chunks[0]).toMatchObject({
      startParagraphIdx: 0,
      endParagraphIdx: 0,
    });
    expect(chunks[1]).toMatchObject({
      startParagraphIdx: 1,
      endParagraphIdx: 1,
    });
  });

  it("finds the chunk containing a paragraph", () => {
    const chunks = buildTTSChunks([
      "Cau mot. Cau hai.",
      "Cau ba.",
      "Cau bon. Cau nam.",
    ]);

    expect(findChunkIndexForParagraph(chunks, 0)).toBe(0);
    expect(findChunkIndexForParagraph(chunks, 1)).toBe(1);
    expect(findChunkIndexForParagraph(chunks, 99)).toBe(-1);
  });
});
