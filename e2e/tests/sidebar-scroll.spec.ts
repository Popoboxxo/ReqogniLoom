// Issue #720: Sidebar not scrollable at small viewport heights
// Validates that the scrollable sidebar region actually scrolls when the
// viewport is shorter than the sidebar content, and that all nav links
// (including the bottom-most admin group) are reachable via scroll.
//
// Outcome: PASS = the QA tooling in #720 measured the wrong DOM node
//          (the outer <nav> wrapper, not the inner scroll region).
//          FAIL = there is a genuine CSS regression.

import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Sidebar scroll at small viewport heights (#720)', () => {
  test('scroll region overflows and bottom nav groups are reachable at 437px viewport height', async ({ page }) => {
    // Login at normal viewport first (UI login is reliable at default size).
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);

    // Navigate to a page where the sidebar is visible, THEN shrink the viewport.
    // This simulates the real user scenario: user has sidebar open, then
    // resizes the browser window to a small height.
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.waitForSelector('[data-testid="sidebar-nav-scroll-content"]', { timeout: 10000 });

    // Now shrink the viewport to the height from the #720 QA report
    await page.setViewportSize({ width: 1280, height: 437 });
    // Wait for layout to settle after resize
    await page.waitForTimeout(500);

    // The sidebar scroll region should still be present
    const scrollContent = page.locator('[data-testid="sidebar-nav-scroll-content"]');
    await expect(scrollContent).toBeVisible({ timeout: 5000 });

    // 1. Verify the scroll region actually overflows (scrollHeight > clientHeight).
    //    If this is false, the sidebar content fits and no scroll is needed.
    const scrollHeight = await scrollContent.evaluate((el) => el.scrollHeight);
    const clientHeight = await scrollContent.evaluate((el) => el.clientHeight);
    expect(scrollHeight).toBeGreaterThan(clientHeight);

    // 2. Scroll to the bottom and verify scrollTop actually moved.
    await scrollContent.evaluate((el) => {
      el.scrollTop = el.scrollHeight;
    });
    const scrollTopAfter = await scrollContent.evaluate((el) => el.scrollTop);
    expect(scrollTopAfter).toBeGreaterThan(0);

    // 3. The admin nav group is inside the scroll content but below the fold.
    //    Use scrollIntoView (matching real user behavior) to bring it into
    //    the visible area, then verify it became visible in the viewport.
    const lastNavGroup = page.locator('[data-testid="nav-group-admin"]');
    await lastNavGroup.scrollIntoViewIfNeeded();
    await expect(lastNavGroup).toBeInViewport();
  });
});
