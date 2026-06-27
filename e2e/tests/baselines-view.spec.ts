// REQ-L1-018 + REQ-L2-RF-007: Baselines mit echten API-Daten
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[COMP-RF-001] BaselinesView', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L1-018] baselines view renders without error', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/baselines`);
    const view = page.locator('[data-testid="baselines-view"]');
    await expect(view).toBeVisible({ timeout: 15000 });
  });

  test('[REQ-L1-018] create baseline button is visible', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/baselines`);
    // Wait for loading to finish (baselines-view present + no loading spinner)
    await expect(page.locator('[data-testid="baselines-view"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[role="status"]')).not.toBeVisible({ timeout: 10000 });
    const btn = page.locator('[data-testid="create-baseline-btn"]');
    await expect(btn).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L1-018] baselines view does not show stub placeholder', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/baselines`);
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).not.toContainText('in Bearbeitung');
  });
});
