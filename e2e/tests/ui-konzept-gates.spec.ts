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
 * per route. Every computed radius counts except a pill/full radius, which is
 * a deliberate shape, not a second standard: it is classified separately (see
 * the Radius rule below) and does not count against MAX_BUTTON_RADII. The two
 * radii that should therefore appear are the standard `--radius-btn` (6 px)
 * and, where a segmented control's inner corners are squared on purpose, a
 * `0px` corner — anything else is a second standard.
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
 *  - Excluded: `[data-testid="workspace-card-clickable-region"]` — the whole
 *    surface of a dashboard workspace card is a click region, not a control.
 *    Its height (200+ px) and its `--radius-lg` corner come from the card
 *    layout, so counting it would make the dashboard's three card rows the
 *    button standard. Same reason tree rows are excluded, and deliberately
 *    the narrow inner testid rather than the `workspace-card` prefix: the
 *    card's real `workspace-card-preset-badge` button is a SIBLING of this
 *    region (rendered outside it to avoid button-inside-button), so a prefix
 *    exclusion would also drop a legitimate button from the measurement.
 *  - Height: `getBoundingClientRect().height`, rounded to whole px. Exactly
 *    24 px is the icon-button height (`--btn-h-xs`, WCAG 2.5.8 target size)
 *    and is classified SEPARATELY (ENT-C6 = B): it is reported in the
 *    assertion message but does not count against MAX_BUTTON_HEIGHTS.
 *  - Radius: computed `border-top-left-radius`, rounded (all four corners
 *    share one token by construction). A pill/full radius (`--radius-full`,
 *    9999 px) is classified SEPARATELY — it is reported in the assertion
 *    message but does not count against MAX_BUTTON_RADII. Pill shapes are a
 *    deliberate full-round treatment (badges, toggles, pill buttons), not a
 *    competing button standard. Every radius other than that pill value is
 *    counted, including `0px`: the squared inner corner of a butted
 *    segmented tab is a real shape on the route, not an excluded one. The two
 *    radii that should appear are therefore `--radius-btn` and, where a
 *    squared corner is unavoidable, `0px`.
 *  - `networkidle` before measuring: lazy-loaded buttons and dialogs must not
 *    make the gate flaky (plan §9, "E2E-Gate flackert durch dynamische
 *    Buttons").
 *  - Reporting: every distinct height and radius bucket keeps up to three
 *    example elements (`tag.firstClass[data-testid=...]`) and the whole map is
 *    `console.log`ged for every route, passing or failing. This changes no
 *    threshold and no classification — it only makes the verdict actionable,
 *    because a gate that reports only the number sends the reader hunting.
 */
const MAX_BUTTON_HEIGHTS = 3;
const MAX_BUTTON_RADII = 2;
/** `--btn-h-xs` — icon buttons. Counted and reported, but not a standard height. */
const ICON_BUTTON_HEIGHT_PX = 24;
/** `--radius-full` — pill/full shape. Reported, but not a counted button radius. */
const PILL_RADIUS_PX = 9999;

/**
 * Routes that are still over the C1 target — a ratchet in E2E form (plan §8
 * "C1 Gate"). The constant stays as the ratchet's carrier: an entry turns that
 * route's `[C1]` test into a `test.fixme`, i.e. it documents a known
 * over-target route instead of a guess.
 *
 * The component CSS was reworked to read the `--btn-h-*` / `--radius-btn` /
 * `--radius-full` scale, and the static scanner now also selects the
 * capitalised `*Btn` call sites where the residual radii lived, so no known
 * over-target route remains and the map is EMPTY. That is an untested claim,
 * not a measurement: the E2E gate has NOT yet been run against this state. The
 * gate is the authority — it decides, and a route that measures over target
 * goes back in WITH its measured values (date, preset, heights/radii, and what
 * was left unchanged), never with an estimate.
 */
const C1_PENDING_ROUTES: Record<string, string> = {};

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
  /**
   * Up to `SAMPLES_PER_BUCKET` example elements per distinct bucket, keyed
   * `"<kind> <value>"` (e.g. `"height 28"`, `"pill radius 9999"`), so the
   * report names the offender instead of only counting it. Reporting only —
   * it feeds no classification and no assertion.
   */
  samples: Record<string, string[]>;
}

/** How many example elements to keep per distinct bucket. */
const SAMPLES_PER_BUCKET = 3;
/** Classes shown per example element (a hashed module class list is unreadable). */
const SAMPLE_CLASS_LIMIT = 2;
/** Maximum length of one example descriptor. */
const SAMPLE_MAX_LENGTH = 60;

async function measureButtonGeometry(page: Page): Promise<ButtonGeometry> {
  return page.evaluate(
    ({ iconButtonHeight, pillRadius, samplesPerBucket, classLimit, maxLength }) => {
      const EXCLUDED_ANCESTORS = [
        '[data-testid="workflow-canvas"]',
        '.react-flow',
        '[data-testid^="diagram-canvas"]',
        '[data-testid="workspace-card-clickable-region"]',
      ];
      const TREES = '[data-testid$="-tree"]';
      const heights = new Set<number>();
      const iconHeights = new Set<number>();
      const radii = new Set<number>();
      const pillRadii = new Set<number>();
      const samples = new Map<string, string[]>();
      let measured = 0;

      // `tag.firstClass[data-testid=...]`, truncated: enough to find the
      // element in the component tree, short enough to read in a CI log.
      // `className` is a plain string here (HTMLElement), so no iterable/
      // DOMTokenList helper is needed.
      const describe = (el: HTMLElement): string => {
        const classes = String(el.className)
          .split(/\s+/)
          .filter(Boolean)
          .slice(0, classLimit)
          .join('.');
        const testId = el.getAttribute('data-testid');
        let text = el.tagName.toLowerCase() + (classes ? `.${classes}` : '');
        if (testId) text += `[data-testid=${testId}]`;
        return text.length > maxLength ? `${text.slice(0, maxLength - 3)}...` : text;
      };
      const remember = (key: string, el: HTMLElement): void => {
        const bucket = samples.get(key);
        if (bucket === undefined) samples.set(key, [describe(el)]);
        else if (bucket.length < samplesPerBucket) bucket.push(describe(el));
      };

      const candidates = document.querySelectorAll<HTMLElement>('button, [role="button"]');
      for (const el of candidates) {
        if (el.offsetWidth === 0) continue;
        if (EXCLUDED_ANCESTORS.some((selector) => el.closest(selector))) continue;
        if (el.getAttribute('role') === 'button' && el.closest(TREES)) continue;

        const height = Math.round(el.getBoundingClientRect().height);
        const radius = Math.round(parseFloat(getComputedStyle(el).borderTopLeftRadius) || 0);
        measured++;
        if (height === iconButtonHeight) {
          iconHeights.add(height);
          remember(`icon height ${height}`, el);
        } else {
          heights.add(height);
          remember(`height ${height}`, el);
        }
        if (radius === pillRadius) {
          pillRadii.add(radius);
          remember(`pill radius ${radius}`, el);
        } else {
          radii.add(radius);
          remember(`radius ${radius}`, el);
        }
      }

      return {
        heights: [...heights].sort((a, b) => a - b),
        iconHeights: [...iconHeights].sort((a, b) => a - b),
        radii: [...radii].sort((a, b) => a - b),
        pillRadii: [...pillRadii].sort((a, b) => a - b),
        measured,
        samples: Object.fromEntries(samples),
      };
    },
    {
      iconButtonHeight: ICON_BUTTON_HEIGHT_PX,
      pillRadius: PILL_RADIUS_PX,
      samplesPerBucket: SAMPLES_PER_BUCKET,
      classLimit: SAMPLE_CLASS_LIMIT,
      maxLength: SAMPLE_MAX_LENGTH,
    },
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

/**
 * The per-bucket sample list, one indented line per distinct height/radius.
 *
 * A gate that reports only the number sends the reader hunting through the DOM
 * for the element that produced it; it must name the offender. The list is
 * emitted for every route — a route that passes still spends its budget on
 * three specific elements, and that is exactly what a later regression report
 * needs to compare against.
 */
function describeGeometrySamples(geometry: ButtonGeometry): string {
  return Object.entries(geometry.samples)
    .map(([bucket, elements]) => `    ${bucket}: ${elements.join(' | ')}`)
    .join('\n');
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

      // Unconditional, before the assertions: a passing route reports which
      // elements produced which height just like a failing one, so a future
      // over-budget report can be diffed against a known good run instead of
      // re-measured from scratch.
      console.log(`[C1] ${route.path} — ${detail}\n${describeGeometrySamples(geometry)}`);

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
