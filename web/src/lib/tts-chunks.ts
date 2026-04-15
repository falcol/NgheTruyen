export interface TTSChunk {
  text: string;
  startParagraphIdx: number;
  endParagraphIdx: number;
}

const MIN_CHUNK_CHARS = 450;
const MAX_CHUNK_CHARS = 1400;

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
  let currentText = "";
  let currentStartParagraphIdx = -1;
  let currentEndParagraphIdx = -1;

  function pushCurrentChunk() {
    if (!currentText) return;

    chunks.push({
      text: currentText.trim(),
      startParagraphIdx: currentStartParagraphIdx,
      endParagraphIdx: currentEndParagraphIdx,
    });

    currentText = "";
    currentStartParagraphIdx = -1;
    currentEndParagraphIdx = -1;
  }

  paragraphs.forEach((paragraph, paragraphIdx) => {
    const sentences = splitSentences(paragraph);

    sentences.forEach((sentence) => {
      const separator =
        currentText.length === 0
          ? ""
          : currentEndParagraphIdx === paragraphIdx
            ? " "
            : "\n\n";
      const nextText = `${currentText}${separator}${sentence}`;

      if (
        currentText &&
        nextText.length > MAX_CHUNK_CHARS &&
        currentText.length >= MIN_CHUNK_CHARS
      ) {
        pushCurrentChunk();
      }

      if (!currentText) {
        currentStartParagraphIdx = paragraphIdx;
      }

      const nextSeparator =
        currentText.length === 0
          ? ""
          : currentEndParagraphIdx === paragraphIdx
            ? " "
            : "\n\n";
      currentText = `${currentText}${nextSeparator}${sentence}`;
      currentEndParagraphIdx = paragraphIdx;
    });
  });

  pushCurrentChunk();
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
