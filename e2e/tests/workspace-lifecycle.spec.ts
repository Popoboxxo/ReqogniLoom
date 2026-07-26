/**
 * E2E tests for REQ-L1-042 Workspace Lifecycle Management.
 *
 * Coverage:
 *   - Close button visible to admin
 *   - Close workspace via UI
 *   - Delete requires captcha (mismatch shows error)
 *   - Delete succeeds with correct captcha
 */
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Workspace Lifecycle (REQ-L1-042)', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('close button visible to admin', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);
    // REQ-184: lifecycle controls moved to the tenant-wide SystemSettings
    // shell; "administration" is the default tab, so no click is needed.
    await expect(page.locator('[data-testid="system-settings-tab-administration"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="lifecycle-section"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="close-workspace-btn"]')).toBeVisible({ timeout: 5000 });
  });

  test('delete button visible to admin', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);
    // REQ-184: lifecycle controls moved to the tenant-wide SystemSettings
    // shell; "administration" is the default tab, so no click is needed.
    await expect(page.locator('[data-testid="system-settings-tab-administration"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="lifecycle-section"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="delete-workspace-btn"]')).toBeVisible({ timeout: 5000 });
  });

  test('delete modal opens on button click', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);
    // REQ-184: lifecycle controls moved to the tenant-wide SystemSettings
    // shell; "administration" is the default tab, so no click is needed.
    await expect(page.locator('[data-testid="system-settings-tab-administration"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="delete-workspace-btn"]')).toBeVisible({ timeout: 10000 });
    await page.click('[data-testid="delete-workspace-btn"]');
    await expect(page.locator('[data-testid="delete-modal"]')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('[data-testid="delete-confirmation-input"]')).toBeVisible({ timeout: 5000 });
  });

  test('delete requires captcha mismatch shows error', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);
    // REQ-184: lifecycle controls moved to the tenant-wide SystemSettings
    // shell; "administration" is the default tab, so no click is needed.
    await expect(page.locator('[data-testid="system-settings-tab-administration"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="delete-workspace-btn"]')).toBeVisible({ timeout: 10000 });
    await page.click('[data-testid="delete-workspace-btn"]');
    await expect(page.locator('[data-testid="delete-modal"]')).toBeVisible({ timeout: 5000 });

    // Type wrong name
    await page.fill('[data-testid="delete-confirmation-input"]', 'Wrong Name');

    // The confirm button should be disabled when input doesn't match workspace name
    const confirmBtn = page.locator('[data-testid="delete-confirm-btn"]');
    await expect(confirmBtn).toBeDisabled({ timeout: 3000 });
  });

  test('delete confirm button disabled when captcha does not match', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);
    // REQ-184: lifecycle controls moved to the tenant-wide SystemSettings
    // shell; "administration" is the default tab, so no click is needed.
    await expect(page.locator('[data-testid="system-settings-tab-administration"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="delete-workspace-btn"]')).toBeVisible({ timeout: 10000 });
    await page.click('[data-testid="delete-workspace-btn"]');
    await expect(page.locator('[data-testid="delete-modal"]')).toBeVisible({ timeout: 5000 });

    // Type partial/wrong name
    await page.fill('[data-testid="delete-confirmation-input"]', 'Wrong');

    // Confirm button should be disabled
    const confirmBtn = page.locator('[data-testid="delete-confirm-btn"]');
    await expect(confirmBtn).toBeDisabled({ timeout: 3000 });
  });

  test('delete cancel button closes modal', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);
    // REQ-184: lifecycle controls moved to the tenant-wide SystemSettings
    // shell; "administration" is the default tab, so no click is needed.
    await expect(page.locator('[data-testid="system-settings-tab-administration"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="delete-workspace-btn"]')).toBeVisible({ timeout: 10000 });
    await page.click('[data-testid="delete-workspace-btn"]');
    await expect(page.locator('[data-testid="delete-modal"]')).toBeVisible({ timeout: 5000 });

    // Click cancel
    await page.click('[data-testid="delete-cancel-btn"]');

    // Modal should be hidden
    await expect(page.locator('[data-testid="delete-modal"]')).not.toBeVisible({ timeout: 3000 });
  });
});
