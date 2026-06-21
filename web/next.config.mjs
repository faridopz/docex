/** @type {import('next').NextConfig} */
const nextConfig = {
  // "standalone" makes `next build` emit a minimal, self-contained server
  // in .next/standalone — only the files actually needed at runtime, not the
  // full node_modules. This is the recommended mode for Docker/production and
  // shrinks the image dramatically.
  output: "standalone",
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
  },
};

export default nextConfig;
