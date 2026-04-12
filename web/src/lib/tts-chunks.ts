export interface TTSChunk {
  text: string;
  startParagraphIdx: number;
  endParagraphIdx: number;
}

const MIN_CHUNK_CHARS = 120;
const MAX_CHUNK_CHARS = 260;

function normalizeText(text: string) {
  return text.replace(/\s+/g, " ").trim();
}

function splitSentences(text: string) {
  const normalized = normalizeText(text);
  if (!normalized) return [];

  const matches =
    normalized.match(/[^.!?]+(?:[.!?]+["')\]]*|$)/g)?.map((part) => part.trim()) ??
    [];

  return matches.filter(Boolean).length > 0 ? matches.filter(Boolean) : [normalized];
}

export function buildTTSChunks(paragraphs: string[]) {
  const chunks: TTSChunk[] = [];

  paragraphs.forEach((paragraph, paragraphIdx) => {
    const sentences = splitSentences(paragraph);
    let currentText = "";

    sentences.forEach((sentence) => {
      const nextText = currentText ? `${currentText} ${sentence}` : sentence;

      if (
        currentText &&
        nextText.length > MAX_CHUNK_CHARS &&
        currentText.length >= MIN_CHUNK_CHARS
      ) {
        chunks.push({
          text: currentText.trim(),
          startParagraphIdx: paragraphIdx,
          endParagraphIdx: paragraphIdx,
        });
        currentText = "";
      }

      currentText = currentText ? `${currentText} ${sentence}` : sentence;
    });

    if (currentText) {
      chunks.push({
        text: currentText.trim(),
        startParagraphIdx: paragraphIdx,
        endParagraphIdx: paragraphIdx,
      });
    }
  });

  return chunks;
}

export function findChunkIndexForParagraph(
  chunks: TTSChunk[],
  paragraphIdx: number,
) {
  return chunks.findIndex(
    (chunk) =>
      paragraphIdx >= chunk.startParagraphIdx &&
      paragraphIdx <= chunk.endParagraphIdx,
  );
}
