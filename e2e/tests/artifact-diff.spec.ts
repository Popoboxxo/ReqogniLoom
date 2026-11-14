// REQ-L1-040, REQ-L2-RF-014: Artifact Diff — visual diff view
// Create a requirement, modify it, open diff view, assert changed field visible
import { test, expect, Page } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
import { collapseInspector, openInspectorTab } from '../helpers/inspector';

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
   * policy", HTTP 400). Without filling the change-reason input the save
   * never reaches the server successfully, no refetch is triggered, and the
   * waitForResponse below hangs until the test times out.
   *
   * Task 25: the requirement editor now renders through the shared
   * `ArtifactForm` (`RequirementArtifactForm`), whose entity-switch reset
   * (`useEntityReset`, keyed on `artifactId`) — unlike the deleted
   * `RequirementForm.tsx`'s own `useEffect(() => {...}, [requirement])` —
   * does NOT re-run on a same-artifact refetch, only on an actual artifact
   * switch. The retry this helper still performs is defense-in-depth against
   * that now-fixed bug class (kept rather than removed: a false-negative
   * retry is free, a flaky E2E failure is not), not a currently-reachable
   * race.
   */
  async function saveWithChangeReason(page: Page, reason: string, attempt = 1): Promise<void> {
    const reasonInput = page.locator('[data-testid="artifact-form-change-reason"]');
    await reasonInput.fill(reason);
    try {
      await Promise.all([
        page.waitForResponse(
          (resp) =>
            /\/requirements\/[^/?]+\/?$/.test(new URL(resp.url()).pathname) &&
            resp.request().method() === 'GET' &&
            resp.status() === 200,
          { timeout: attempt === 1 ? 8000 : 30000 }
        ),
        page.locator('[data-testid="artifact-form-save"]').click(),
      ]);
    } catch (err) {
      const stillHasReason = await reasonInput.inputValue();
      if (attempt === 1 && stillHasReason.trim() !== reason.trim()) {
        await saveWithChangeReason(page, reason, attempt + 1);
        return;
      }
      throw err;
    }
    await expect(page.locator('[data-testid="artifact-form-save"]')).toContainText(/Save|Speichern/, { timeout: 10000 });
  }

  /**
   * Open the inspector on its Diff tab.
   *
   * Replaces the old `ensureInspectorExpanded()` helper, which pressed the
   * `artifact-inspector-expand` button of the stacked `RightSidebar`. Since
   * #1762/M1 the requirements route mounts the tabbed `InspectorShell`: the
   * collapsed state is a rail whose counter buttons open the inspector *on that
   * tab*, and the areas are tabs now instead of stacked panels. Testids come
   * from the shell's contract (`inspectorContract.ts`, spec §8.4), so this is
   * the same selector inventory the frontend unit tests use. See
   * `helpers/inspector.ts` for the sheet/`inert` background.
   */
  async function openDiffTab(page: Page): Promise<void> {
    await openInspectorTab(page, 'diff');
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
    await expect(page.locator('[data-testid="artifact-field-title"]')).toBeVisible({ timeout: 10000 });

    // #1762 (M1): the inspector mounts as a sheet at the 1280 px E2E viewport
    // and makes the detail area it covers `inert`. Collapse it before driving
    // the form — a fill() on an inert input silently does nothing.
    await collapseInspector(page);

    // Fill in initial data
    const titleInput = page.locator('[data-testid="artifact-field-title"]');
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
    // REQ-L2-RF-034/036 it shares the persistent ArtifactInspector with the
    // version list, and since #1762/M1 it is the inspector's "Diff" tab.
    // `RequirementEditors.tsx` always passes <InspectorShell> next to the form
    // (DiffPanel wraps ArtifactDiff with an inspector section around it, see
    // tabs/DiffTab.tsx).
    const inspector = page.locator('[data-testid="inspector-shell"]');
    await expect(inspector).toBeVisible({ timeout: 10000 });
    await openDiffTab(page);

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
    await expect(page.locator('[data-testid="artifact-field-title"]')).toBeVisible({ timeout: 10000 });

    // #1762 (M1): collapse the inspector's sheet before filling the form — see
    // the note in the previous test.
    await collapseInspector(page);

    // Fill in data and save. See the previous test for why we wait for the
    // detail-refetch GET rather than a fixed delay.
    await page.locator('[data-testid="artifact-field-title"]').fill('Baseline Diff Test');
    await saveWithChangeReason(page, 'initial content');

    // The diff is the inspector's "Diff" tab since #1762/M1 — no separate
    // "View Diff" trigger exists anymore, see the note in the previous test.
    await openDiffTab(page);
    const diffView = page.locator('[data-testid="artifact-diff-view"]');
    await expect(diffView).toBeVisible({ timeout: 10000 });

    // Select from_version=0 (Creation baseline)
    const fromSelect = page.locator('[data-testid="diff-from-version"]');
    await fromSelect.selectOption({ value: '0' });

    // Wait for diff to load
    const diffFields = page.locator('[data-testid="diff-fields"]');
    await expect(diffFields).toBeVisible({ timeout: 10000 });

    // All fields carry the "added" status when comparing from the version-0
    // baseline (since version 0 has no data, every current field is added).
    // The badge text is translated, so assert the locale-independent
    // `data-testid` instead of the English/ German prose.
    const addedBadges = diffFields.getByTestId('diff-status-added');
    // At least the title field should be marked as added
    await expect(addedBadges.first()).toBeVisible({ timeout: 10000 });
  });
});
