export interface TTSChunk {
  text: string;
  startParagraphIdx: number;
  endParagraphIdx: number;
}

const MIN_CHUNK_CHARS = 60;
const MAX_CHUNK_CHARS = 250;
const SENTENCE_SEPARATOR = " ";
const BOUNDARY_PATTERN = /[^.!?。！？…;；:：]+(?:[.!?。！？…;；:：]+["')\]”’」』）]*|$)/g;

function normalizeText(text: string) {
  return text.replace(/\s+/g, " ").trim();
}

function splitSentences(text: string) {
  const normalized = normalizeText(text);
  if (!normalized) return [];

  const matches =
    normalized.match(BOUNDARY_PATTERN)?.map((part) => part.trim()) ?? [];

  const parts = matches.filter(Boolean).length > 0 ? matches.filter(Boolean) : [normalized];
  return parts.flatMap(splitLongSegment);
}

function splitLongSegment(text: string) {
  if (text.length <= MAX_CHUNK_CHARS) return [text];

  const chunks: string[] = [];
  let remaining = text.trim();

  while (remaining.length > MAX_CHUNK_CHARS) {
    const windowText = remaining.slice(0, MAX_CHUNK_CHARS + 1);
    const splitAt = Math.max(
      windowText.lastIndexOf(" "),
      windowText.lastIndexOf("-"),
      windowText.lastIndexOf("—"),
    );
    const safeSplitAt =
      splitAt >= MIN_CHUNK_CHARS ? splitAt : MAX_CHUNK_CHARS;

    chunks.push(remaining.slice(0, safeSplitAt).trim());
    remaining = remaining.slice(safeSplitAt).trim();
  }

  if (remaining) chunks.push(remaining);
  return chunks;
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
      const separator = currentText.length === 0 ? "" : SENTENCE_SEPARATOR;
      const nextText = `${currentText}${separator}${sentence}`;

      if (
        currentText &&
        nextText.length > MAX_CHUNK_CHARS
      ) {
        pushCurrentChunk();
      }

      if (!currentText) {
        currentStartParagraphIdx = paragraphIdx;
      }

      const nextSeparator = currentText.length === 0 ? "" : SENTENCE_SEPARATOR;
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
