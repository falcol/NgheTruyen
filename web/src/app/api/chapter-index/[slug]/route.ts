import { getChapterIndex } from "@/lib/data";

export const revalidate = 86400;

export async function GET(
  _request: Request,
  context: { params: Promise<{ slug: string }> },
) {
  const { slug } = await context.params;
  const chapters = getChapterIndex(slug);
  if (!chapters) return new Response("Not found", { status: 404 });

  const titles = chapters.map((chapter) => ({
    index: chapter.index,
    title: chapter.title,
  }));

  return Response.json(titles, {
    headers: {
      "Cache-Control": "public, s-maxage=86400, stale-while-revalidate=604800",
    },
  });
}
