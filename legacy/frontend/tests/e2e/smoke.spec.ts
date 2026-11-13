import { test, expect } from '@playwright/test';

test.describe('Energy Dashboard Smoke Tests', () => {

  test('Threat Map loads and renders map without errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', err => errors.push(err.message));
    page.on('console', msg => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    
    const failedRequests: string[] = [];
    page.on('response', response => {
      if (response.status() === 404 && response.url().includes('basemaps.cartocdn.com')) {
        failedRequests.push(response.url());
      }
    });

    await page.goto('/');
    // Check map container
    const map = page.locator('.leaflet-container');
    await expect(map).toBeVisible();
    
    // Check for 404 tiles
    expect(failedRequests).toHaveLength(0);
    
    // Check for unhandled errors
    expect(errors).toEqual([]);
  });

  test('Risk Intelligence cards render properly', async ({ page }) => {
    await page.goto('/');
    await page.click('text=Risk Intelligence');
    
    // Wait for cards to load
    await page.waitForSelector('.space-y-4');
    
    const cardContent = await page.locator('.space-y-4').textContent();
    // Check for LLM leaking unknown output or non-answers
    expect(cardContent).not.toContain('Unknown');
    expect(cardContent).not.toContain('do not indicate');
  });

  test('Reroute Matrix calculations are valid', async ({ page }) => {
    await page.goto('/');
    await page.click('text=Reroute Matrix');
    
    // Click Generate matrix (assuming there is a button, or it auto generates)
    await page.click('button:has-text("Generate Reroute Matrix")'); // Adjust text if needed based on actual UI
    
    // Wait for the table
    await page.waitForSelector('table');
    
    // Collect all freight premium values from the table
    // Adjust selector based on actual column position (e.g. 5th column might be freight premium)
    const freightPremiums = await page.evaluate(() => {
      const rows = Array.from(document.querySelectorAll('tbody tr'));
      // Assuming Freight Premium is the 5th column, index 4
      return rows.map(row => row.cells[4]?.innerText || '');
    });
    
    expect(freightPremiums.length).toBeGreaterThan(0);
    
    // Assert they are not all identical (i.e. all $0.00)
    const uniquePremiums = new Set(freightPremiums);
    expect(uniquePremiums.size).toBeGreaterThan(1);
  });

  test('War Room executive brief renders without raw errors', async ({ page }) => {
    await page.goto('/');
    await page.click('text=War Room');
    
    // Click Run Scenario
    await page.click('button:has-text("SIMULATE SCENARIO")'); // Adjust text
    
    // Wait for plan generation
    await page.waitForSelector('.prose'); // Markdown container
    
    const briefContent = await page.locator('.prose').textContent();
    expect(briefContent).not.toContain('RESOURCE_EXHAUSTED');
    expect(briefContent).not.toContain('429');
  });

  test('SPR Optimizer sliders update outputs correctly', async ({ page }) => {
    await page.goto('/');
    await page.click('text=SPR Optimizer');
    
    // Locate the first slider (GDP Impact Rate for example)
    const gdpValuePre = await page.locator('text=GDP Impact per Day').textContent();
    
    // Simulate slider change
    const slider = page.locator('input[type="range"]').first();
    await slider.fill('0.8'); // Assuming it accepts percentage values
    
    // Click Run Simulator
    await page.click('button:has-text("Run SPR Simulation")');
    
    const gdpValuePost = await page.locator('text=GDP Impact per Day').textContent();
    expect(gdpValuePre).not.toEqual(gdpValuePost);
  });

});
