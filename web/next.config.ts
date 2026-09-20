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
  // does not swallow the whole project. Chapter .json.gz is CDN-static.
  outputFileTracingIncludes: {
    "/api/chapter/**": ["./public/data/**/*"],
    "/story/**": ["./public/data/**/*"],
    "/read/**": ["./public/data/**/*"],
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
  ],
  allowedDevOrigins: ['100.81.233.82'],
};

export default nextConfig;
