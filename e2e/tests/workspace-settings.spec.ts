import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Workspace Settings', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L2-RF-012] workspace settings page renders', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    await expect(page.locator('[data-testid="workspace-settings"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L2-RF-012] preset selector is visible for admin', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    await expect(page.locator('[data-testid="preset-selector"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L1-087] access denied warning is shown for non-admins', async ({ page }) => {
    // AuthContext derives `roles` from the GET /auth/me/ response (REQ-052
    // httpOnly-cookie session restore), not from sessionStorage — intercept
    // that response and strip the admin role to simulate a non-admin session.
    await page.route('**/api/v1/auth/me/', async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      body.roles = (body.roles ?? []).filter((r: string) => r !== 'admin');
      await route.fulfill({ response, json: body });
    });

    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    
    // Admin features should not be visible
    await expect(page.locator('[data-testid="preset-selector"]')).not.toBeVisible();
    
    // Access denied warning should be visible
    await expect(page.getByText(/You must be an admin to view or edit Workspace Settings/)).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L2-RF-012] can create new workspace', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/`);
    const btn = page.locator('[data-testid="create-workspace-btn"]');
    await expect(btn).toBeVisible({ timeout: 10000 });
    await btn.click();
    const nameInput = page.locator('[data-testid="new-workspace-name"]');
    await expect(nameInput).toBeVisible({ timeout: 5000 });
    await nameInput.fill('Test Workspace E2E');
    await page.locator('[data-testid="new-workspace-submit"]').click();
    // After creation, dashboard should show (no blank screen)
    await expect(page.locator('[data-testid="workspace-list"]')).toBeVisible({ timeout: 10000 });
  });
});
