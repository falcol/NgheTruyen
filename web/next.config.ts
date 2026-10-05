import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
  },
  compress: true,
  experimental: {
    optimizePackageImports: ["@smoores/epub"],
  },
  // Server fs reads these; dynamic path.join is turbopackIgnored so NFT
  // does not swallow the whole project. Only the small index/metadata files
  // are needed at runtime — chapter volumes are fetched client-side from
  // the static /data files, which keeps every function far below the
  // 250MB bundle limit.
  outputFileTracingIncludes: {
    "/story/**": [
      "./public/data/*/*/chapters_index.json",
      "./public/data/*/*/chapters_index.json.gz",
      "./public/data/*/*/metadata.json",
      "./public/data/*/*/metadata.json.gz",
    ],
    "/read/**": [
      "./public/data/*/*/chapters_index.json",
      "./public/data/*/*/chapters_index.json.gz",
      "./public/data/*/*/metadata.json",
      "./public/data/*/*/metadata.json.gz",
    ],
    "/epub/**": ["./public/epub-cache/*.json"],
  },
  outputFileTracingExcludes: {
    "/*": ["./public/epub-cache/**/ch/**"],
  },
  headers: async () => [
    {
      source: "/epub-cache/:path*",
      headers: [
        { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
      ],
    },
    {
      // Volume/index files can be rewritten by a recrawl, so no immutable.
      source: "/data/:path*",
      headers: [
        { key: "Cache-Control", value: "public, max-age=3600, stale-while-revalidate=604800" },
      ],
    },
  ],
  allowedDevOrigins: ['100.81.233.82'],
};

export default nextConfig;
