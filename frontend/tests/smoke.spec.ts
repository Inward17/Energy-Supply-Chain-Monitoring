import { expect, test, type Page } from "@playwright/test"

const PAGES = [
  ["overview", "Overview"],
  ["map", "Threat Map"],
  ["risk", "Risk Intelligence"],
  ["market", "Market Pulse"],
  ["reroute", "Reroute Matrix"],
  ["spr", "SPR Optimizer"],
  ["war", "Executive War Room"],
  ["history", "Historical Validation"],
] as const

/** Fail the test on any uncaught exception — a render crash is the most
 *  important regression this suite exists to catch. */
function trackErrors(page: Page) {
  const errors: string[] = []
  page.on("pageerror", (e) => errors.push(e.message))
  return errors
}

const isMobile = (name: string) => name === "mobile"

test("app shell loads and reports the backend as offline", async ({ page }) => {
  const errors = trackErrors(page)
  await page.goto("/")
  await expect(page).toHaveTitle(/MERIDIAN/)
  // The build points at a closed port, so the honest state is "offline".
  await expect(page.getByRole("button", { name: /backend offline/i }).first()).toBeVisible()
  expect(errors).toEqual([])
})

test("every page renders without crashing", async ({ page }, info) => {
  test.skip(isMobile(info.project.name), "desktop covers routing; mobile has its own checks")
  const errors = trackErrors(page)
  await page.goto("/")
  for (const [hash, title] of PAGES) {
    await page.goto(`/#${hash}`)
    await expect(page.locator("header h1")).toHaveText(title)
  }
  expect(errors).toEqual([])
})

test("desktop shows the sidebar, not the tab bar", async ({ page }, info) => {
  test.skip(isMobile(info.project.name))
  await page.goto("/")
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible()
  await expect(page.getByRole("navigation", { name: "Main" })).toBeHidden()
  await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name: "SPR Optimizer" }).click()
  await expect(page).toHaveURL(/#spr$/)
})

test("phone shows a five-tab bar and never scrolls sideways", async ({ page }, info) => {
  test.skip(!isMobile(info.project.name))
  const errors = trackErrors(page)
  await page.goto("/")
  const tabs = page.getByRole("navigation", { name: "Main" }).getByRole("link")
  await expect(tabs).toHaveText(["Overview", "Map", "Risk", "Markets", "Respond"])
  await expect(page.getByRole("navigation", { name: "Primary" })).toBeHidden()

  for (const [hash] of PAGES) {
    await page.goto(`/#${hash}`)
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
    expect(overflow, `#${hash} overflows horizontally`).toBeLessThanOrEqual(0)
  }

  // Grouped tabs expose their sub-pages.
  await page.goto("/#war")
  await expect(page.getByRole("navigation", { name: "Respond tools" }).getByRole("link")).toHaveText(["War Room", "Reroute", "SPR"])
  expect(errors).toEqual([])
})

test("theme toggle switches to light and survives a reload", async ({ page }, info) => {
  await page.emulateMedia({ colorScheme: "dark" })
  await page.goto("/")
  const html = page.locator("html")
  await expect(html).toHaveClass(/\bdark\b/)

  if (isMobile(info.project.name)) {
    await page.getByRole("button", { name: "Filters" }).click()
    await page.getByRole("checkbox", { name: "Light theme" }).check()
  } else {
    await page.getByRole("button", { name: "Switch to light theme" }).click()
  }
  await expect(html).toHaveClass(/\blight\b/)
  await page.reload()
  await expect(html).toHaveClass(/\blight\b/)
})
