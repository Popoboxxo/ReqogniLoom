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
 * Selector for a genuine list/tree row.
 *
 * Two row conventions exist in the app (see ConceptSplitView's position
 * memory): `WorkspaceTree` renders `<li role="treeitem" aria-selected>`,
 * `ArtifactRow` renders `<div role="button" aria-pressed>`. Both carry an ARIA
 * selection attribute — and so do real controls: `RequirementViewToggle` uses
 * `<button aria-pressed>` and is rendered *before* the rows on /requirements.
 * A bare `[aria-selected], [aria-pressed]` query therefore clicks the view
 * toggle on a fresh route and opens no detail (the M5 regression this helper
 * must not reintroduce). Every toolbar/view toggle in the app is a real
 * `<button>`, so excluding native controls removes them without encoding one
 * editor's markup into the helper.
 */
export const LIST_ROW_SELECTOR = [
  '[role="treeitem"]:not(button)',
  '[aria-pressed]:not(button):not(input):not(select)',
  '[aria-selected]:not(button):not(input):not(select)',
].join(', ');

/**
 * Open the first genuine row of a list/tree and wait for the mobile detail.
 *
 * On a phone the detail replaces the list (Spec §4.1 / REQ-209): the list pane
 * becomes `display: none` and the shared back control appears. Waiting for
 * that indicator turns a mis-targeted click into an actionable timeout instead
 * of a silently passing smoke step.
 */
export async function openFirstListItem(page: Page): Promise<void> {
  // PR #1888: a phone always starts in the list pane. Wait for it before
  // locating a row so a detail-on-mount regression fails here with an
  // actionable "list pane hidden" timeout rather than deep in the locator.
  await expect(page.getByTestId('splitview-list')).toBeVisible();
  const row = page.locator(LIST_ROW_SELECTOR).first();
  await expect(row).toBeVisible();
  await row.click();
  await expect(page.getByTestId('splitview-detail')).toBeVisible();
  await expect(page.getByTestId('splitview-back')).toBeVisible();
}
