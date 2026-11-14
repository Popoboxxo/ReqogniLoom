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
 * Wait until the sidebar nav has finished its asynchronous first render.
 *
 * WHY THIS EXISTS (measured 2026-11-14 on the #1762 inspector branch): the nav
 * is populated by two independent async sources — the workspace list (which
 * mounts the pinned footer switcher) and the permission/preset query that
 * decides which entries a workspace shows. `waitForSelector` on the scroll
 * container resolves during the first frame, before either has landed. Sampled
 * at 1366×768 on the same page, back-to-back:
 *
 *   t0      : 28 links, clientHeight 531, scrollHeight 1009, no switcher
 *   t + 1.5 s: 30 links, clientHeight 500, scrollHeight 1202, switcher mounted
 *
 * A `scrollHeight` read taken in the t0 layout is therefore not comparable with
 * one taken after the nav settled, and that is exactly how this case went red:
 * the "space is reclaimed" delta came out as 225 px against a 409 px panel
 * height, because the *baseline* had been measured in the pre-settle layout
 * (1009 - (1202 - 409) ≈ 216).
 *
 * Both conditions are state-based, not a sleep: the switcher is the last pinned
 * node to mount, and the region counts as settled once five consecutive
 * animation frames agree on clientHeight, scrollHeight and link count.
 */
async function waitForNavSettled(page: Page): Promise<void> {
  await expect(
    page.locator('[data-testid="workspace-switcher"]'),
    'the sidebar footer (workspace switcher) marks the end of the nav\'s first render'
  ).toHaveCount(1, { timeout: 15000 });

  await page.evaluate(async (selector) => {
    const el = document.querySelector(selector) as HTMLElement | null;
    if (!el) throw new Error(`nav scroll container ${selector} is not rendered`);
    const snapshot = () =>
      `${el.clientHeight}|${el.scrollHeight}|${el.querySelectorAll('a').length}`;
    const deadline = performance.now() + 15000;
    let previous = snapshot();
    let stableFrames = 0;
    while (performance.now() < deadline) {
      // eslint-disable-next-line no-await-in-loop - one frame at a time is the point
      await new Promise((resolve) => requestAnimationFrame(() => resolve(null)));
      const current = snapshot();
      stableFrames = current === previous ? stableFrames + 1 : 0;
      previous = current;
      if (stableFrames >= 5) return;
    }
    throw new Error(`sidebar nav did not settle within 15s (last sample: ${previous})`);
  }, SCROLL_CONTENT);
}

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

/**
 * Read the persisted disclosure state of the groups this case touches.
 *
 * WHY (#1762 M1 live run): that preference is stored per user and the nav is
 * shared by every later spec, so a case that collapses "test" and walks away
 * leaves `/baselines` hidden behind that collapsed panel. `se-workflow.spec.ts`
 * asserts exactly that link is visible and went red with
 *
 *   locator resolved to <a href="/baselines" …>Baselines</a>
 *   unexpected value "hidden"
 *
 * — in a *different* shard, i.e. the failure had no visible cause in its own
 * file. Snapshotting here and restoring in the `afterEach` hook below keeps this
 * case honest about what it changes (it is about the disclosure contract, not
 * about leaving the user's sidebar folded).
 */
async function readDisclosureState(page: Page, groupIds: readonly string[]): Promise<boolean[]> {
  const state: boolean[] = [];
  for (const groupId of groupIds) {
    const toggle = page.locator(`[data-testid="sidebar-group-toggle-${groupId}"]`);
    state.push((await toggle.getAttribute('aria-expanded')) === 'true');
  }
  return state;
}

/** Click any touched toggle whose `aria-expanded` differs from `wantExpanded`. */
async function restoreDisclosureState(
  page: Page,
  groupIds: readonly string[],
  wantExpanded: readonly boolean[]
): Promise<void> {
  for (const [index, groupId] of groupIds.entries()) {
    const toggle = page.locator(`[data-testid="sidebar-group-toggle-${groupId}"]`);
    if ((await toggle.count()) === 0) continue;
    const expanded = (await toggle.getAttribute('aria-expanded')) === 'true';
    if (expanded !== wantExpanded[index]) {
      await toggle.click();
      await expect(toggle).toHaveAttribute('aria-expanded', String(wantExpanded[index]));
    }
  }
}

test.describe('Sidebar collapsible groups (T-C4-4)', () => {
  test.use({ viewport: { width: 1366, height: 768 } });

  /**
   * Disclosure state as found by this case, restored after it (see
   * `readDisclosureState` for why the case must not leave the sidebar folded).
   * `null` until the test has read it, so a failure before that point does not
   * try to restore a guess.
   */
  let disclosureAsFound: boolean[] | null = null;

  test.afterEach(async ({ page }) => {
    if (!disclosureAsFound) return;
    await restoreDisclosureState(page, COLLAPSED_GROUPS, disclosureAsFound);
    disclosureAsFound = null;
  });

  test('collapsing admin and test reclaims their space at 1366x768 without breaking overview..architecture', async ({
    page,
  }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);

    // A route inside "requirements" so no group the case measures is pinned
    // open by the active-route guard, and so the sidebar is actually rendered.
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.waitForSelector(SCROLL_CONTENT, { timeout: 10000 });
    await waitForNavSettled(page);

    const scrollContent = page.locator(SCROLL_CONTENT);
    disclosureAsFound = await readDisclosureState(page, COLLAPSED_GROUPS);

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
    const before = await scrollContent.evaluate((el) => ({
      clientH: el.clientHeight,
      scrollH: el.scrollHeight,
    }));
    const heightBefore = before.scrollH;

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
    // The reclaim can never exceed the overflow the region had before the
    // collapse: when the nav is shorter than the two panels are tall (a
    // workspace with few entries, or a taller viewport), the region stops
    // overflowing at some point and `scrollHeight` floors at `clientHeight`.
    // Both outcomes mean "the space is reclaimed"; only a delta of zero — or a
    // region that grew — would break the contract this case pins.
    const overflowBefore = Math.max(0, heightBefore - before.clientH);
    expect(
      heightBefore - heightAfter,
      `collapsing ${COLLAPSED_GROUPS.join('+')} must shorten the nav region ` +
        `(panels ${collapsedHeight}px, region overflow before ${overflowBefore}px, ` +
        `scrollHeight ${heightBefore} -> ${heightAfter})`
    ).toBeGreaterThanOrEqual(Math.min(collapsedHeight, overflowBefore) - 1);

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
