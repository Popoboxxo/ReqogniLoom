import { test, expect, type Page } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const WIDTHS = [1280, 1024, 768];

async function listPanel(page: Page) {
  const divider = page.locator('[data-testid="splitview-divider"]');
  await expect(divider).toBeVisible({ timeout: 20000 });
  return divider.locator('xpath=preceding-sibling::*[1]');
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
