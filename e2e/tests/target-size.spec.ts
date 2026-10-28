/**
 * WCAG 2.2 SC 2.5.8 "Target Size (Minimum)" — measured in a real browser.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * The repo already gates hit targets, but only as *CSS declarations*:
 * `frontend/src/test/interactive-hit-targets.test.ts` and
 * `frontend/src/test/form-control-hit-targets.test.ts` resolve
 * `min-height`/`min-width` tokens out of the stylesheets. jsdom has no layout
 * engine, so those assertions can be perfectly green while the rendered box is
 * still below the floor. A declaration can also be overridden by a later,
 * higher-specificity rule, clamped by a fixed `height`, or shrunk by a flex
 * parent — none of which a stylesheet read can see. The two defects the
 * declaration tests missed (#1395: a 24x20 ID-chip copy button, a 22x22 row
 * delete button) were found by hand-measuring the browser; nothing in CI proved
 * the rendered box, which is the hole this spec closes.
 *
 * Both of those defects were REAL and are FIXED in the same change that added
 * this spec: the shared control floor now reaches the rendered copy/delete
 * buttons. They were first pinned in `KNOWN_SUB_TARGET_ALLOWANCES` with their
 * measured boxes so the gate could land without pretending; the product fixes
 * then made those pinned targets pass, which turned this spec red ("the
 * allowance is stale") until the entries were deleted. That red → empty
 * transition is the ratchet doing its job, and it is why the mechanism stays
 * in place with an EMPTY list instead of being removed with the entries.
 *
 * This spec closes that gap: it measures the boxes Playwright lays out
 * (`locator.boundingBox()`), on real routes, against the 24x24 CSS-px floor.
 * No `page.evaluate` / `browser_*` escape computes geometry here — the browser's
 * own layout result is the only input.
 *
 * WHAT IS MEASURED (explicit, named categories — no blanket element sweep)
 * ------------------------------------------------------------------------
 * Per route, inside `<main role="main">`:
 *
 *   1. `button`        — enabled `<button>` elements: the primary action, the
 *                        icon-only buttons (copy/delete/close) and the
 *                        ghost/disclosure variants all render as one.
 *   2. `checkbox/radio`— the control's LABEL ROW, not the raw input
 *                        (ENT-G4=A: an 18px box is acceptable when the row the
 *                        user actually clicks is >=24px tall).
 *   3. `link`          — standalone `<a href>` targets.
 *
 * EXTENDED TARGET EXCEPTIONS (explicit, never a silent filter)
 * ------------------------------------------------------------
 * WCAG 2.5.8 excludes targets that are "in a sentence or block of text" (the
 * *inline* exception). In this app that means links inside running prose and
 * inside hint/help text — clicking them is a text-selection gesture, and their
 * inline box is governed by the line-height of the paragraph, not by a control
 * geometry. `INLINE_PROSE_LINK_CONTEXTS` names every such container; the
 * exclusion is applied mechanically to the link selector (`:not(<container> a)`),
 * so it is visible, reviewable and limited to the containers below. Anything
 * else — every standalone link — must measure >=24x24.
 *
 * FALSIFIABILITY
 * --------------
 * A measurement gate that cannot go red is worthless, so the same
 * `measureTarget` / `targetSizeViolation` / `collectViolations` functions used
 * by the route sweeps are also driven against synthetic DOM (`page.setContent`)
 * in the last describe block: a 20x20 button must be reported, a 24x24 button
 * must not, and an 18px checkbox inside a 28px label row must pass through the
 * label-row path. The self-check therefore exercises the real gate.
 * The synthetic fixtures are marked up with a plain `class`, never with a
 * `data-testid`: the #1113 static drift gate requires every testid literal
 * under `e2e/` to exist in `frontend/src/`, and a fixture-only id does not — it
 * would (correctly) be reported as drift. Offender identification in the
 * self-tests therefore exercises the helper's class fallback, which is also
 * what a real control without a test id gets.
 *
 * Determinism / CI
 * ----------------
 * - No fixed sleeps: `settle()` waits for the lazy-chunk suspense fallback to
 *   disappear and the `<main>` landmark to be visible (same pattern as
 *   `a11y-smoke.spec.ts` / `ui-konzept-gates.spec.ts`).
 * - The list routes (`/requirements`, `/architecture`) do NOT assume seeded
 *   artifacts: `seed_demo` creates none, so both routes legitimately render
 *   `<EmptyState>` and the row-level controls this spec exists for (issue
 *   #1394/#1395: the 22x22 row delete, the 24x20 IdChip copy, the tree's
 *   add-child control) would never be on the page. Each of those routes
 *   therefore ensures ONE row exists through its own quick-create dialog
 *   first, then returns to the list and asserts — non-vacuously, by test id —
 *   that those controls are rendered before measuring them.
 *   The creation is skipped when the route already renders a row, so a retry
 *   (or a second run against a persistent CI database) measures the existing
 *   rows instead of mutating again. That is also what keeps `/architecture`
 *   legal: the seeded workspace uses the EXTENDED rigor preset, where
 *   invariant I5 allows only one root element.
 *   A created artifact is left behind, exactly like the a11y smoke gate's
 *   ArtifactForm fixture; the title carries `Date.now()` + the retry counter
 *   so concurrent runs cannot collide.
 * - The detail route is reached by creating ONE throwaway requirement through
 *   the list's quick form (no seeded artifact id helper exists) and following
 *   the resulting `/requirements/<uuid>` URL.
 *
 * KNOWN RED BASELINE — NOW EMPTY
 * ------------------------------
 * `KNOWN_SUB_TARGET_ALLOWANCES` pins targets that are still below the floor,
 * with their measured box and the reason. It is bidirectional: an entry whose
 * target now passes fails the run ("delete the entry"), so an allowance cannot
 * silently outlive its defect. As of this PR the list is EMPTY and kept: the
 * two entries it held (the 24x20 IdChip copy, the 18px MCP profile link) were
 * real defects, and they were closed by product fixes in the same PR — which is
 * what forced the deletions. Removing the list with the entries would throw
 * away the only mechanism that stops the next sub-target from shipping
 * unrecorded.
 *
 * LOCAL STACK CAVEAT
 * ------------------
 * `make up` runs a PREBUILT `reqogniloom-frontend` image. If that image is
 * older than HEAD, this spec measures the old bundle and reports targets HEAD
 * has already fixed (observed: 24x20 IdChip copy / 22x22 row delete from the
 * pre-#1395 build, and the 259 x 18 MCP profile link from before its fix).
 * That is a stale artefact, not a regression — rebuild the image, or point
 * `FRONTEND_URL` at a dev server (`npm run dev` + `VITE_API_BASE_URL` at the
 * backend, which is how the red/green runs in the PR were captured) before
 * trusting a local red. CI builds from source.
 */
import { test, expect, type Locator, type Page, type TestInfo } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/** WCAG 2.2 SC 2.5.8 minimum target size, in CSS px. */
const MIN_TARGET_PX = 24;

/** The authenticated content landmark every measurement is scoped to. */
const MAIN = 'main[role="main"]';

/**
 * Containers whose links are "in a sentence or block of text" and therefore
 * fall under the WCAG 2.5.8 inline exception. Each entry is a CONTAINER
 * selector; the link sweep excludes `:not(<container> a)`. Add a container
 * deliberately, with its reason — never by widening the sweep.
 */
const INLINE_PROSE_LINK_CONTEXTS: ReadonlyArray<{
  name: string;
  container: string;
  reason: string;
}> = [
  {
    name: 'artifact description prose',
    container: '[data-testid="artifact-field-description"]',
    reason:
      'The description is free prose rendered inline in the form; its links are clicked as ' +
      'part of reading/selecting text, and their box is the paragraph line box.',
  },
  {
    name: 'rich-text / markdown prose',
    container: '[class*="prose"]',
    reason:
      'Markdown bodies (same inline-exception case) — the container class is the one the ' +
      'shared markdown renderer uses.',
  },
];

/** All link targets except the documented inline-prose exception. */
const LINK_SELECTOR =
  `${MAIN} a[href]` +
  INLINE_PROSE_LINK_CONTEXTS.map(({ container }) => `:not(${container} a)`).join('');

type CategoryName = 'button' | 'checkbox/radio' | 'link';

interface TargetCategory {
  name: CategoryName;
  /** CSS selector, relative to the route's `<main role="main">`. */
  selector: string;
  /** How the box is obtained for one control. */
  measure: 'self' | 'label-row';
  /** Why this category is covered. */
  reason: string;
}

const TARGET_CATEGORIES: readonly TargetCategory[] = [
  {
    name: 'button',
    selector: `${MAIN} button:not([disabled]):not([aria-disabled="true"])`,
    measure: 'self',
    reason:
      'Buttons include the icon-only controls (copy, row delete, dialog close) and the ' +
      'ghost/disclosure variants; they are the app-wide pointer target.',
  },
  {
    name: 'checkbox/radio',
    selector:
      `${MAIN} input[type="checkbox"]:not([disabled]), ` +
      `${MAIN} input[type="radio"]:not([disabled])`,
    measure: 'label-row',
    reason:
      'ENT-G4=A: an 18px control may satisfy 2.5.8 when its label row is >=24px tall, so the ' +
      'label row is the target that gets measured.',
  },
  {
    name: 'link',
    selector: LINK_SELECTOR,
    measure: 'self',
    reason: 'Standalone links are pointer targets like buttons (inline-prose links are excepted).',
  },
];

interface RouteUnderTest {
  path: string;
  label: string;
  /**
   * Key used by `KNOWN_SUB_TARGET_ALLOWANCES` for parametrised paths
   * (`/requirements/<uuid>`); defaults to `path`.
   */
  allowanceKey?: string;
  /**
   * Minimum number of targets per category. A category that is present with
   * count 0 on a route where it is expected would make the sweep vacuous, so
   * the minimum is asserted, not assumed.
   */
  minCounts?: Partial<Record<CategoryName, number>>;
  /**
   * Create one throwaway artifact through this route's own quick-create dialog
   * before measuring, then come back to the list. Without it the route can
   * legitimately show `<EmptyState>` (the demo seed creates no artifacts) and
   * the row-level controls below would never be on the page.
   */
  seed?: 'requirement' | 'architectureElement';
  /**
   * Row-level controls that exist only when the list has at least one row.
   * Present AND measured, by test id — never assumed. These are the controls
   * issues #1394/#1395 measured by hand (row delete 22x22, IdChip copy 24x20)
   * plus the architecture tree's add-child/move buttons.
   */
  rowControls?: readonly RowControlProbe[];
}

/** A row-level control identified by a test-id prefix (the id is a UUID). */
interface RowControlProbe {
  /** Human label used in the failure output and the attached evidence. */
  name: string;
  /** CSS selector (test-id based; the artifact id is not known up front). */
  selector: string;
}

const ROUTES: readonly RouteUnderTest[] = [
  {
    path: '/settings',
    label: 'Workspace settings',
    minCounts: { button: 3, 'checkbox/radio': 1 },
  },
  {
    path: '/system-settings',
    label: 'System settings',
    minCounts: { button: 3, 'checkbox/radio': 1 },
  },
  {
    path: '/requirements',
    label: 'Requirements',
    minCounts: { button: 3 },
    seed: 'requirement',
    // #1395's two measured defects — present only once a row exists.
    rowControls: [
      {
        name: 'requirement row delete button (#1395: measured 22x22 before the fix)',
        selector: `${MAIN} [data-testid^="req-row-delete-"]`,
      },
      {
        name: 'requirement row IdChip copy button (#1395: measured 24x20 before the fix)',
        selector: `${MAIN} [data-testid^="req-row-"][data-testid$="-id-copy"]`,
      },
    ],
  },
  {
    path: '/architecture',
    label: 'Architecture',
    minCounts: { button: 3 },
    seed: 'architectureElement',
    // The tree's two per-row actions; both are icon-only buttons, i.e. exactly
    // the shape that shrinks below 24px when a floor is missing.
    rowControls: [
      {
        name: 'architecture tree row add-child button',
        selector: `${MAIN} [data-testid^="arch-tree-add-child-"]`,
      },
      {
        name: 'architecture tree row move (reparent) button',
        selector: `${MAIN} [data-testid^="arch-tree-move-"]`,
      },
    ],
  },
];

/**
 * Known targets that are still below 24x24 — the gate's explicit red baseline,
 * in the same spirit as `KNOWN_CONTRACT_GAPS` in the frontend ratchet and
 * `KNOWN_EXEMPT_RULES` in `a11y-smoke.spec.ts`.
 *
 * An entry is matched by (route, `data-testid`) and is bidirectional: the test
 * fails if the target stops being reported ("the allowance is stale, delete
 * it") as well as if an unlisted target drops below the floor. So the list
 * cannot quietly rot, and every entry must carry the measured box.
 *
 * EMPTY, BY DESIGN (see the header): the entries it held were real defects —
 * `mcp-personal-access-tokens-link` at 259 x 18 on `/settings` (the MCP section
 * rendered a bare inline `<Link>` with only font-size/colour styling) — and the
 * fix (an inline-flex/min-height `--space-6` floor) is what made the entry
 * stale, which turned this spec red until it was deleted. Keeping the empty
 * list is what keeps that loop armed for the next sub-target.
 */
interface KnownSubTargetAllowance {
  /** Route the target renders on (`path`, or `allowanceKey` for `:id` routes). */
  route: string;
  /** `data-testid` of the offending control. */
  testId: string;
  /** Measured box + classification + why it was opened. */
  reason: string;
}

const KNOWN_SUB_TARGET_ALLOWANCES: readonly KnownSubTargetAllowance[] = [];

/** One measured interactive target. */
interface TargetMeasurement {
  /** Human-identifiable label used in the failure output. */
  name: string;
  width: number;
  height: number;
}

/** One target that broke the floor, kept structured so it can be matched. */
interface SubTargetFailure {
  /** `data-testid` of the control, when it has one (allowance identity). */
  testId: string | null;
  /** Full, human-readable failure line (names test id / class / box). */
  violation: string;
}

/**
 * A row-level control that was actually rendered AND measured. Attached to the
 * test as evidence, so a green run proves the row existed instead of only
 * proving "nothing failed" on an empty list.
 */
interface MeasuredRowControl {
  route: string;
  name: string;
  width: number;
  height: number;
}

/** The gate: `null` when the box clears the floor, else a named failure line. */
function targetSizeViolation(
  measurement: TargetMeasurement,
  minimum: number = MIN_TARGET_PX
): string | null {
  if (measurement.width >= minimum && measurement.height >= minimum) return null;
  return (
    `${measurement.name}: ${formatPx(measurement.width)} x ${formatPx(measurement.height)} ` +
    `CSS px is below the ${minimum} x ${minimum} minimum`
  );
}

function formatPx(value: number): string {
  return Number(value.toFixed(1)).toString();
}

function truncate(value: string, limit = 40): string {
  return value.length > limit ? `${value.slice(0, limit - 1)}…` : value;
}

/**
 * Measure ONE target through Playwright's own layout API.
 *
 * Returns `null` for a control that is not rendered at all (collapsed panel,
 * `display:none` tab, `hidden` attribute): it is not a target, so it has no
 * target size. A rendered control always yields a box — a zero-sized box is a
 * real failure, not a skip.
 */
async function measureTarget(
  locator: Locator,
  name: string
): Promise<TargetMeasurement | null> {
  if ((await locator.count()) === 0) return null;
  if (!(await locator.first().isVisible())) return null;
  const box = await locator.first().boundingBox();
  if (box === null) return { name, width: 0, height: 0 };
  return { name, width: box.width, height: box.height };
}

/** The nearest `<label>` ancestor of a control, else its parent element. */
async function labelRowOf(control: Locator): Promise<Locator> {
  const label = control.locator('xpath=ancestor-or-self::label[1]');
  if ((await label.count()) > 0) return label;
  // Documented fallback: a `htmlFor`-style label is a sibling, so the row is
  // the control's parent element. Kept explicit so it is reviewable.
  return control.locator('xpath=..');
}

/** Identify a target by test id / aria-label / class / text. */
async function describeTarget(
  control: Locator,
  category: CategoryName,
  index: number,
  measuredRow: boolean
): Promise<{ testId: string | null; name: string }> {
  const parts: string[] = [`[${category} #${index}]`];

  const testId = await control.getAttribute('data-testid');
  if (testId) parts.push(`data-testid="${testId}"`);

  const ariaLabel = await control.getAttribute('aria-label');
  if (ariaLabel) parts.push(`aria-label="${truncate(ariaLabel)}"`);

  const classNames = (await control.getAttribute('class')) ?? '';
  const firstClasses = classNames.split(/\s+/).filter(Boolean).slice(0, 2).join(' ');
  if (firstClasses) parts.push(`class="${firstClasses}"`);

  const text = truncate(
    (await control.innerText().catch(() => '')).replace(/\s+/g, ' ').trim()
  );
  if (text) parts.push(`text="${text}"`);

  if (measuredRow) parts.push('(label row measured, not the raw input — ENT-G4=A)');

  return { testId, name: parts.join(' ') };
}

/**
 * Measure every target in a set and return one structured failure per
 * offending target. This is the single code path both the route sweeps and the
 * falsifiability self-checks exercise.
 */
async function collectViolations(
  targets: Locator,
  category: CategoryName,
  options: { measureLabelRow?: boolean } = {}
): Promise<SubTargetFailure[]> {
  const measureLabelRow = options.measureLabelRow === true;
  const count = await targets.count();
  const failures: SubTargetFailure[] = [];

  for (let index = 0; index < count; index += 1) {
    const control = targets.nth(index);
    const measured = measureLabelRow ? await labelRowOf(control) : control;
    const { testId, name } = await describeTarget(
      control,
      category,
      index,
      measureLabelRow
    );
    const measurement = await measureTarget(measured, name);
    if (measurement === null) continue;
    const violation = targetSizeViolation(measurement);
    if (violation !== null) failures.push({ testId, violation });
  }

  return failures;
}

/**
 * Wait for a route to finish its lazy-chunk + data settling (explicit state
 * waits, no fixed sleeps) — the same pattern as `a11y-smoke.spec.ts`, plus one
 * route-content wait: the lazy chunk can already be mounted while the route is
 * still showing its "Laden…" status, and measuring that state would report a
 * vacuous 0 targets (observed locally on /architecture).
 */
async function settle(page: Page): Promise<void> {
  await expect(page.locator('[data-testid="route-suspense-fallback"]')).toHaveCount(0, {
    timeout: 15000,
  });
  await expect(page.locator(MAIN)).toBeVisible({ timeout: 10000 });
  await expect
    .poll(() => page.locator(`${MAIN} button, ${MAIN} a[href], ${MAIN} input`).count(), {
      message: 'route finished loading: at least one interactive element is rendered in <main>',
      timeout: 15000,
    })
    .toBeGreaterThan(0);
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {
    // Some routes keep a long-poll connection open; the waits above are the gate.
  });
}

/**
 * Allowances that were NOT consumed by a reported violation. Those entries are
 * stale: their target now clears the floor, so the exemption must be deleted
 * (otherwise it would keep hiding the fixed target's siblings). Extracted as a
 * pure function so the bidirectionality is itself testable — with the live list
 * empty, "nothing was reported, nothing is stale" would otherwise pass without
 * ever exercising the mechanism.
 */
function staleAllowances(
  allowances: readonly KnownSubTargetAllowance[],
  usedTestIds: ReadonlySet<string>
): KnownSubTargetAllowance[] {
  return allowances.filter((allowance) => !usedTestIds.has(allowance.testId));
}

/**
 * A unique, retry-safe title for a throwaway artifact. `Date.now()` keeps two
 * runs (and a retry) apart; the run id keeps parallel workers apart.
 */
function throwawayTitle(label: string, testInfo: TestInfo): string {
  return `Target size gate ${label} ${Date.now()}-w${testInfo.workerIndex}-r${testInfo.retry}`;
}

/**
 * Create ONE requirement through the list's own quick-create dialog and return
 * to the list.
 *
 * The detail route proves the POST landed (the editor navigates to
 * `/requirements/<uuid>`); going back to the list is what puts the row — and
 * therefore the row-level copy/delete controls — on the page under test.
 *
 * Idempotent by design: on a workspace that already has rows the write is
 * skipped and the existing rows are measured. The gate is "a row is rendered
 * and measured", not "this run mutated the database", and re-running the suite
 * against a persistent CI database must not keep growing it.
 */
async function seedRequirementRow(page: Page, testInfo: TestInfo): Promise<void> {
  await page.goto(`${FRONTEND_URL}/requirements`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  if ((await page.locator(`${MAIN} [data-testid^="req-row-"]`).count()) > 0) return;

  await page.locator('[data-testid="create-req-btn"]').click();
  await page
    .locator('[data-testid="req-new-title-input"]')
    .fill(throwawayTitle('requirement', testInfo));
  await page.locator('[data-testid="req-new-save-btn"]').click();

  // The URL is the proof the artifact exists — the list is refetched after it.
  await expect(page).toHaveURL(/\/requirements\/[0-9a-fA-F-]{36}$/, { timeout: 15000 });
  await page.goto(`${FRONTEND_URL}/requirements`, { waitUntil: 'domcontentloaded' });
  await settle(page);
}

/**
 * The architecture analogue: `create-arch-btn` → `arch-new-title-input` →
 * `arch-new-save-btn`, then back to the list so the tree row is rendered.
 *
 * Same idempotence, and here it is load-bearing rather than tidy: the seeded
 * workspace runs the EXTENDED rigor preset, whose invariant I5 forbids a second
 * root. Creating unconditionally would therefore fail on any run after the
 * first ("an element with no parent already exists") — a retry (`retries: 2`)
 * would turn a pass into a red. When a tree row already exists it is measured
 * instead; the dialog path runs exactly when the route is in the empty state
 * that made this sweep vacuous in the first place.
 */
async function seedArchitectureRow(page: Page, testInfo: TestInfo): Promise<void> {
  await page.goto(`${FRONTEND_URL}/architecture`, { waitUntil: 'domcontentloaded' });
  await settle(page);
  if ((await page.locator(`${MAIN} [data-testid^="arch-tree-node-"]`).count()) > 0) return;

  await page.locator('[data-testid="create-arch-btn"]').click();
  await page
    .locator('[data-testid="arch-new-title-input"]')
    .fill(throwawayTitle('architecture element', testInfo));
  await page.locator('[data-testid="arch-new-save-btn"]').click();

  await expect(page).toHaveURL(/\/architecture\/[0-9a-fA-F-]{36}$/, { timeout: 15000 });
  await page.goto(`${FRONTEND_URL}/architecture`, { waitUntil: 'domcontentloaded' });
  await settle(page);
}

/**
 * Open a route with the content the sweep needs.
 *
 * `seed` is not a convenience: on `/requirements` and `/architecture` the demo
 * seed creates no artifacts, so the route renders `<EmptyState>` and a sweep
 * would measure empty-state chrome only — green and meaningless. One throwaway
 * artifact per route closes that hole; the row controls are then asserted to be
 * present before they are measured (see `expectRouteTargets`).
 */
async function openRouteWithContent(
  page: Page,
  route: RouteUnderTest,
  testInfo: TestInfo
): Promise<void> {
  if (route.seed === 'requirement') {
    await seedRequirementRow(page, testInfo);
    return;
  }
  if (route.seed === 'architectureElement') {
    await seedArchitectureRow(page, testInfo);
    return;
  }
  await page.goto(`${FRONTEND_URL}${route.path}`, { waitUntil: 'domcontentloaded' });
  await settle(page);
}

/**
 * Sweep every category on the current route and fail with the full list.
 *
 * Returns the row-level controls that were actually measured, so the caller can
 * attach them as evidence — a green run then says *which* boxes it saw, not
 * only that nothing failed.
 */
async function expectRouteTargets(
  page: Page,
  route: RouteUnderTest
): Promise<MeasuredRowControl[]> {
  const allowanceKey = route.allowanceKey ?? route.path;
  const applicableAllowances = KNOWN_SUB_TARGET_ALLOWANCES.filter(
    (allowance) => allowance.route === allowanceKey
  );
  const usedAllowances = new Set<string>();
  const failures: string[] = [];
  const measuredRowControls: MeasuredRowControl[] = [];

  // Row-level controls first: they are the controls this spec exists for, and
  // asserting their presence is what makes the sweep below non-vacuous on a
  // list route (an empty-state page has buttons too — just not these).
  for (const probe of route.rowControls ?? []) {
    await expect
      .poll(() => page.locator(probe.selector).count(), {
        message:
          `${route.path}: waiting for "${probe.name}" — the route rendered no list row, ` +
          'so the row-level target sweep would be vacuous',
        timeout: 15000,
      })
      .toBeGreaterThan(0);

    const control = page.locator(probe.selector).first();
    const measurement = await measureTarget(control, probe.name);
    if (measurement === null) {
      failures.push(`${probe.name}: matched a row control that is not visible/rendered`);
      continue;
    }
    measuredRowControls.push({
      route: route.path,
      name: probe.name,
      width: measurement.width,
      height: measurement.height,
    });
    const violation = targetSizeViolation(measurement);
    if (violation !== null) failures.push(violation);
  }

  for (const category of TARGET_CATEGORIES) {
    const targets = page.locator(category.selector);
    const minimum = route.minCounts?.[category.name] ?? 0;

    // Vacuity is asserted, not assumed: a category expected on this route must
    // actually be rendered before the sweep (also the explicit state wait for
    // data-driven routes — no sleeps).
    if (minimum > 0) {
      await expect
        .poll(() => targets.count(), {
          message:
            `${route.path}: waiting for at least ${minimum} ${category.name} target(s) — ` +
            `otherwise the ${category.name} sweep is vacuous`,
          timeout: 15000,
        })
        .toBeGreaterThanOrEqual(minimum);
    }

    const count = await targets.count();
    if (count === 0) continue;

    const found = await collectViolations(targets, category.name, {
      measureLabelRow: category.measure === 'label-row',
    });
    for (const failure of found) {
      const allowance = applicableAllowances.find(
        (candidate) => candidate.testId === failure.testId
      );
      if (allowance !== undefined) {
        usedAllowances.add(allowance.testId);
        continue;
      }
      failures.push(failure.violation);
    }
  }

  // Bidirectional: an allowance that is no longer needed is a stale entry and
  // must be deleted, otherwise it would keep hiding a fixed target's siblings.
  for (const stale of staleAllowances(applicableAllowances, usedAllowances)) {
    failures.push(
      `[allowance] data-testid="${stale.testId}" now meets the ${MIN_TARGET_PX}px floor ` +
        '— delete its entry from KNOWN_SUB_TARGET_ALLOWANCES'
    );
  }

  expect(
    failures,
    `SC 2.5.8 target-size regressions on ${route.path} (${route.label}):\n` +
      failures.map((line) => `  - ${line}`).join('\n')
  ).toEqual([]);

  return measuredRowControls;
}

test.describe('[REQ-056] WCAG 2.2 SC 2.5.8 target size, measured in the browser', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  for (const route of ROUTES) {
    test(`${route.path} interactive targets are >= 24x24 CSS px`, async (
      { page },
      testInfo
    ) => {
      await openRouteWithContent(page, route, testInfo);
      const measuredRowControls = await expectRouteTargets(page, route);

      // Evidence, not decoration: a green list-route run states which row
      // controls it actually saw and how big they were, so "no violation" can
      // never be confused with "nothing to measure". The `console.log` also
      // reaches the list reporter output, which is what a human reads.
      if (measuredRowControls.length > 0) {
        const summary = measuredRowControls
          .map(
            (control) =>
              `${control.route}: ${control.name} = ${formatPx(control.width)} x ${formatPx(
                control.height
              )} CSS px`
          )
          .join('\n');
        console.log(`[target-size] measured row-level controls:\n${summary}`);
        await testInfo.attach('measured-row-controls', {
          body: JSON.stringify(measuredRowControls, null, 2),
          contentType: 'application/json',
        });
      }
    });
  }

  /**
   * The detail route. No seeded artifact id helper exists, so the artifact (and
   * therefore the URL) is produced through the list's quick create form — the
   * same flow `a11y-smoke.spec.ts` uses for the ArtifactForm state. Only this
   * one throwaway requirement is created; the seeded data is not touched.
   */
  test('the requirement detail route interactive targets are >= 24x24 CSS px', async ({
    page,
  }, testInfo) => {
    await page.goto(`${FRONTEND_URL}/requirements`, { waitUntil: 'domcontentloaded' });
    await settle(page);

    await page.locator('[data-testid="create-req-btn"]').click();
    await page
      .locator('[data-testid="req-new-title-input"]')
      .fill(throwawayTitle('detail requirement', testInfo));
    await page.locator('[data-testid="req-new-save-btn"]').click();

    // The editor navigates to the created artifact's own route; waiting for the
    // URL is what proves the detail route (not the list) is under test.
    await expect(page).toHaveURL(/\/requirements\/[0-9a-fA-F-]{36}$/, { timeout: 15000 });
    await expect(page.locator('[data-testid="artifact-form"]')).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="artifact-field-title"]')).toBeVisible({
      timeout: 15000,
    });
    await settle(page);

    await expectRouteTargets(page, {
      path: new URL(page.url()).pathname,
      allowanceKey: '/requirements/:id',
      label: 'Requirement detail',
      minCounts: { button: 3 },
    });
  });
});

/**
 * Falsifiability of the gate itself. These run against synthetic DOM via
 * `page.setContent` (no app, no login, no seeded data) and go through the SAME
 * measurement and comparison functions as the route tests above.
 */
test.describe('target-size measurement is falsifiable', () => {
  test('applies every declared inline-prose exclusion to the link sweep', () => {
    // The exclusion list must reach the selector mechanically — a container
    // documented but not applied would be a silent filter of a different kind.
    expect(INLINE_PROSE_LINK_CONTEXTS.length).toBeGreaterThan(0);
    for (const context of INLINE_PROSE_LINK_CONTEXTS) {
      expect(LINK_SELECTOR).toContain(`:not(${context.container} a)`);
    }
    expect(LINK_SELECTOR.startsWith(`${MAIN} a[href]`)).toBe(true);
  });

  /**
   * The allowance mechanism itself is bidirectional, and that must not depend
   * on the live list being non-empty (it is empty now, which made the
   * reconciliation loop in `expectRouteTargets` a no-op). So the pure
   * `staleAllowances` function is exercised directly:
   *   - consumed allowance  → not stale (it was needed, it is still in place),
   *   - unconsumed allowance → stale (the target is fixed; the entry must go).
   * The live list being empty is asserted too, so a re-added exemption is a
   * deliberate, reviewable act rather than a silent re-hide.
   */
  test('treats a fixed target’s allowance as stale, and has no open allowance left', () => {
    const allowance: KnownSubTargetAllowance = {
      route: '/settings',
      testId: 'mcp-personal-access-tokens-link',
      reason: 'the entry this spec shipped with; now fixed and therefore deleted',
    };

    // Still reported below the floor → the allowance does its job, not stale.
    expect(staleAllowances([allowance], new Set([allowance.testId]))).toEqual([]);
    // No longer reported → nothing consumed it → stale → the gate must fail.
    expect(staleAllowances([allowance], new Set())).toEqual([allowance]);

    // …and the committed list carries no entry, i.e. nothing is silently hidden.
    expect(KNOWN_SUB_TARGET_ALLOWANCES).toEqual([]);
  });

  test('reports a sub-24px button by name and measured box', async ({ page }) => {
    await page.setContent(
      '<button class="tiny-target btn-sm" style="width:20px;height:20px">x</button>'
    );

    const violations = await collectViolations(page.locator('button.tiny-target'), 'button');

    expect(violations).toHaveLength(1);
    const [failure] = violations;
    // The fixture is synthetic DOM, so it carries no test id: identification
    // falls back to the class, exactly as it does for a real control that has
    // no test id — the offender line must still name it.
    expect(failure.testId).toBeNull();
    expect(failure.violation).toContain('class="tiny-target btn-sm"');
    expect(failure.violation).toContain('20 x 20');
    expect(failure.violation).toContain('below the 24 x 24 minimum');
  });

  test('accepts a button exactly on the 24x24 floor', async ({ page }) => {
    await page.setContent(
      '<button class="ok-target" ' +
        'style="width:24px;height:24px;box-sizing:border-box;border:0">x</button>'
    );

    const target = page.locator('button.ok-target');
    // Boundary value: the floor itself passes, and the box really is 24x24 —
    // otherwise "green" would only mean "the UA default is bigger than 24".
    const measurement = await measureTarget(target, 'floor target');
    expect(measurement).toMatchObject({ width: 24, height: 24 });
    expect(await collectViolations(target, 'button')).toEqual([]);
  });

  test('measures an 18px checkbox by its label row (ENT-G4=A)', async ({ page }) => {
    await page.setContent(
      '<label class="row" style="display:flex;align-items:center;height:28px">' +
        '<input type="checkbox" class="small-checkbox" style="width:18px;height:18px" />' +
        '<span>Banner aktiv</span>' +
        '</label>'
    );

    // The raw input is below the floor …
    const control = page.locator('input.small-checkbox');
    const controlMeasurement = await measureTarget(control, 'raw input');
    expect(controlMeasurement).not.toBeNull();
    expect(targetSizeViolation(controlMeasurement!)).not.toBeNull();

    // … and the shared offender path reports it, naming the fixture by class.
    const rawViolations = await collectViolations(control, 'checkbox/radio');
    expect(rawViolations).toHaveLength(1);
    expect(rawViolations[0].violation).toContain('class="small-checkbox"');
    expect(rawViolations[0].violation).toContain('18 x 18');

    // … but the row the user actually clicks satisfies it.
    const rowViolations = await collectViolations(control, 'checkbox/radio', {
      measureLabelRow: true,
    });
    expect(rowViolations).toEqual([]);
    // The row really was the measured element, not a lucky raw input.
    const row = await measureTarget(await labelRowOf(control), 'row');
    expect(row).not.toBeNull();
    expect(row!.height).toBe(28);
    expect(row!.height).toBeGreaterThan(controlMeasurement!.height);
  });
});
