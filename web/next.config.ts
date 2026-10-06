import type { NextConfig } from "next";

// Only the small files data.ts reads at runtime in local mode
// (chapters_index + metadata ≈ 1.4MB total). Volume files (~202MB) are NOT
// traced: in external mode (NEXT_PUBLIC_DATA_URL) API routes fetch them as
// static assets from the story-data branch; in local dev they are read from
// public/data on disk, which never goes through serverless tracing.
const STORY_DATA_FILES = [
  "./public/data/*/*/chapters_index.json",
  "./public/data/*/*/chapters_index.json.gz",
  "./public/data/*/*/metadata.json",
  "./public/data/*/*/metadata.json.gz",
];

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
  },
  compress: true,
  experimental: {
    optimizePackageImports: ["@smoores/epub"],
  },
  // Server fs reads these; dynamic path.join is turbopackIgnored so NFT
  // does not swallow the whole project. Chapter .json.gz is CDN-static.
  outputFileTracingIncludes: {
    "/api/chapter/**": STORY_DATA_FILES,
    "/story/**": STORY_DATA_FILES,
    "/read/**": STORY_DATA_FILES,
    "/epub/**": ["./public/epub-cache/*.json"],
  },
  outputFileTracingExcludes: {
    "/*": [
      "./public/epub-cache/**/ch/**",
      // Volume files (~202MB) must never ride inside a serverless function:
      // external mode fetches them over CDN, local dev reads them from disk.
      // (Kept out of Includes above AND excluded here because @vercel/nft
      // auto-traces the whole public/data tree via fs.readdirSync analysis.)
      "./public/data/*/*/vol-*.json",
      "./public/data/*/*/vol-*.json.gz",
      // Crawl leftovers (raw book dumps, previews, cookies) are never read at
      // runtime; they alone were ~90MB of the 250MB function budget.
      "./public/data/**/book.*.txt",
      "./public/data/**/_preview*",
      "./public/data/**/.cookies.json",
    ],
  },
  headers: async () => [
    {
      source: "/epub-cache/:path*",
      headers: [
        { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
      ],
    },
  ],
  allowedDevOrigins: ['100.81.233.82'],
};

export default nextConfig;
