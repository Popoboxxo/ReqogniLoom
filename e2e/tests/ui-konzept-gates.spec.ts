/**
 * UI-Konzept Kapitel 16.1 — dynamically checkable structural gates.
 *
 * Task 7.5 (docs/superpowers/plans/Archive/2026-08-01-ui-konzept-vollrollout.md):
 * two of the gates listed in chapter 16.1 cannot be enforced statically
 * (ESLint / a plain grep) and are checked here, parametrized across every
 * route defined in `NavigationShell.tsx`:
 *
 *   1. Exactly one `<h1>` per route ("Kopf-Wildwuchs").
 *   2. At most 3 scroll containers per route ("Scroll-Wildwuchs" — the
 *      audit-era finding was 2 to 5 nested scroll areas per page, see
 *      docs/UI_KONZEPT.md Anhang B).
 *
 * IMPORTANT (per the plan's explicit acceptance criterion and this project's
 * rule set): this spec file is written and reviewed for structural
 * soundness only. It is **not** executed as part of this task — E2E runs
 * require an explicit user request and are not a DoD gate.
 *
 * Route table: derived directly from the `<Route path="..." element={...} />`
 * table in `frontend/src/components/NavigationShell/NavigationShell.tsx`
 * (`AppShell`'s `<Routes>`), not hand-guessed. Only routes reachable with a
 * static path are included — `:id` / `:entityType` parametrized routes
 * (`/needs/:id`, `/requirements/:id`, `/architecture/:id`, `/adrs/:id`,
 * `/risks/:id`, `/issues/:id`, `/testcases/:id`, `/icds/:id`, `/diagrams/:id`,
 * `/diagrams/:id/canvas`, `/diagrams/:id/mermaid`, `/workflows/:entityType`)
 * are deliberately excluded: they require a real, seeded artifact ID that
 * this suite has no stable/known value for (unlike `SEEDED_WORKSPACE_ID`,
 * no `SEEDED_REQUIREMENT_ID` etc. exists in `helpers/auth.ts`). The
 * `/workspace-settings` route is excluded too — it is a pure
 * `<Navigate to="/settings" replace />` redirect, not a page.
 *
 * `/login` is checked separately below: it renders outside `AuthGate` /
 * `AppShell` (no sidebar, no `<main role="main">`), so it does not fit the
 * authenticated-route loop's shared `beforeEach`.
 */
import { test, expect, type Page } from '@playwright/test';
import {
  loginAsAdmin,
  setWorkspaceId,
  setWorkspacePreset,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/** Maximum number of nested scroll containers allowed per route (16.1). */
const MAX_SCROLL_CONTAINERS = 3;

interface RouteUnderTest {
  /** Path as registered in NavigationShell.tsx's <Routes>. */
  path: string;
  /** Human-readable label used in test titles. */
  label: string;
}

// Static routes from NavigationShell.tsx's `AppShell` <Routes> block, in the
// order they're declared there. `/` (DashboardViews) through `/profile`
// (UserProfileSettings) — see the file header comment for exclusions.
const ROUTES: RouteUnderTest[] = [
  { path: '/', label: 'Dashboard' },
  { path: '/needs', label: 'Needs' },
  { path: '/requirements', label: 'Requirements' },
  { path: '/architecture', label: 'Architecture' },
  { path: '/traceability', label: 'Traceability' },
  { path: '/impact', label: 'Impact' },
  { path: '/baselines', label: 'Baselines' },
  { path: '/reviews', label: 'Reviews' },
  { path: '/adrs', label: 'ADRs' },
  { path: '/risks', label: 'Risks' },
  { path: '/issues', label: 'Issues' },
  { path: '/testcases', label: 'Test cases' },
  { path: '/test-runs', label: 'Test runs' },
  { path: '/import', label: 'CSV import' },
  { path: '/icds', label: 'ICDs' },
  { path: '/diagrams', label: 'Diagrams' },
  { path: '/metrics', label: 'Metrics' },
  { path: '/audit', label: 'Audit' },
  { path: '/settings', label: 'Workspace settings' },
  { path: '/system-settings', label: 'System settings' },
  { path: '/goals', label: 'Goals' },
  { path: '/glossary', label: 'Glossary' },
  { path: '/workflows', label: 'Workflows' },
  { path: '/profile', label: 'User profile' },
];

/**
 * Counts DOM elements that are *actual* scroll containers: an
 * `overflow-y`/`overflow-x` of `auto` or `scroll` (computed style) AND
 * content that actually overflows the box (`scrollHeight > clientHeight` or
 * `scrollWidth > clientWidth`). A plain `overflow: auto` in CSS that never
 * ends up scrollable (short list, empty state, etc.) must not count —
 * that's exactly the false-positive this two-part check avoids.
 *
 * Zero-size elements (`clientHeight`/`clientWidth` of 0 — e.g. collapsed or
 * `display: none` subtrees) are excluded, since they cannot be a container
 * a user actually scrolls.
 */
async function countScrollContainers(page: Page): Promise<number> {
  return page.evaluate(() => {
    const SCROLLABLE_OVERFLOW = new Set(['auto', 'scroll']);
    const all = document.querySelectorAll<HTMLElement>('*');
    let count = 0;
    for (const el of all) {
      if (el.clientHeight === 0 || el.clientWidth === 0) continue;
      const style = window.getComputedStyle(el);
      const scrollsY =
        SCROLLABLE_OVERFLOW.has(style.overflowY) && el.scrollHeight > el.clientHeight + 1;
      const scrollsX =
        SCROLLABLE_OVERFLOW.has(style.overflowX) && el.scrollWidth > el.clientWidth + 1;
      if (scrollsY || scrollsX) count++;
    }
    return count;
  });
}

test.describe('[UI-KONZEPT 16.1] Structural gates (h1 + scroll containers)', () => {
  test.beforeAll(async () => {
    // Extended preset unlocks the widest route/feature surface (baselines,
    // reviews, audit, workflows, ...) so every route in the table above
    // renders its full page rather than a "not available in this preset"
    // fallback. Mirrors the pattern in helpers/auth.ts's own doc comment.
    await setWorkspacePreset('extended');
  });

  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  for (const route of ROUTES) {
    test(`[16.1] ${route.label} (${route.path}): exactly one <h1>`, async ({ page }) => {
      await page.goto(`${FRONTEND_URL}${route.path}`);
      await page.waitForLoadState('networkidle');

      // Route-transition Suspense fallback must resolve before the heading
      // count is meaningful. Scoped to its own data-testid, not a bare
      // role="status" selector — some routes (e.g. WorkflowEditor) render
      // a persistent, legitimate role="status" live-status bar that never
      // disappears and isn't a loading indicator.
      await expect(page.locator('[data-testid="route-suspense-fallback"]')).not.toBeVisible({
        timeout: 15000,
      });

      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
    });

    test(`[16.1] ${route.label} (${route.path}): at most ${MAX_SCROLL_CONTAINERS} scroll containers`, async ({
      page,
    }) => {
      await page.goto(`${FRONTEND_URL}${route.path}`);
      await page.waitForLoadState('networkidle');
      await expect(page.locator('[data-testid="route-suspense-fallback"]')).not.toBeVisible({
        timeout: 15000,
      });
      // Content is present once the page's own heading has rendered — a
      // stand-in for "the route finished loading" that works identically
      // across all page types (list, dashboard, editor).
      await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);

      const scrollContainers = await countScrollContainers(page);
      expect(
        scrollContainers,
        `${route.path} has ${scrollContainers} scroll containers (limit ${MAX_SCROLL_CONTAINERS})`
      ).toBeLessThanOrEqual(MAX_SCROLL_CONTAINERS);
    });
  }
});

test.describe('[UI-KONZEPT 16.1] Structural gates — /login (outside AuthGate)', () => {
  test('[16.1] Login: exactly one <h1>', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/login`);
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);
  });

  test(`[16.1] Login: at most ${MAX_SCROLL_CONTAINERS} scroll containers`, async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/login`);
    await expect(page.getByRole('heading', { level: 1 })).toHaveCount(1);

    const scrollContainers = await countScrollContainers(page);
    expect(
      scrollContainers,
      `/login has ${scrollContainers} scroll containers (limit ${MAX_SCROLL_CONTAINERS})`
    ).toBeLessThanOrEqual(MAX_SCROLL_CONTAINERS);
  });
});
