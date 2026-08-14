// REQ-L1-040, REQ-L2-RF-014: Artifact Diff — visual diff view
// Create a requirement, modify it, open diff view, assert changed field visible
import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[COMP-RF-014] ArtifactDiff', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  /**
   * Save the open requirement and wait for the detail-refetch GET.
   *
   * The seeded workspace runs the "extended" preset, whose policy rejects a
   * PATCH without a change reason ("change_reason required by workspace preset
   * policy", HTTP 400). Without filling change-reason-input the save never
   * reaches the server successfully, no refetch is triggered, and the
   * waitForResponse below hangs until the test times out.
   */
  async function saveWithChangeReason(page: Page, reason: string): Promise<void> {
    await page.locator('[data-testid="change-reason-input"]').fill(reason);
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
  }

  test('[REQ-L1-040] diff view opens and shows field-level diff for a requirement', async ({ page }) => {
    // Bumped from 10000ms: the create flow needs an extra fill+click
    // round-trip (req-new-title-input/req-new-save-btn) before the detail
    // editor renders (issue #172), and every save additionally fills
    // change-reason-input (extended-preset policy) and waits for the
    // detail-refetch GET. 15000ms no longer covers two such saves.
    test.setTimeout(30000);

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
    // refetch (../RequirementEditors/useRequirementData.ts refresh()).
    // saveWithChangeReason waits for that refetch instead of a fixed delay, so
    // the next edit is guaranteed to race against fresh, persisted state.
    await saveWithChangeReason(page, 'initial content');

    // Now modify the title
    await titleInput.fill('Diff Test Requirement - Modified');

    // Save again to create a new version
    await saveWithChangeReason(page, 'renamed for the diff assertion');

    // Diff is no longer behind a "View Diff" modal trigger — since
    // REQ-L2-RF-034/036 (RightSidebar shell) it is rendered inline in the
    // persistent ArtifactInspector sidebar, always visible once a version
    // exists (RequirementEditors.tsx renders <RightSidebar> unconditionally
    // next to the form; DiffPanel wraps ArtifactDiff with an inspector
    // section around it, see DiffPanel.tsx).
    const inspector = page.locator('[data-testid="artifact-inspector"]');
    await expect(inspector).toBeVisible({ timeout: 10000 });

    const diffPanel = page.locator('[data-testid="inspector-diff-panel"]');
    await expect(diffPanel).toBeVisible({ timeout: 10000 });

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

    // The Close button is kept for visual/API parity with the standalone
    // ArtifactDiff component, but per UI standards §1.2 the inspector is
    // persistent and must NOT unmount on close (DiffPanel.tsx onClose is a
    // deliberate no-op) — so clicking it must leave the diff view visible.
    const closeBtn = page.locator('[data-testid="diff-close-btn"]');
    await expect(closeBtn).toBeVisible({ timeout: 4000 });
    await closeBtn.click();
    await expect(diffView).toBeVisible({ timeout: 2000 });
  });

  test('[REQ-L2-RF-014] diff view shows version 0 baseline as all fields added', async ({ page }) => {
    // Bumped from 10000ms: the create flow needs an extra fill+click
    // round-trip (req-new-title-input/req-new-save-btn) before the detail
    // editor renders (issue #172), and every save additionally fills
    // change-reason-input (extended-preset policy) and waits for the
    // detail-refetch GET. 15000ms no longer covers two such saves.
    test.setTimeout(30000);

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
    await saveWithChangeReason(page, 'initial content');

    // Diff view is rendered inline in the persistent ArtifactInspector
    // sidebar (REQ-L2-RF-034/036) — no separate "View Diff" trigger exists
    // anymore, see the note in the previous test.
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
