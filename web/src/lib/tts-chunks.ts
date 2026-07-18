export interface TTSChunk {
  text: string;
  startParagraphIdx: number;
  endParagraphIdx: number;
}

// Cloud neural TTS (Edge) handles long utterances well. Larger chunks =
// fewer HTTP round-trips + fewer audio handoffs → smoother like Read Aloud
// (their cloud path uses ~750 chars). Cap below API max (800) in tts-server.
// First chunk stays smaller so cold Play / prepare gets audio sooner.
const MIN_CHUNK_CHARS = 120;
const MAX_CHUNK_CHARS = 750;
const FIRST_CHUNK_CHARS = 400;
const SENTENCE_SEPARATOR = " ";

// Placeholder swapped in for protected periods so they survive the split step.
// Must be a character that never appears in story text.
const PROTECTED_PERIOD = "\x01";

// Vietnamese academic/professional titles and common abbreviations that should
// NOT trigger a sentence break when followed by a period.
const VI_ABBR_PATTERN =
  /\b(GS|PGS|TS|ThS|BS|KS|NXB|UBND|HĐND|MTTQ|TP|TT|TX|BT|TH|TK|CT|TW|QH|TG|NV|BC|TBT|PV|BTV|MC|Mr|Mrs|Ms|Dr|Prof|St|vs|etc)\./gi;

// Numbered/lettered list markers: "1.", "(1)", "a." followed by a space
// Only shield when they appear at a word boundary before a space.
const NUM_LIST_PATTERN = /(\b\d{1,3}|\([a-zA-Zđ\d]{1,2}\))\.\s/g;

function normalizeText(text: string) {
  return text.replace(/\s+/g, " ").trim();
}

// Protect abbreviation/list periods → split on real sentence endings → restore.
// Inspired by Read Aloud (MIT): github.com/ken107/read-aloud
function splitSentences(text: string): string[] {
  const normalized = normalizeText(text);
  if (!normalized) return [];

  // Shield periods that are NOT sentence endings
  const shielded = normalized
    .replace(VI_ABBR_PATTERN, (_, abbr) => `${abbr}${PROTECTED_PERIOD}`)
    .replace(NUM_LIST_PATTERN, (_, tok) => `${tok}${PROTECTED_PERIOD} `);

  // Split on genuine sentence-ending punctuation followed by whitespace or EOS
  const raw = shielded.split(/(?<=[.!?…。！？]+["')\]"'」』）]*)\s+/);

  const sentences = raw
    .map((s) => s.replace(new RegExp(PROTECTED_PERIOD, "g"), ".").trim())
    .filter(Boolean);

  const parts = sentences.length > 0 ? sentences : [normalized];
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

  function chunkLimit() {
    return chunks.length === 0 ? FIRST_CHUNK_CHARS : MAX_CHUNK_CHARS;
  }

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
      const limit = chunkLimit();

      if (currentText && nextText.length > limit) {
        pushCurrentChunk();
      }

      if (!currentText) {
        currentStartParagraphIdx = paragraphIdx;
      }

      const nextSeparator = currentText.length === 0 ? "" : SENTENCE_SEPARATOR;
      // If a single sentence exceeds the active limit, still accept it (splitLongSegment handled upstream)
      currentText = `${currentText}${nextSeparator}${sentence}`;
      currentEndParagraphIdx = paragraphIdx;

      // Flush first chunk as soon as it reaches the short target (faster first audio)
      if (chunks.length === 0 && currentText.length >= FIRST_CHUNK_CHARS) {
        pushCurrentChunk();
      }
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
