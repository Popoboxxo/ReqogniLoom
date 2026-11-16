// Mobile E2E helpers (plan M0, REQ-215).
//
// The smoke suite asserts one thing on every route that a desktop suite
// never checks: the document itself must not scroll sideways. Scrollable
// tables are allowed to scroll *inside their own container* (Spec §7.3);
// only `documentElement` is the failure signal here.
import { expect, type Page } from '@playwright/test';

/**
 * Assert that the page has no horizontal document overflow at the current
 * viewport. The 1px tolerance absorbs sub-pixel rounding on mobile
 * viewports with a visible scrollbar.
 */
export async function expectNoHorizontalDocumentScroll(page: Page): Promise<void> {
  const width = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(
    width.scrollWidth,
    `horizontal document overflow: scrollWidth=${width.scrollWidth}, clientWidth=${width.clientWidth}`,
  ).toBeLessThanOrEqual(width.clientWidth + 1);
}

/**
 * Open the first selectable row of a list/tree.
 *
 * Two row conventions exist in the app (see ConceptSplitView's position
 * memory): treeitems carry `aria-selected="true"`, artifact rows carry
 * `aria-pressed="true"`. A mobile list may render either, so this helper
 * tries both instead of encoding one editor's markup into the smoke test.
 */
export async function openFirstListItem(page: Page): Promise<void> {
  const row = page.locator('[aria-selected="true"], [aria-pressed="true"]').first();
  await expect(row).toBeVisible();
  await row.click();
}
