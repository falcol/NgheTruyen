import { describe, expect, it } from "vitest";
import { buildTTSChunks, findChunkIndexForParagraph } from "@/lib/tts-chunks";

describe("tts chunking", () => {
  it("can merge neighboring paragraphs into larger chunks", () => {
    const chunks = buildTTSChunks([
      "Xin chao.",
      "Day la doan ngan.",
      "Doan nay cung ngan.",
      "Mot doan dai hon mot chut de chunk duoc gop lai tu nhieu cau nho va tranh viec goi api qua nhieu lan.",
    ]);

    expect(chunks[0]).toMatchObject({
      startParagraphIdx: 0,
      endParagraphIdx: 3,
    });
    expect(chunks).toHaveLength(1);
  });

  it("finds the chunk containing a paragraph", () => {
    const chunks = buildTTSChunks([
      "Cau mot. Cau hai. Cau ba. Cau bon.",
      "Cau nam. Cau sau. Cau bay.",
      "Cau tam. Cau chin. Cau muoi.",
    ]);

    expect(findChunkIndexForParagraph(chunks, 0)).toBe(0);
    expect(findChunkIndexForParagraph(chunks, 1)).toBe(0);
    expect(findChunkIndexForParagraph(chunks, 99)).toBe(-1);
  });
});
