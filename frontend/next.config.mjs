// Static export bakes NEXT_PUBLIC_API_URL into the bundle. On Cloudflare Pages
// (CF_PAGES=1) a missing or localhost value would ship a site whose browsers
// call their own machine, so fail the build instead.
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ''
if (process.env.CF_PAGES === '1' && (!apiUrl || /localhost|127\.0\.0\.1/.test(apiUrl))) {
  throw new Error(`NEXT_PUBLIC_API_URL must point at the production API on Cloudflare builds (got "${apiUrl}")`)
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Static export: the app has no API routes and fetches entirely client-side
  // (see lib/api.ts), so `next build` emits a plain `out/` directory that
  // Cloudflare Pages can serve directly — no SSR adapter needed.
  output: 'export',
  images: {
    unoptimized: true,
  },
  reactStrictMode: false,
}

export default nextConfig
