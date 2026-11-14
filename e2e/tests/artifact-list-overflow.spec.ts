import { test, expect, type Page } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const WIDTHS = [1280, 1024, 768];

/**
 * The requirements list pane.
 *
 * Until #1762/M1 this was "the drag divider's previous sibling": the route used
 * SplitView's *legacy* contract, which renders `splitview-divider` between the
 * panels. The route now uses the *concept* contract (`list`/`detail`/`spine`,
 * UI_KONZEPT ch. 12.6), which has no drag divider — the approved M1 contract
 * drops it (commit 85ceecad: "the requirements route no longer has a drag
 * divider because the approved contract has none"). The list pane is a named
 * container there, so the overflow checks target it directly instead of
 * inferring it from a divider that no longer exists.
 */
async function listPanel(page: Page) {
  const panel = page.getByTestId('splitview-list');
  await expect(panel).toBeVisible({ timeout: 20000 });
  return panel;
}

test.describe('Artifact list horizontal overflow (#1252)', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  for (const width of WIDTHS) {
    test(`no horizontal scrollbar in the requirements list at ${width}px`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`${FRONTEND_URL}/requirements`);
      const panel = await listPanel(page);

      await expect
        .poll(async () => panel.evaluate((el) => getComputedStyle(el).overflowX))
        .toBe('hidden');

      const doc = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      expect(doc.scrollWidth, 'document must not scroll horizontally').toBeLessThanOrEqual(
        doc.clientWidth + 1,
      );

      const panelOverflow = await panel.evaluate((el) => ({
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
      }));
      expect(
        panelOverflow.scrollWidth,
        'list panel must not have a horizontal scrollbar',
      ).toBeLessThanOrEqual(panelOverflow.clientWidth + 1);
    });
  }
});
