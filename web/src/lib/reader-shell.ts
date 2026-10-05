export interface ReaderChapterRef {
  index: number;
  title: string;
}

/** Titles serialized into the first reader document: the open chapter only. */
export function readerFirstChapters(current: ReaderChapterRef): ReaderChapterRef[] {
  return [{ index: current.index, title: current.title }];
}

function unwrapChapterList(data: unknown): unknown[] {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== "object") return [];
  const record = data as Record<string, unknown>;
  if (Array.isArray(record.chapters)) return record.chapters;
  const meta = record.meta;
  if (meta && typeof meta === "object") {
    const chapters = (meta as Record<string, unknown>).chapters;
    if (Array.isArray(chapters)) return chapters;
  }
  return [];
}

/** Titles for the picker. Paragraph bodies on a record are ignored. */
export function parseChapterIndex(data: unknown): ReaderChapterRef[] {
  const out: ReaderChapterRef[] = [];
  for (const item of unwrapChapterList(data)) {
    if (!item || typeof item !== "object") continue;
    const rec = item as Record<string, unknown>;
    if (typeof rec.index !== "number" || !Number.isFinite(rec.index)) continue;
    if (typeof rec.title !== "string" || rec.title.length === 0) continue;
    out.push({ index: rec.index, title: rec.title });
  }
  return out;
}
