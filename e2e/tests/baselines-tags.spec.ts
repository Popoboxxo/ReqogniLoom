// F4.3 — Baseline tags in the UI: set a tag in the detail panel, then filter
// the list by it (REQ-L1-018). The filter is server-side (`?tag=…`), so the
// second half of this test only passes when the select actually reaches the
// list call.
import { test, expect } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  createIsolatedWorkspace,
  setWorkspaceId,
} from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

const TAG = 'Release';

test.describe('[REQ-L1-018] Baseline tags (F4.3)', () => {
  test('sets a tag in the detail panel and filters the list by it', async ({ page, request }) => {
    const token = await getAuthToken();
    // Isolated workspace: the tagged + untagged baseline pair must not collide
    // with anything another spec (or a previous run) left in the seed.
    const workspaceId = await createIsolatedWorkspace(token);
    const headers = { Authorization: `Bearer ${token}` };
    const suffix = Date.now().toString(36);
    const taggedName = `e2e-tag-target-${suffix}`;
    const otherName = `e2e-tag-other-${suffix}`;

    for (const name of [taggedName, otherName]) {
      const response = await request.post(`${BACKEND_URL}/api/v1/baselines/`, {
        headers,
        data: { workspace_id: workspaceId, name, scope: 'project' },
      });
      // A non-2xx here is either a preset gate or SE_AUDITOR_BLOCKED — both
      // make the UI half meaningless, so fail with the backend's own message.
      expect(
        response.ok(),
        `baseline create failed: ${response.status()} ${await response.text()}`,
      ).toBeTruthy();
    }

    await setWorkspaceId(page, workspaceId);
    await loginAsAdmin(page);

    await page.goto(`${FRONTEND_URL}/baselines`);
    await expect(page.locator('[data-testid="baselines-view"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[role="status"]:visible')).toHaveCount(0, { timeout: 10000 });

    // Open the baseline that will be tagged.
    await page.locator('[data-testid="baseline-item"]', { hasText: taggedName }).click();
    await expect(page.locator('[data-testid="baseline-tags"]')).toBeVisible();

    // Add + persist one tag through the editor.
    await page.locator('[data-testid="baseline-tag-input"]').fill(TAG);
    await page.locator('[data-testid="baseline-tag-add-btn"]').click();
    await expect(page.locator('[data-testid="baseline-tag-chip"]')).toHaveText(new RegExp(TAG));
    await page.locator('[data-testid="baseline-tag-save-btn"]').click();
    await expect(page.locator('[data-testid="baseline-tag-error"]')).toHaveCount(0);

    // The filter option only exists once the refreshed list carries the label.
    const tagOption = page.locator('[data-testid="baseline-tag-filter"] option', {
      hasText: TAG,
    });
    await expect(tagOption).toHaveCount(1, { timeout: 10000 });

    // Filtering is server-side: only the tagged baseline may remain.
    await page.locator('[data-testid="baseline-tag-filter"]').selectOption({ label: TAG });
    await expect(
      page.locator('[data-testid="baseline-item"]', { hasText: taggedName }),
    ).toBeVisible({ timeout: 10000 });
    await expect(
      page.locator('[data-testid="baseline-item"]', { hasText: otherName }),
    ).toHaveCount(0, { timeout: 10000 });
  });
});
