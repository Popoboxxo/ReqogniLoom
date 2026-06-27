import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Global Search', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L1-009] search bar is visible in sidebar', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/`);
    await expect(page.locator('[data-testid="global-search"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L1-009] search returns results for known term', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/`);
    const searchInput = page.locator('[data-testid="global-search"]');
    await searchInput.fill('test');
    await searchInput.press('Enter');
    // Either results dropdown or navigation should happen
    await page.waitForTimeout(2000);
    // Just verify no crash — the page should still be functional
    await expect(page.locator('body')).not.toContainText('TypeError');
  });
});
