import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  turbopack: {
    root: __dirname,
  },
  compress: true,
  experimental: {
    optimizePackageImports: ["@smoores/epub"],
  },
  headers: async () => [
    {
      source: "/epub-cache/:path*",
      headers: [
        { key: "Cache-Control", value: "public, max-age=31536000, immutable" },
      ],
    },
  ],
};

export default nextConfig;
