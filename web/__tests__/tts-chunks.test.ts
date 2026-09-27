import { describe, expect, it } from "vitest";
import {
  buildTTSChunks,
  findChunkIndexForParagraph,
  softenTtsPunctuation,
} from "@/lib/tts-chunks";

describe("tts chunking", () => {
  it("keeps chunks small for low-latency playback", () => {
    const chunks = buildTTSChunks([
      "Xin chao.",
      "Day la doan ngan.",
      "Doan nay cung ngan.",
      "Mot doan dai hon mot chut de chunk duoc gop lai tu nhieu cau nho va tranh viec goi api qua nhieu lan.",
    ]);

    expect(chunks[0]).toMatchObject({
      startParagraphIdx: 0,
    });
    expect(Math.max(...chunks.map((chunk) => chunk.text.length))).toBeLessThanOrEqual(750);
  });

  it("keeps the first chunk shorter for faster cold start", () => {
    const longParas = Array.from({ length: 20 }, (_, i) =>
      `Cau so ${i + 1} day la mot cau van kha dai de gop chunk, noi dung phu de dat nguong ky tu.`,
    );
    const chunks = buildTTSChunks(longParas);
    expect(chunks.length).toBeGreaterThan(1);
    expect(chunks[0].text.length).toBeLessThanOrEqual(400 + 80);
    expect(Math.max(...chunks.slice(1).map((c) => c.text.length))).toBeLessThanOrEqual(750);
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

  it("turns hitching marks into a normal pause", () => {
    expect(softenTtsPunctuation("Ngươi... Ngươi làm sao ở chỗ này?")).toBe(
      "Ngươi, Ngươi làm sao ở chỗ này?",
    );
    expect(softenTtsPunctuation("tuyệt đối là vô pháp vô thiên....")).toBe(
      "tuyệt đối là vô pháp vô thiên.",
    );
    expect(softenTtsPunctuation("Tích tích tích……")).toBe("Tích tích tích.");
    expect(softenTtsPunctuation("Cấm chú · chân lý! A!!")).toBe(
      "Cấm chú chân lý! A!",
    );
    expect(softenTtsPunctuation("Thorne không c·hết.")).toBe(
      "Thorne không chết.",
    );
    expect(softenTtsPunctuation("bay thẳng ra 3~5m —— xong")).toBe(
      "bay thẳng ra 3 đến 5m, xong",
    );
    expect(softenTtsPunctuation("GS. Nguyễn nói... tiếp")).toBe(
      "GS. Nguyễn nói, tiếp",
    );
    expect(softenTtsPunctuation("...")).toBe(".");
    expect(softenTtsPunctuation("“...”")).not.toMatch(/\.{2,}|…/);
  });

  it("does not speak a punctuation-only paragraph", () => {
    const chunks = buildTTSChunks(["...", "Hắn gật đầu."]);
    expect(chunks.map((chunk) => chunk.text)).toEqual(["Hắn gật đầu."]);
    expect(chunks[0].startParagraphIdx).toBe(1);
  });

  it("keeps a hesitation inside the same sentence", () => {
    const chunks = buildTTSChunks([
      "Ngươi... Ngươi làm sao ở chỗ này? Diệp Phong gật đầu.",
    ]);
    expect(chunks).toHaveLength(1);
    expect(chunks[0].text).toBe(
      "Ngươi, Ngươi làm sao ở chỗ này? Diệp Phong gật đầu.",
    );
  });
});
