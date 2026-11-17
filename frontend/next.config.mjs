// Static export bakes NEXT_PUBLIC_API_URL into the bundle. On the Cloudflare
// Pages production build a missing or localhost value would ship a site whose
// browsers call their own machine, so fail the build instead. Preview builds
// are not blocked; set the variable for Preview too so previews get data.
const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? ''
if (process.env.CF_PAGES === '1' && process.env.CF_PAGES_BRANCH === 'main' && (!apiUrl || /localhost|127\.0\.0\.1/.test(apiUrl))) {
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
