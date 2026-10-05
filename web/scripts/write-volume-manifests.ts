import fs from "fs";
import path from "path";

/**
 * Prebuild step: write one tiny `volumes_manifest.json` per story under
 * public/data. Serverless functions cannot rely on fs.readdirSync at request
 * time (only NFT-traced files exist in the bundle), but they CAN read a
 * single known file — so getVolumeManifest() reads this file first and only
 * falls back to a directory scan (local dev).
 *
 * Must run after `data:copy` (it scans public/data, not crawler/data).
 */

const MANIFEST_FILENAME = "volumes_manifest.json";
const VOL_PATTERN = /^vol-\d+-ch(\d+)-(\d+)\.json(?:\.gz)?$/;

function main() {
  const dataDir = path.join(process.cwd(), "public", "data");
  if (!fs.existsSync(dataDir)) {
    console.log("No public/data — skipping volume manifests.");
    return;
  }

  let stories = 0;
  let vols = 0;
  for (const source of fs.readdirSync(dataDir)) {
    if (source === "iqiyi") continue;
    const sourceDir = path.join(dataDir, source);
    if (!fs.statSync(sourceDir).isDirectory()) continue;

    for (const slug of fs.readdirSync(sourceDir)) {
      const storyDir = path.join(sourceDir, slug);
      if (!fs.statSync(storyDir).isDirectory()) continue;

      const ranges = fs
        .readdirSync(storyDir)
        .map((f) => {
          const m = VOL_PATTERN.exec(f);
          if (!m) return null;
          return {
            url: `/data/${source}/${encodeURIComponent(slug)}/${f}`,
            first: Number(m[1]),
            last: Number(m[2]),
          };
        })
        .filter((v) => v !== null)
        .sort((a, b) => a.first - b.first);
      if (ranges.length === 0) continue;

      fs.writeFileSync(
        path.join(storyDir, MANIFEST_FILENAME),
        JSON.stringify({
          indexUrl: `/data/${source}/${encodeURIComponent(slug)}/chapters_index.json.gz`,
          vols: ranges,
        }),
      );
      stories += 1;
      vols += ranges.length;
    }
  }
  console.log(`Wrote ${MANIFEST_FILENAME} for ${stories} storie(s), ${vols} volume(s).`);
}

main();
