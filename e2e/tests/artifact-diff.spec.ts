// REQ-L1-040, REQ-L2-RF-014: Artifact Diff — visual diff view
// Create a requirement, modify it, open diff view, assert changed field visible
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[COMP-RF-014] ArtifactDiff', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L1-040] diff view opens and shows field-level diff for a requirement', async ({ page }) => {
    // Navigate to requirements and create a new one
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 12000 });

    // Fill in initial data
    const titleInput = page.locator('[data-testid="req-title"]');
    await titleInput.fill('Diff Test Requirement');

    const descriptionArea = page.locator('textarea').first();
    await descriptionArea.fill('Initial description for diff test');

    // Save the requirement
    await page.locator('[data-testid="save-btn"]').click();
    await expect(page.locator('[data-testid="save-btn"]')).toBeVisible({ timeout: 8000 });

    // Now modify the title
    await titleInput.fill('Diff Test Requirement - Modified');

    // Save again to create a new version
    await page.locator('[data-testid="save-btn"]').click();
    await expect(page.locator('[data-testid="save-btn"]')).toBeVisible({ timeout: 8000 });

    // Click the "View Diff" button
    const viewDiffBtn = page.locator('[data-testid="view-diff-btn"]');
    await expect(viewDiffBtn).toBeVisible({ timeout: 8000 });
    await viewDiffBtn.click();

    // The diff view should appear
    const diffView = page.locator('[data-testid="artifact-diff-view"]');
    await expect(diffView).toBeVisible({ timeout: 8000 });

    // Version selectors should be present
    const versionSelectors = page.locator('[data-testid="diff-version-selectors"]');
    await expect(versionSelectors).toBeVisible({ timeout: 4000 });

    // The from-version dropdown should be visible
    const fromVersionSelect = page.locator('[data-testid="diff-from-version"]');
    await expect(fromVersionSelect).toBeVisible({ timeout: 4000 });

    // The to-version dropdown should be visible
    const toVersionSelect = page.locator('[data-testid="diff-to-version"]');
    await expect(toVersionSelect).toBeVisible({ timeout: 4000 });

    // Diff fields should be rendered
    const diffFields = page.locator('[data-testid="diff-fields"]');
    await expect(diffFields).toBeVisible({ timeout: 8000 });

    // Close button should work
    const closeBtn = page.locator('[data-testid="diff-close-btn"]');
    await expect(closeBtn).toBeVisible({ timeout: 4000 });
    await closeBtn.click();

    // Diff view should be hidden
    await expect(diffView).not.toBeVisible({ timeout: 4000 });
  });

  test('[REQ-L2-RF-014] diff view shows version 0 baseline as all fields added', async ({ page }) => {
    // Navigate to requirements and create a new one
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 12000 });

    // Fill in data and save
    await page.locator('[data-testid="req-title"]').fill('Baseline Diff Test');
    await page.locator('[data-testid="save-btn"]').click();
    await expect(page.locator('[data-testid="save-btn"]')).toBeVisible({ timeout: 8000 });

    // Open diff view
    await page.locator('[data-testid="view-diff-btn"]').click();
    const diffView = page.locator('[data-testid="artifact-diff-view"]');
    await expect(diffView).toBeVisible({ timeout: 8000 });

    // Select from_version=0 (Creation baseline)
    const fromSelect = page.locator('[data-testid="diff-from-version"]');
    await fromSelect.selectOption({ value: '0' });

    // Wait for diff to load
    const diffFields = page.locator('[data-testid="diff-fields"]');
    await expect(diffFields).toBeVisible({ timeout: 8000 });

    // All fields should show "Added" status when comparing from baseline
    // (since version 0 has no data, all current fields are "added")
    const addedBadges = diffFields.locator('text=Added');
    // At least the title field should be marked as added
    await expect(addedBadges.first()).toBeVisible({ timeout: 8000 });
  });
});
