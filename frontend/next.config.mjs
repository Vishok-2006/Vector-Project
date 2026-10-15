/** @type {import('next').NextConfig} */
const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";

const nextConfig = {
  // Self-contained server bundle used by the Docker image (node server.js).
  output: "standalone",
  poweredByHeader: false,
  // Only used by `npm run dev` (and as a fallback): in the container nginx routes /api itself.
  rewrites: async () => [{ source: "/api/:path*", destination: `${backend}/api/:path*` }],
};

export default nextConfig;
