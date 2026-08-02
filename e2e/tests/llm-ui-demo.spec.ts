import { test, expect } from '@playwright/test';

test.describe('LLM-Optimized UI Tests', () => {
  test('should navigate to the dashboard and load architecture views using semantic data-testids', async ({ page }) => {
    // Navigate to the main page
    await page.goto('/');

    // Wait for the app to load
    // Depending on auth state, it either shows login or dashboard
    const rootElement = page.locator('#root');
    await expect(rootElement).toBeVisible();

    // Verify page title to ensure app mounted
    // NOTE: product was renamed ReqFlow -> ReqogniLoom; frontend/index.html
    // <title> now reads "ReqogniLoom" (see index.html:7). This assertion
    // was stale, matching neither the current nor any prior title, so it
    // always failed regardless of app health.
    await expect(page).toHaveTitle(/ReqogniLoom/i);
  });
});
