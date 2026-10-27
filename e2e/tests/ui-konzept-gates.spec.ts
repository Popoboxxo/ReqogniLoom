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
 * A third block (below the 16.1 describe) carries the C1 button-geometry
 * gate from Plan C (T-C1-1, #1258): ≤3 button heights and ≤2 radii per
 * route. It is not a chapter-16.1 gate, hence its own `[C1]` title prefix.
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

/**
 * C1 button-geometry standard (Plan C §1 Ziel 2 + §3.2, task T-C1-1,
 * issue #1258; ENT-C6 = B): at most 3 distinct button heights (the
 * `--btn-h-sm/md/lg` scale, i.e. 32/36/44 px) and at most 2 distinct radii
 * per route. The counted radii are the standard `--radius-btn` (6 px) plus
 * `--radius-md` (12 px); a pill/full radius is a deliberate shape, not a
 * second standard, so it is classified separately (see the Radius rule
 * below) and does not count against MAX_BUTTON_RADII.
 *
 * Measurement rules (literal, per the task spec — rationale inline):
 *
 *  - Elements: `button, [role="button"]`. Both are "buttons" to a user; the
 *    ARIA role is how the codebase renders click-only rows/cards.
 *  - Only visible elements: `offsetWidth > 0`. A `display: none` subtree or a
 *    collapsed menu must not contribute geometry to the count.
 *  - Excluded: anything inside `[data-testid="workflow-canvas"]`,
 *    `.react-flow`, `[data-testid^="diagram-canvas"]`, and rows with
 *    `role="button"` inside `[data-testid$="-tree"]`. Canvas nodes and tree
 *    rows are graph/navigation surfaces whose size is driven by their
 *    content (node label, row text), not by the button scale — counting them
 *    would gate canvas layout instead of button styling.
 *  - Height: `getBoundingClientRect().height`, rounded to whole px. Exactly
 *    24 px is the icon-button height (`--btn-h-xs`, WCAG 2.5.8 target size)
 *    and is classified SEPARATELY (ENT-C6 = B): it is reported in the
 *    assertion message but does not count against MAX_BUTTON_HEIGHTS.
 *  - Radius: computed `border-top-left-radius`, rounded (all four corners
 *    share one token by construction). A pill/full radius (`--radius-full`,
 *    9999 px) is classified SEPARATELY — it is reported in the assertion
 *    message but does not count against MAX_BUTTON_RADII. Pill shapes are a
 *    deliberate full-round treatment (badges, toggles, pill buttons), not a
 *    competing button standard; the two radii that are actually enforced are
 *    `--radius-btn` (6 px) and `--radius-md` (12 px).
 *  - `networkidle` before measuring: lazy-loaded buttons and dialogs must not
 *    make the gate flaky (plan §9, "E2E-Gate flackert durch dynamische
 *    Buttons").
 */
const MAX_BUTTON_HEIGHTS = 3;
const MAX_BUTTON_RADII = 2;
/** `--btn-h-xs` — icon buttons. Counted and reported, but not a standard height. */
const ICON_BUTTON_HEIGHT_PX = 24;
/** `--radius-full` — pill/full shape. Reported, but not a counted button radius. */
const PILL_RADIUS_PX = 9999;

/**
 * Routes that were still over the C1 target when this gate was introduced
 * (ratchet in E2E form, plan §8 "C1 Gate"). Each C1 PR removes its own
 * routes: T-C1-3 -> `/system-settings`, T-C1-4 -> `/workflows`, `/settings`,
 * `/`, T-C1-5/T-C1-6 -> the remainder. This list may only shrink.
 *
 * Values are the live measurement of 2026-10-23 (seeded demo workspace,
 * extended preset) — no route is listed or omitted on a guess. PR-C12
 * (T-C1-4/T-C1-5) removed `/`, `/settings` and `/workflows`, whose scanned
 * button rules are now all on `--btn-h-*`/`--radius-btn`; the surviving
 * entries keep that baseline measurement and name what PR-C12 did NOT change.
 */
const C1_PENDING_ROUTES: Record<string, string> = {
  '/requirements': '3 heights / 3 radii measured — PR-C12 tokenised the scanned radii; residual radii come from unscanned .xxxBtn call sites',
  '/impact': '4 heights / 2 radii measured — heights over target; PR-C12 changed radii only',
  '/baselines': '3 heights / 3 radii measured — no C1-scanned button on this route; unscanned radii remain',
  '/adrs': '3 heights / 3 radii measured — no C1-scanned button on this route; unscanned radii remain',
  '/risks': '4 heights / 3 radii measured — heights over target; PR-C12 changed radii only',
  '/issues': '3 heights / 3 radii measured — no C1-scanned button on this route; unscanned radii remain',
  '/testcases': '3 heights / 3 radii measured — no C1-scanned button on this route; unscanned radii remain',
  '/test-runs': '3 heights / 3 radii measured — PR-C12 tokenised the editor/grid radii; TestRunsList .xxxBtn radii remain',
  '/import': '4 heights / 2 radii measured — heights over target (CsvImport padding), untouched by PR-C12',
  '/icds': '3 heights / 3 radii measured — PR-C12 tokenised the scanned radii; IcdDetailPane .xxxBtn radii remain',
  '/diagrams': '3 heights / 3 radii measured — PR-C12 tokenised the scanned radii; DiagramCreateForm .xxxBtn radii remain',
  '/metrics': '3 heights / 3 radii measured — PR-C12 fixed .refreshButton; other call sites unchanged',
  '/audit': '3 heights / 3 radii measured — no C1-scanned button on this route; unscanned radii remain',
  '/system-settings': '4 heights / 4 radii measured (T-C1-3) — owned by the /system-settings PR, not PR-C12',
  '/goals': '3 heights / 3 radii measured — no C1-scanned button on this route; unscanned radii remain',
  '/glossary': '3 heights / 3 radii measured — PR-C12 fixed .btn; other call sites unchanged',
  '/profile': '5 heights / 3 radii measured — heights over target; PR-C12 changed radii only',
};

interface ButtonGeometry {
  /** Distinct rounded heights of non-icon buttons, ascending. */
  heights: number[];
  /** Distinct rounded heights classified as icon buttons (24 px). */
  iconHeights: number[];
  /** Distinct rounded `border-top-left-radius` values, ascending. */
  radii: number[];
  /** Distinct rounded radii classified as pill/full (9999 px), ascending. */
  pillRadii: number[];
  /** Visible, non-excluded buttons the numbers were derived from. */
  measured: number;
}

async function measureButtonGeometry(page: Page): Promise<ButtonGeometry> {
  return page.evaluate(
    ({ iconButtonHeight, pillRadius }) => {
      const EXCLUDED_ANCESTORS = [
        '[data-testid="workflow-canvas"]',
        '.react-flow',
        '[data-testid^="diagram-canvas"]',
      ];
      const TREES = '[data-testid$="-tree"]';
      const heights = new Set<number>();
      const iconHeights = new Set<number>();
      const radii = new Set<number>();
      const pillRadii = new Set<number>();
      let measured = 0;

      const candidates = document.querySelectorAll<HTMLElement>('button, [role="button"]');
      for (const el of candidates) {
        if (el.offsetWidth === 0) continue;
        if (EXCLUDED_ANCESTORS.some((selector) => el.closest(selector))) continue;
        if (el.getAttribute('role') === 'button' && el.closest(TREES)) continue;

        const height = Math.round(el.getBoundingClientRect().height);
        const radius = Math.round(parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0);
        measured++;
        if (height === iconButtonHeight) iconHeights.add(height);
        else heights.add(height);
        if (radius === pillRadius) pillRadii.add(radius);
        else radii.add(radius);
      }

      return {
        heights: [...heights].sort((a, b) => a - b),
        iconHeights: [...iconHeights].sort((a, b) => a - b),
        radii: [...radii].sort((a, b) => a - b),
        pillRadii: [...pillRadii].sort((a, b) => a - b),
        measured,
      };
    },
    { iconButtonHeight: ICON_BUTTON_HEIGHT_PX, pillRadius: PILL_RADIUS_PX },
  );
}

/** One-line classification for the assertion message: what was counted, and how. */
function describeGeometry(geometry: ButtonGeometry): string {
  const icons = geometry.iconHeights.length
    ? `${geometry.iconHeights.join('/')} px icon button(s) excluded from the height count (--btn-h-xs, ENT-C6 = B)`
    : 'no 24 px icon buttons rendered';
  const pills = geometry.pillRadii.length
    ? `${geometry.pillRadii.join('/')} px pill radius/radii excluded from the radius count (--radius-full)`
    : 'no pill-radius buttons rendered';
  return (
    `${geometry.heights.length} height(s) [${geometry.heights.join(', ')}], ` +
    `${geometry.radii.length} radius/radii [${geometry.radii.join(', ')}], ` +
    `${icons}, ${pills} — from ${geometry.measured} visible button(s)`
  );
}

test.describe('[C1] Button geometry (heights + radii per route)', () => {
  test.beforeAll(async () => {
    // Same rationale as the 16.1 block above: the extended preset renders
    // every route's full surface instead of a preset fallback.
    await setWorkspacePreset('extended');
  });

  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  for (const route of ROUTES) {
    test(`[C1] ${route.label}: ≤${MAX_BUTTON_HEIGHTS} button heights, ≤${MAX_BUTTON_RADII} radii`, async ({
      page,
    }) => {
      const pendingReason = C1_PENDING_ROUTES[route.path];
      // Ratchet, not a mute: a pending route is still measured by the C1
      // PRs that remove it, and its measurement stays documented above.
      if (pendingReason) test.fixme(true, pendingReason);

      await page.goto(`${FRONTEND_URL}${route.path}`);
      await page.waitForLoadState('networkidle');
      await expect(page.locator('[data-testid="route-suspense-fallback"]')).not.toBeVisible({
        timeout: 15000,
      });

      const geometry = await measureButtonGeometry(page);
      const detail = `${route.path}: ${describeGeometry(geometry)}`;

      expect(
        geometry.heights.length,
        `${detail} — limit ${MAX_BUTTON_HEIGHTS} heights`
      ).toBeLessThanOrEqual(MAX_BUTTON_HEIGHTS);
      expect(
        geometry.radii.length,
        `${detail} — limit ${MAX_BUTTON_RADII} radii`
      ).toBeLessThanOrEqual(MAX_BUTTON_RADII);
    });
  }
});

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
