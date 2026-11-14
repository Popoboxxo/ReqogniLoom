// =============================================================================
// Artifact inspector helpers (issue #1762, slice M1)
// =============================================================================
//
// The requirements route mounts the tabbed `InspectorShell` instead of the old
// stacked `RightSidebar` (commit 85ceecad, spec
// docs/superpowers/specs/2026-11-10-inspector-redesign-design.md §2.1/§4.2).
// Two consequences matter for every spec that drives the requirement detail
// form:
//
//  1. **The inspector opens as a sheet at the E2E viewport.** Breakpoint table
//     (§4.2): 1024–1439 px = R3, and R3 starts *open* from 1280 px. Playwright's
//     "Desktop Chrome" default is exactly 1280×720, so a freshly opened
//     requirement shows the sheet over the detail area.
//  2. **The covered detail area is `inert`** (§4.2, WCAG 2.2 SC 2.4.11). Inert
//     is not a visual state: `locator.click()` fails with "… intercepts pointer
//     events" and, far worse, `locator.fill()` silently does nothing — the
//     input keeps its old value and the test only fails much later, somewhere
//     else. That silent-fill failure mode is why `collapseInspector()` asserts
//     the bracket is gone instead of trusting the click that removed it.
//
// The specs that use this helper therefore do what a 1280 px user has to do:
// close the sheet (its header close button) before typing into the form, and
// open the inspector again from its rail when a tab is what the test is about.
//
// All locators come from the shell's own contract
// (`frontend/src/components/shared/ArtifactInspector/inspectorContract.ts`,
// §8.4): the testids and the `data-inspector-form` values are the public
// surface, so no spec has to know a CSS module class name.
// =============================================================================

import { expect, type Page } from '@playwright/test';

/** Tab keys of the shell, in rendered order (inspectorContract §2.1). */
export type InspectorTab = 'version' | 'diff' | 'links' | 'comments';

/** `data-testid` inventory of the shell (inspectorContract.INSPECTOR_TEST_IDS). */
export const INSPECTOR_TEST_IDS = {
  /** The `<aside>` that is rail, panel, sheet or full-screen — one node. */
  shell: 'inspector-shell',
  close: 'inspector-close',
  tabs: 'inspector-tabs',
  rail: 'inspector-rail',
  /** Rail button that expands the inspector (on the active tab). */
  railOpen: 'inspector-rail-open',
  /** Rail counter button — expands the inspector *on that tab*. */
  railCount: (tab: InspectorTab): string => `inspector-rail-count-${tab}`,
  tab: (tab: InspectorTab): string => `inspector-tab-${tab}`,
  panel: (tab: InspectorTab): string => `inspector-panel-${tab}`,
} as const;

/** Rendered forms of the shell (inspectorContract.InspectorForm). */
type InspectorForm = 'panel' | 'rail' | 'sheet' | 'fullscreen';

/** Forms that overlay the detail area and therefore make it `inert`. */
const OVERLAY_FORMS: readonly InspectorForm[] = ['sheet', 'fullscreen'];

/**
 * Collapse the inspector to its rail so the requirement detail form is
 * operable again.
 *
 * Call this after a requirement detail has loaded and before any interaction
 * with the form (fill/click/select). It is idempotent: on a wide viewport
 * (R1/R2, form `panel`) and on an already collapsed inspector it does nothing.
 *
 * The final assertions are the actual contract check, not decoration:
 *  - `data-inspector-form="rail"` proves the sheet is gone,
 *  - no `[inert]` element is left inside the requirements page, which is what
 *    makes `fill()` silently no-op if it regresses.
 */
export async function collapseInspector(page: Page): Promise<void> {
  const shell = page.getByTestId(INSPECTOR_TEST_IDS.shell);

  // The shell is mounted by the route as soon as a requirement is selected
  // (`{currentVersion && <InspectorShell …>}`), i.e. in the same commit as the
  // detail form every caller has already waited for.
  await expect(shell).toBeAttached({ timeout: 15000 });
  await expect(shell).toHaveAttribute(
    'data-inspector-form',
    /^(panel|rail|sheet|fullscreen)$/
  );

  const form = (await shell.getAttribute('data-inspector-form')) as InspectorForm;
  if (!OVERLAY_FORMS.includes(form)) return;

  await page.getByTestId(INSPECTOR_TEST_IDS.close).click();
  await expect(shell).toHaveAttribute('data-inspector-form', 'rail');
  await expect(
    page.locator('[data-testid="requirements-page"] [inert]'),
    'the closed inspector must not leave the detail area inert — a fill() on an inert input silently does nothing'
  ).toHaveCount(0);
}

/**
 * Open the inspector and activate `tab`.
 *
 * Works from both states: from the rail it presses the tab's counter button
 * (which is how a collapsed inspector is opened "on that tab", §3), from
 * panel/sheet it activates the tab in the tablist. Manual activation (§5.2)
 * means a click on the tab is the activation — no extra keyboard step.
 */
export async function openInspectorTab(page: Page, tab: InspectorTab): Promise<void> {
  const shell = page.getByTestId(INSPECTOR_TEST_IDS.shell);
  await expect(shell).toBeAttached({ timeout: 15000 });
  await expect(shell).toHaveAttribute(
    'data-inspector-form',
    /^(panel|rail|sheet|fullscreen)$/
  );

  if ((await shell.getAttribute('data-inspector-form')) === 'rail') {
    await page.getByTestId(INSPECTOR_TEST_IDS.railCount(tab)).click();
    await expect(shell).toHaveAttribute('data-inspector-form', /^(sheet|panel|fullscreen)$/);
  }

  await page.getByTestId(INSPECTOR_TEST_IDS.tab(tab)).click();
  await expect(page.getByTestId(INSPECTOR_TEST_IDS.tab(tab))).toHaveAttribute(
    'aria-selected',
    'true'
  );
  await expect(page.getByTestId(INSPECTOR_TEST_IDS.panel(tab))).toBeVisible();
}
