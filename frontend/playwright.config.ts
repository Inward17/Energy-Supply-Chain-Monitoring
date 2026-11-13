import { defineConfig, devices } from "@playwright/test"

/**
 * Smoke tests run against the static export in `out/` — the exact files
 * Cloudflare Pages serves. The build points the API at a closed port, so the
 * app runs in its "backend offline" state: deterministic, no network, no
 * secrets. These tests check the shell (navigation, layout, theming), not data.
 */
const PORT = 4173
const python = process.platform === "win32" ? "python" : "python3"

export default defineConfig({
  testDir: "./tests",
  timeout: 30_000,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["github"], ["html", { open: "never" }]] : "list",
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure" },
  webServer: {
    command: `${python} -m http.server ${PORT} --bind 127.0.0.1 --directory out`,
    url: `http://127.0.0.1:${PORT}`,
    reuseExistingServer: !process.env.CI,
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Pixel 5"] } },
  ],
})
