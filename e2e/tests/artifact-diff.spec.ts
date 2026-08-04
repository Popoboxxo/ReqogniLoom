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
    // Bumped from 10000ms: the create flow now needs an extra fill+click
    // round-trip (req-new-title-input/req-new-save-btn) before the detail
    // editor renders (issue #172).
    test.setTimeout(15000);

    // Navigate to requirements and create a new one. The create form
    // (issue #172: PageHeader pattern) asks for the title up front via
    // req-new-title-input/req-new-save-btn; the full editor (req-title etc.)
    // only renders after Save navigates to the detail route.
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await page.locator('[data-testid="req-new-title-input"]').fill('Diff Test Requirement');
    await page.locator('[data-testid="req-new-save-btn"]').click();
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 10000 });

    // Fill in initial data
    const titleInput = page.locator('[data-testid="req-title"]');
    await titleInput.fill('Diff Test Requirement');

    // Save the requirement. The save handler PATCHes the requirement and
    // then invalidates the detail query, which triggers a background GET
    // refetch (../RequirementEditors/useRequirementData.ts refresh()). Wait
    // for that refetch response instead of a fixed delay, so the next edit
    // is guaranteed to race against fresh, persisted state.
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          /\/requirements\/[^/]+\/?($|\?)/.test(resp.url()) &&
          resp.request().method() === 'GET' &&
          resp.status() === 200
      ),
      page.locator('[data-testid="save-btn"]').click(),
    ]);
    // Wait for save to complete (button text returns from "Saving..." to "Save")
    await expect(page.locator('[data-testid="save-btn"]')).toContainText('Save', { timeout: 10000 });

    // Now modify the title
    await titleInput.fill('Diff Test Requirement - Modified');

    // Save again to create a new version
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          /\/requirements\/[^/]+\/?($|\?)/.test(resp.url()) &&
          resp.request().method() === 'GET' &&
          resp.status() === 200
      ),
      page.locator('[data-testid="save-btn"]').click(),
    ]);
    await expect(page.locator('[data-testid="save-btn"]')).toContainText('Save', { timeout: 10000 });

    // Click the "View Diff" button
    const viewDiffBtn = page.locator('[data-testid="view-diff-btn"]');
    await expect(viewDiffBtn).toBeVisible({ timeout: 10000 });
    await viewDiffBtn.click();

    // The diff view should appear
    const diffView = page.locator('[data-testid="artifact-diff-view"]');
    await expect(diffView).toBeVisible({ timeout: 10000 });

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
    await expect(diffFields).toBeVisible({ timeout: 10000 });

    // Close button should work
    const closeBtn = page.locator('[data-testid="diff-close-btn"]');
    await expect(closeBtn).toBeVisible({ timeout: 4000 });
    await closeBtn.click();

    // Diff view should be hidden
    await expect(diffView).not.toBeVisible({ timeout: 4000 });
  });

  test('[REQ-L2-RF-014] diff view shows version 0 baseline as all fields added', async ({ page }) => {
    // Bumped from 10000ms: the create flow now needs an extra fill+click
    // round-trip (req-new-title-input/req-new-save-btn) before the detail
    // editor renders (issue #172).
    test.setTimeout(15000);

    // Navigate to requirements and create a new one. The create form
    // (issue #172: PageHeader pattern) asks for the title up front via
    // req-new-title-input/req-new-save-btn; the full editor (req-title etc.)
    // only renders after Save navigates to the detail route.
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await page.locator('[data-testid="req-new-title-input"]').fill('Baseline Diff Test');
    await page.locator('[data-testid="req-new-save-btn"]').click();
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 10000 });

    // Fill in data and save. See the previous test for why we wait for the
    // detail-refetch GET rather than a fixed delay.
    await page.locator('[data-testid="req-title"]').fill('Baseline Diff Test');
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          /\/requirements\/[^/]+\/?($|\?)/.test(resp.url()) &&
          resp.request().method() === 'GET' &&
          resp.status() === 200
      ),
      page.locator('[data-testid="save-btn"]').click(),
    ]);
    await expect(page.locator('[data-testid="save-btn"]')).toContainText('Save', { timeout: 10000 });

    // Open diff view
    const viewDiffBtn = page.locator('[data-testid="view-diff-btn"]');
    await expect(viewDiffBtn).toBeVisible({ timeout: 10000 });
    await viewDiffBtn.click();

    const diffView = page.locator('[data-testid="artifact-diff-view"]');
    await expect(diffView).toBeVisible({ timeout: 10000 });

    // Select from_version=0 (Creation baseline)
    const fromSelect = page.locator('[data-testid="diff-from-version"]');
    await fromSelect.selectOption({ value: '0' });

    // Wait for diff to load
    const diffFields = page.locator('[data-testid="diff-fields"]');
    await expect(diffFields).toBeVisible({ timeout: 10000 });

    // All fields should show "Added" status when comparing from baseline
    // (since version 0 has no data, all current fields are "added")
    const addedBadges = diffFields.locator('text=Added');
    // At least the title field should be marked as added
    await expect(addedBadges.first()).toBeVisible({ timeout: 10000 });
  });
});
