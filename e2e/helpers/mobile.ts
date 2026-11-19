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

// ---------------------------------------------------------------------------
// Task 11 (Schnitt 4b) — mobile sheet contract (plan §3.5).
//
// On a phone the trace footer and the artifact inspector are two overlays over
// the same detail area. Both preferences may be on, but the contract is:
//   1. exactly ONE sheet is expanded at a time (opening one collapses the other)
//   2. the open sheet has ONE visible dismissal control (its own close)
//   3. focus lives inside the opened sheet and returns to its trigger on close
//   4. every interactive control in an open sheet has a >=44px tap target
//
// ACCESSIBLE SEMANTICS (resolved against plan §3.5 and #1762 / spec §4.2 D3/B1):
// the plan's "aria-modal only on the open sheet" was written for two *modal*
// sheets. The artifact inspector is deliberately NON-modal — `role="region"`,
// no scrim / focus trap, covered area `inert` — and the trace footer bottom
// sheet uses the same honest region semantics. So neither carries aria-modal;
// `aria-modal="true"` belongs ONLY to the genuinely modal ImpactDrawer, which
// portals a scrim and traps focus. The assertion below checks that contract
// instead of demanding aria-modal on a surface that correctly is not a dialog
// (asserting region+inert is stronger than asserting a role the source rejects).
//
// These helpers read the accessibility tree / rendered boxes, not CSS module
// class names. They deliberately fail loudly (no silent "0 sheets => pass"
// branch) so a missing implementation cannot produce a false green.
// ---------------------------------------------------------------------------

/** Stable public testids of the two mobile sheets and their controls. */
export const SHEET_TEST_IDS = {
  /** TraceSpineFooter (collapsed bar / expanded bottom sheet). */
  footer: 'trace-footer',
  footerExpand: 'trace-footer-expand',
  footerMore: 'trace-footer-more',
  footerCollapse: 'trace-footer-collapse',
  /** ArtifactInspector sheet (overlay form of the shell). */
  inspector: 'inspector-shell',
  inspectorClose: 'inspector-close',
  inspectorRailOpen: 'inspector-rail-open',
  /** On-demand impact drawer (/traceability). */
  impactDrawer: 'impact-drawer',
  impactOpen: 'impact-open-btn',
  impactClose: 'impact-drawer-close',
  /** Single mobile back control (SplitView). */
  back: 'splitview-back',
} as const;

/** WCAG 2.5.5 / mobile platform touch target, in CSS px (plan §3.5). */
export const TOUCH_TARGET_MIN_PX = 44;

interface SheetSnapshot {
  testid: string;
  /** True when the sheet currently overlays the detail area. */
  open: boolean;
  /** Value of `aria-modal`, or null when absent. */
  ariaModal: string | null;
  /** Explicit ARIA role, or null when absent. */
  role: string | null;
}

/**
 * Read the current state of every sheet on the page from the DOM.
 *
 * "Open" is deliberately derived from observable state, not a source helper:
 *  - inspector: `data-inspector-form` is `sheet` / `fullscreen` when expanded;
 *  - footer: `[aria-expanded="true"]` on its bar expander, or a rendered
 *    close control (only present when expanded);
 *  - impact drawer: it is portalled into `document.body` only while open.
 */
export async function readSheetStates(page: Page): Promise<SheetSnapshot[]> {
  return page.evaluate((ids) => {
    const snap = (testid: string, open: boolean): SheetSnapshot => {
      const el = document.querySelector<HTMLElement>(`[data-testid="${testid}"]`);
      // The inspector inherits no `role` on its <aside> root: the named
      // region is its inner surface. Accept either so both sheets read the
      // same honest way from the accessibility tree.
      const role =
        el?.getAttribute('role') ?? (el?.querySelector('[role="region"]') ? 'region' : null);
      return {
        testid,
        open: !!el && open,
        ariaModal: el?.getAttribute('aria-modal') ?? null,
        role,
      };
    };
    const footerEl = document.querySelector<HTMLElement>(`[data-testid="${ids.footer}"]`);
    const inspector = document.querySelector<HTMLElement>(`[data-testid="${ids.inspector}"]`);
    const inspectorForm = inspector?.getAttribute('data-inspector-form');
    const footerExpanded =
      document.querySelector<HTMLElement>(`[data-testid="${ids.footerExpand}"][aria-expanded="true"]`) !== null ||
      document.querySelector<HTMLElement>(`[data-testid="${ids.footerCollapse}"]`) !== null ||
      document.querySelector<HTMLElement>(`[data-testid="${ids.footer}"] [aria-expanded="true"]`) !== null;
    return [
      {
        testid: ids.footer,
        open: footerExpanded,
        ariaModal: footerEl?.getAttribute('aria-modal') ?? null,
        role: footerEl?.getAttribute('role') ?? null,
      },
      snap(ids.inspector, inspectorForm === 'sheet' || inspectorForm === 'fullscreen' || inspectorForm === 'overlay'),
      snap(ids.impactDrawer, true),
    ].filter((s) => {
      // A sheet that is not in the DOM is not open. snap() returns open=true
      // for the drawer because its presence IS the open signal; drop it when
      // absent. The footer/inspector elements are always mounted (rail form),
      // so their own `open` flag decides.
      if (s.testid === ids.impactDrawer) {
        return document.querySelector(`[data-testid="${ids.impactDrawer}"]`) !== null;
      }
      return s.open || document.querySelector(`[data-testid="${s.testid}"]`) !== null;
    });
  }, SHEET_TEST_IDS);
}

/**
 * Assert the resolved §3.5 contract: at most one expanded sheet, honest ARIA.
 *
 * A modal surface (the ImpactDrawer) must carry `aria-modal="true"` and be the
 * only open sheet. The two NON-modal mobile sheets (inspector, trace footer)
 * must declare `role="region"` and must NOT claim `aria-modal` — the covered
 * area is made `inert` instead (checked by `expectNonModalSheet`). No closed
 * sheet may ever claim `aria-modal`.
 */
export async function expectAtMostOneExpandedSheet(page: Page): Promise<void> {
  const all = await readSheetStates(page);
  const sheets = all.filter((s) => s.open);
  expect(
    sheets.length,
    `expected at most one expanded sheet, found: ${sheets.map((s) => s.testid).join(', ') || '(none)'}`
  ).toBeLessThanOrEqual(1);
  for (const sheet of sheets) {
    if (sheet.ariaModal === 'true') {
      expect(sheet.testid, 'a modal sheet must be the sole open sheet').toBe(SHEET_TEST_IDS.impactDrawer);
      expect(sheets.length).toBe(1);
    } else {
      expect(sheet.role, `${sheet.testid} is a non-modal sheet and must declare role="region"`).toBe('region');
    }
  }
  expect(
    all.filter((s) => !s.open && s.ariaModal === 'true').map((s) => s.testid),
    'aria-modal must only be set on the open sheet'
  ).toEqual([]);
}

/**
 * Assert a NON-modal mobile sheet's contract: `role="region"`, no `aria-modal`,
 * and the covered detail area made `inert` (WCAG 2.2 SC 2.4.11) — the honest
 * counterpart to the plan's modal-only wording, kept for #1762.
 */
export async function expectNonModalSheet(page: Page, sheetTestId: string): Promise<void> {
  const sheet = page.locator(`[data-testid="${sheetTestId}"]`).first();
  await expect(sheet, `${sheetTestId} must be visible to inspect its role`).toBeVisible();

  const role = await sheet.getAttribute('role');
  const hasInnerRegion = (await sheet.locator('[role="region"]').count()) > 0;
  expect(role === 'region' || hasInnerRegion, `${sheetTestId} must declare a named region`).toBe(true);
  expect(role, `${sheetTestId} is non-modal — never a dialog`).not.toBe('dialog');
  await expect(sheet, `${sheetTestId} is non-modal — must not claim aria-modal`).not.toHaveAttribute('aria-modal');

  // WCAG 2.2 SC 2.4.11: both non-modal sheets cover a host-owned detail area
  // and must mark it inert while open. The inspector's R5 `fullscreen` form is
  // the sole exception — it REPLACES the detail area, so nothing is behind it.
  const form = await sheet.getAttribute('data-inspector-form');
  const isFullscreen = form === 'fullscreen';
  if (!isFullscreen) {
    // Scope to the COVERED DETAIL subtree, not all [inert] nodes: the closed
    // mobile sidebar is legitimately inert (SidebarNavigation.tsx) and would
    // make a page-wide count vacuously true. The inspector marks an inner
    // detailScroll div inert; the footer marks splitview-detail itself. Check
    // self OR descendant so both correct brackets are accepted.
    const detailCovered = await page.getByTestId('splitview-detail').evaluate(
      (el) => !!el.closest('[inert]') || !!el.querySelector('[inert]'),
    );
    expect(
      detailCovered,
      `${sheetTestId} open over covered detail: area must be inert (SC 2.4.11)`,
    ).toBe(true);
  }
}

/** Measure an interactive control's rendered box against the >=44px touch floor. */
export async function expectTouchTarget(page: Page, selector: string, label: string): Promise<void> {
  const locator = page.locator(selector).first();
  await expect(locator, `${label} must be visible to have a measurable tap target`).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, `${label} has no rendered box`).not.toBeNull();
  expect(box!.width, `${label} width ${box!.width}px < ${TOUCH_TARGET_MIN_PX}px`).toBeGreaterThanOrEqual(
    TOUCH_TARGET_MIN_PX
  );
  expect(box!.height, `${label} height ${box!.height}px < ${TOUCH_TARGET_MIN_PX}px`).toBeGreaterThanOrEqual(
    TOUCH_TARGET_MIN_PX
  );
}

/** Assert focus is inside the named sheet (accessibility-tree owner of §3.5). */
export async function expectFocusWithinSheet(page: Page, sheetTestId: string): Promise<void> {
  const focus = await page.evaluate((id) => {
    const active = document.activeElement as HTMLElement | null;
    return {
      inside: !!active?.closest(`[data-testid="${id}"]`),
      testid: active?.getAttribute('data-testid') ?? null,
    };
  }, sheetTestId);
  expect(focus.inside, `focus must live inside ${sheetTestId}; active element = ${focus.testid ?? '(none)'}`).toBe(
    true
  );
}

/** Escape closes the topmost non-modal sheet (the open surface). */
export async function closeTopmostSheet(page: Page): Promise<void> {
  await page.keyboard.press('Escape');
  await expect.poll(async () => (await readSheetStates(page)).filter((s) => s.open).length).toBeLessThanOrEqual(1);
}

/** Reflow: 1280px design width at 400% ≈ 320 CSS px (WCAG 1.4.10). */
export async function expectNoOverflowAt400Zoom(page: Page): Promise<void> {
  await page.setViewportSize({ width: 320, height: 720 });
  await expectNoHorizontalDocumentScroll(page);
  await page.setViewportSize({ width: 1280, height: 720 });
}
