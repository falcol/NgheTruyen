import fs from "fs";
import path from "path";
import zlib from "zlib";

// Builds data/manifest.json for the story-data orphan branch.
// Scans <src> (crawler/data layout: <source>/<slug>/{chapters_index,metadata,vol-*}),
// writes { version, generatedAt, stories: [{slug, source, title, totalChapters, volFiles}] }.
// Prefers .gz variants, falls back to plain .json — same rule as src/lib/data.ts.
// Writes { version, generatedAt, stories: [{slug, source, title,
// totalChapters (max-based), chapterCount (index length), volFiles}] }.

export const DATA_MANIFEST_VERSION = 1;

export interface DataManifestEntry {
  slug: string;
  source: string;
  title: string;
  totalChapters: number;
  chapterCount: number;
  volFiles: string[];
}

export interface DataManifest {
  version: typeof DATA_MANIFEST_VERSION;
  generatedAt: string;
  stories: DataManifestEntry[];
}

function readJsonAny<T>(filePath: string): T | null {
  try {
    const buf = fs.readFileSync(filePath + ".gz");
    return JSON.parse(zlib.gunzipSync(buf).toString("utf-8")) as T;
  } catch {
    /* .gz not found */
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, "utf-8")) as T;
  } catch {
    return null;
  }
}

function existsAny(filePath: string): boolean {
  return fs.existsSync(filePath) || fs.existsSync(filePath + ".gz");
}

function resolveSrcDir(): string {
  const flagIdx = process.argv.indexOf("--src");
  if (flagIdx !== -1 && process.argv[flagIdx + 1]) {
    return path.resolve(process.argv[flagIdx + 1]);
  }
  const localCopy = path.resolve(__dirname, "../public/data");
  if (fs.existsSync(localCopy)) return localCopy;
  return path.resolve(__dirname, "../../crawler/data");
}

function resolveOutPath(srcDir: string): string {
  const flagIdx = process.argv.indexOf("--out");
  if (flagIdx !== -1 && process.argv[flagIdx + 1]) {
    return path.resolve(process.argv[flagIdx + 1]);
  }
  return path.join(srcDir, "manifest.json");
}

function buildManifest(srcDir: string): DataManifest {
  const manifest: DataManifest = {
    version: DATA_MANIFEST_VERSION,
    generatedAt: new Date().toISOString(),
    stories: [],
  };
  if (!fs.existsSync(srcDir)) return manifest;

  const sources = fs
    .readdirSync(srcDir)
    .filter(
      (d) => d !== "iqiyi" && fs.statSync(path.join(srcDir, d)).isDirectory(),
    );

  for (const source of sources) {
    const sourceDir = path.join(srcDir, source);
    const slugs = fs
      .readdirSync(sourceDir)
      .filter((d) => fs.statSync(path.join(sourceDir, d)).isDirectory());
    for (const slug of slugs) {
      const storyDir = path.join(sourceDir, slug);
      const hasIndex = existsAny(path.join(storyDir, "chapters_index.json"));
      const hasMeta = existsAny(path.join(storyDir, "metadata.json"));
      if (!hasIndex && !hasMeta) continue;

      const index = readJsonAny<{ index: number; title: string }[]>(
        path.join(storyDir, "chapters_index.json"),
      );
      const meta = readJsonAny<{ story_title: string }>(
        path.join(storyDir, "metadata.json"),
      );
      const volFiles = fs
        .readdirSync(storyDir)
        .filter(
          (f) =>
            f.startsWith("vol-") &&
            (f.endsWith(".json") || f.endsWith(".json.gz")),
        )
        .sort();
      manifest.stories.push({
        slug,
        source,
        title: meta?.story_title ?? slug,
        totalChapters: index
          ? index.reduce((m, c) => Math.max(m, c.index), -1) + 1
          : 0,
        chapterCount: index ? index.length : 0,
        volFiles,
      });
    }
  }

  manifest.stories.sort((a, b) => a.slug.localeCompare(b.slug));
  return manifest;
}

function main() {
  const srcDir = resolveSrcDir();
  const outPath = resolveOutPath(srcDir);
  const manifest = buildManifest(srcDir);
  fs.mkdirSync(path.dirname(outPath), { recursive: true });
  fs.writeFileSync(outPath, JSON.stringify(manifest));
  console.log(
    `Wrote ${manifest.stories.length} stories from ${srcDir} to ${outPath}`,
  );
}

main();
