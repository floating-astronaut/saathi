import type { NextConfig } from "next";

// Static export: Cloudflare Pages serves the output directly, no Node runtime,
// no next-on-pages adapter. The site is content only — a landing page and the
// policy pages Meta app review checks — so nothing here needs a server.
const nextConfig: NextConfig = {
  output: "export",
  images: { unoptimized: true },
  trailingSlash: true,
};

export default nextConfig;
