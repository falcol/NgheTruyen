import type { NextConfig } from "next";

// Only the files data.ts reads at runtime. `./public/data/**/*` also dragged
// in crawl leftovers (book dumps, previews), and Excludes cannot remove files
// that an Include added.
const STORY_DATA_FILES = [
  "./public/data/*/*/vol-*.json",
  "./public/data/*/*/vol-*.json.gz",
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
