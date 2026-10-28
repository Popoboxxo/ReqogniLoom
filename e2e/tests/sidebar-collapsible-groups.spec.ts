// Plan C / T-C4-4 (C-L6, finding R19): at 1366×768 only 11 of 27 nav links
// were visible above the fold, so the sidebar's group headers became
// disclosure toggles whose state is the user-level Q1 preference
// `ui.sidebar.collapsed_groups`.
//
// Scope of this case (measured, see the note at the end): it pins the
// disclosure contract, that a collapsed group's links really leave the
// accessibility tree, and that the region's scroll length shrinks by the
// collapsed panels' height — i.e. the space the two bottom groups occupied is
// actually reclaimed. Every link of "overview" through "architecture" must
// stay present and reachable, and the case must not have introduced clipping.
//
// Links are addressed by panel (`data-testid="nav-group-<id>"`) and href, not
// by label, so the case does not depend on the active UI language or on which
// preset-gated entries the seeded workspace happens to show.

import { test, expect, type Page } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/** Groups whose links must all stay reachable after the two below collapse. */
const UPPER_GROUPS = ['overview', 'requirements', 'architecture'] as const;
/** Groups collapsed by this case (the two that push everything down). */
const COLLAPSED_GROUPS = ['admin', 'test'] as const;

const SCROLL_CONTENT = '[data-testid="sidebar-nav-scroll-content"]';

/**
 * Collapse `groupId` unless it is already collapsed.
 *
 * The preference is persisted per user, so a previous (or interrupted) run may
 * already have left a group closed — clicking unconditionally would then
 * *open* it and invert the premise of this case.
 */
async function collapseGroup(page: Page, groupId: string): Promise<void> {
  const toggle = page.locator(`[data-testid="sidebar-group-toggle-${groupId}"]`);
  await expect(toggle).toBeVisible({ timeout: 10000 });
  if ((await toggle.getAttribute('aria-expanded')) === 'true') {
    await toggle.click();
  }
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
}

test.describe('Sidebar collapsible groups (T-C4-4)', () => {
  test.use({ viewport: { width: 1366, height: 768 } });

  test('collapsing admin and test reclaims their space at 1366x768 without breaking overview..architecture', async ({
    page,
  }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);

    // A route inside "requirements" so no group the case measures is pinned
    // open by the active-route guard, and so the sidebar is actually rendered.
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.waitForSelector(SCROLL_CONTENT, { timeout: 10000 });

    const scrollContent = page.locator(SCROLL_CONTENT);

    // The height the two panels occupy while expanded — the amount of scroll
    // length the collapse has to give back. Measured before collapsing,
    // because a hidden element has no layout and would report 0; a group left
    // collapsed by an earlier run is expanded once for the measurement.
    let collapsedHeight = 0;
    for (const groupId of COLLAPSED_GROUPS) {
      const toggle = page.locator(`[data-testid="sidebar-group-toggle-${groupId}"]`);
      await expect(toggle).toBeVisible({ timeout: 10000 });
      if ((await toggle.getAttribute('aria-expanded')) === 'false') {
        await toggle.click();
        await expect(toggle).toHaveAttribute('aria-expanded', 'true');
      }
      const panelId = await toggle.getAttribute('aria-controls');
      collapsedHeight += await page
        .locator(`#${panelId}`)
        .evaluate((el) => el.scrollHeight);
    }

    // Captured with every group open, so the delta below is purely the two
    // collapsed panels.
    const heightBefore = await scrollContent.evaluate((el) => el.scrollHeight);

    for (const groupId of COLLAPSED_GROUPS) {
      await collapseGroup(page, groupId);
    }

    // 1. The disclosure contract: aria-expanded false, aria-controls points at
    //    the panel, and that panel is hidden with no visible links left.
    for (const groupId of COLLAPSED_GROUPS) {
      const toggle = page.locator(`[data-testid="sidebar-group-toggle-${groupId}"]`);
      const panelId = await toggle.getAttribute('aria-controls');
      expect(panelId).toBe(`sidebar-nav-group-panel-${groupId}`);

      const panel = page.locator(`#${panelId}`);
      await expect(panel).toBeHidden();
      await expect(panel.locator('a:visible')).toHaveCount(0);
    }

    // 2. The space is genuinely reclaimed: the scroll region is shorter by the
    //    collapsed panels' height, so the bottom groups no longer need to be
    //    scrolled past.
    const heightAfter = await scrollContent.evaluate((el) => el.scrollHeight);
    expect(collapsedHeight).toBeGreaterThan(100);
    expect(heightBefore - heightAfter).toBeGreaterThanOrEqual(collapsedHeight - 1);

    // 3. Nothing above the collapsed groups was clipped or dropped: every link
    //    of overview..architecture is still rendered and reachable, and the
    //    last one scrolls into view inside the region.
    let assertedLinks = 0;
    for (const groupId of UPPER_GROUPS) {
      const panel = page.locator(`[data-testid="nav-group-${groupId}"]`);
      await expect(panel).toBeVisible();

      const links = panel.locator('a');
      const count = await links.count();
      expect(count, `group "${groupId}" should render at least one link`).toBeGreaterThan(0);

      for (let index = 0; index < count; index += 1) {
        const link = links.nth(index);
        const href = await link.getAttribute('href');
        expect(href, `${groupId} link ${index} must carry an href`).toBeTruthy();
        await link.scrollIntoViewIfNeeded();
        await expect(link, `${groupId} link ${href} must be reachable`).toBeInViewport();
        assertedLinks += 1;
      }
    }
    // The whole point of the change: more than the 11 links the finding
    // measured are rendered above the collapsed sections.
    expect(assertedLinks).toBeGreaterThan(11);

    // Note (DoD deviation, measured 2026-10-28): the plan's wording "after
    // collapsing admin and test, every link from overview to architecture is
    // visible without scrolling" is not attainable at 1366×768 — the pinned
    // footer leaves the scroll region ~484 px tall, while the three upper
    // groups alone need ~702 px. Collapsing the two *lower* groups cannot move
    // content above them into view; it shortens the region (assertion 2) and
    // keeps everything reachable (assertion 3). The DoD wording needs a
    // follow-up decision (row height or folding the workspace switcher), which
    // is outside T-C4-4. Escalated to the plan owner.
  });
});
