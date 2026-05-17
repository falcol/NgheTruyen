import { listEpubFiles, warmAllEpubCaches } from "../src/lib/epub-parse";

async function main() {
  const files = listEpubFiles();
  if (files.length === 0) {
    console.log("No EPUB files in ../epub/");
    return;
  }
  console.log(`Extracting metadata + chapters for ${files.length} EPUB(s)...`);
  await warmAllEpubCaches();
  console.log("Done. Cache: web/public/epub-cache/");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
