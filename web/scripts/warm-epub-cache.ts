import { listEpubFiles, warmAllEpubCaches } from "../src/lib/epub";

async function main() {
  const files = listEpubFiles();
  if (files.length === 0) {
    console.log("No EPUB files in ../epub/");
    return;
  }
  console.log(`Warming metadata cache for ${files.length} EPUB(s)...`);
  await warmAllEpubCaches();
  console.log("Done. Cache written to epub/.cache/");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
