// REQ-L0-017 / REQ-L2-ICD-001: ICD Management UI smoke tests
// Validates the frontend surfaces the ICD list and the create-ICD affordance.
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[REQ-L0-017 / REQ-L2-ICD-001] IcdView UI', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L0-017] icd_list_renders', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/icds`);
    // The view container should mount and finish loading
    const view = page.locator('[data-testid="icd-view"]');
    await expect(view).toBeVisible({ timeout: 10000 });
    // Wait for the loading spinner to disappear (status role is reserved for loading)
    await expect(page.locator('[role="status"]')).not.toBeVisible({ timeout: 10000 });
    // Either the list or the empty-state placeholder must be on the page
    const list = page.locator('[data-testid="icds-list"]');
    const empty = page.locator('[data-testid="icds-empty"]');
    await expect(list.or(empty)).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L0-017] icd_create_button_visible', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/icds`);
    await expect(page.locator('[data-testid="icd-view"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[role="status"]')).not.toBeVisible({ timeout: 10000 });
    const createBtn = page.locator('[data-testid="create-icd-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 10000 });
    await expect(createBtn).toBeEnabled();
  });
});
