/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: the app has no API routes and fetches entirely client-side
  // (see lib/api.ts), so `next build` emits a plain `out/` directory that
  // Cloudflare Pages can serve directly — no SSR adapter needed.
  output: 'export',
  typescript: {
    ignoreBuildErrors: true,
  },
  images: {
    unoptimized: true,
  },
  reactStrictMode: false,
}

export default nextConfig
