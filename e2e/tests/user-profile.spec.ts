import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('User Profile Settings', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L1-087] user profile page renders', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/profile`);
    await expect(page.locator('[data-testid="user-profile-settings"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L1-087] visibility section is present in user profile', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/profile`);
    // Wait for the visibility section to be loaded and visible
    await expect(page.locator('[data-testid="visibility-section"]')).toBeVisible({ timeout: 10000 });
    
    // Check that at least one toggle is visible
    await expect(page.locator('[data-testid="visibility-row-diagrams"]')).toBeVisible();
    await expect(page.locator('[data-testid="visibility-checkbox-diagrams"]')).toBeVisible();
  });

  test('[REQ-L1-087] can toggle visibility override', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/profile`);
    
    // Check initial state
    const diagramsCheckbox = page.locator('[data-testid="visibility-checkbox-diagrams"]');
    await expect(diagramsCheckbox).toBeVisible({ timeout: 10000 });
    
    // Toggle the checkbox
    await diagramsCheckbox.click();
    
    // Wait for the reset button to become *enabled* (indicating the override
    // is active). Visibility alone is not enough: the button is always in the
    // DOM but stays disabled until the toggle has been persisted, so under
    // load the click below raced the persist and timed out (issue #947).
    const resetBtn = page.locator('[data-testid="visibility-reset-diagrams"]');
    await expect(resetBtn).toBeEnabled({ timeout: 15000 });
    
    // Reset the override
    await resetBtn.click();
    
    // Reset button should be disabled
    await expect(resetBtn).toBeDisabled({ timeout: 10000 });
  });
});
