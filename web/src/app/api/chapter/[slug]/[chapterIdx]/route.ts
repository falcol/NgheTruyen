import { getChapter } from "@/lib/data";

export const revalidate = 86400; // ISR — regenerate at most once per day

export async function GET(
  _request: Request,
  context: { params: Promise<{ slug: string; chapterIdx: string }> },
) {
  const { slug, chapterIdx: idxStr } = await context.params;
  const chapterIdx = parseInt(idxStr, 10);
  if (isNaN(chapterIdx)) {
    return new Response("Invalid chapter index", { status: 400 });
  }

  const chapter = getChapter(slug, chapterIdx);
  if (!chapter) {
    return new Response("Not found", { status: 404 });
  }

  return Response.json(chapter, {
    headers: {
      "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800",
    },
  });
}
