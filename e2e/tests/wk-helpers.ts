// =============================================================================
// UI-Helper für Wasserkessel-SysEng-Szenario
// =============================================================================
// Stellt wiederverwendbare UI-Aktionen bereit. Jeder Helper macht eine
// konkrete UI-Interaktion und meldet, wenn die erwarteten UI-Elemente
// fehlen oder das Ergebnis leer ist (das ist Teil des Bug-Findings).
// =============================================================================

import type { Page, Locator } from '@playwright/test';
import { expect } from '@playwright/test';

export const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
export const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/**
 * Extrahiert eine UUID aus einem `data-testid` Attribut eines Locators.
 * Erwartet ein Attribut der Form `<prefix>-<uuid>`.
 */
async function extractIdFromTestid(locator: Locator, prefix: string): Promise<string> {
  await locator.waitFor({ timeout: 8000 });
  const testId = await locator.getAttribute('data-testid');
  if (!testId || !testId.startsWith(prefix)) {
    throw new Error(`expected data-testid starting with ${prefix}, got: ${testId}`);
  }
  return testId.slice(prefix.length);
}

/**
 * Erstellt eine Anforderung über die UI. Liefert die ID der neuen Anforderung
 * (aus der URL abgeleitet, in die der Editor nach Create navigiert).
 */
export async function createRequirementViaUI(
  page: Page,
  data: { title: string; description?: string; category?: string }
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/requirements`);
  await page.locator('[data-testid="create-req-btn"]').click();
  await page.locator('[data-testid="req-new-title-input"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="req-new-title-input"]').fill(data.title);
  await page.locator('[data-testid="req-new-save-btn"]').click();
  await page.waitForURL(/\/requirements\/[0-9a-f-]+/, { timeout: 12000 });

  const url = page.url();
  const match = url.match(/\/requirements\/([0-9a-f-]+)/);
  if (!match) throw new Error(`expected /requirements/:id URL, got: ${url}`);
  const id = match[1];

  // Optional: Description/Category im Detail-Editor ergänzen
  if (data.description) {
    await page.locator('[data-testid="req-title"]').waitFor({ timeout: 8000 });
    const descArea = page.locator('textarea').first();
    if (await descArea.count() > 0) {
      await descArea.fill(data.description);
      await saveRequirementDetail(page, 'E2E: set description');
    }
  }
  if (data.category) {
    // REQ_CATEGORIES option values are lowercase (frontend/src/types/index.ts) —
    // normalize so callers can pass human-readable category names.
    await page.locator('[data-testid="req-category"]').selectOption(data.category.toLowerCase());
    await saveRequirementDetail(page, 'E2E: set category');
  }
  return id;
}

/**
 * Speichert den Requirement-Detail-Editor und füllt vorher — falls gerendert —
 * die Change-Reason.
 *
 * Die WK-Szenarien setzen in Phase 0 das `extended`-Preset, dessen Policy jeden
 * PATCH ohne Begründung mit `400 change_reason required by workspace preset
 * policy` ablehnt. Ohne diesen Schritt lief der Save ins Leere: der Request
 * schlug fehl, `waitForLoadState('networkidle')` merkte davon nichts, und die
 * gerade gesetzte Kategorie bzw. Beschreibung war still verworfen.
 */
async function saveRequirementDetail(page: Page, reason: string): Promise<void> {
  const reasonInput = page.locator('[data-testid="change-reason-input"]');
  if (await reasonInput.isVisible({ timeout: 2000 }).catch(() => false)) {
    await reasonInput.fill(reason);
  }
  await page.locator('[data-testid="save-btn"]').click();
  await page.waitForLoadState('networkidle');
}

/**
 * Erstellt ein Architektur-Element über die UI.
 */
export async function createArchitectureElementViaUI(
  page: Page,
  data: { title: string; elementType: string; description?: string },
  parentId?: string
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/architecture`);
  if (parentId) {
    // [I5]: a workspace may have at most one root ArchitectureElement — every
    // element after the first must be attached under an existing one via the
    // tree's per-node "Add child" button (arch-tree uses WorkspaceTree,
    // testIdPrefix="arch-tree" — no context menu, plain button click).
    await page.locator(`[data-testid="arch-tree-add-child-${parentId}"]`).click();
  } else {
    await page.locator('[data-testid="create-arch-btn"]').click();
    // "+ New" only opens an inline quick-create form (title input + Save);
    // the full editor only renders after Save navigates to the detail route.
    await page.locator('[data-testid="arch-new-title-input"]').waitFor({ timeout: 8000 });
    await page.locator('[data-testid="arch-new-title-input"]').fill(data.title);
    await page.locator('[data-testid="arch-new-save-btn"]').click();
  }
  await page.waitForURL(/\/architecture\/[0-9a-f-]+/, { timeout: 12000 });

  const url = page.url();
  const match = url.match(/\/architecture\/([0-9a-f-]+)/);
  if (!match) throw new Error(`expected /architecture/:id URL, got: ${url}`);
  const id = match[1];

  await page.locator('[data-testid="arch-title"]').waitFor({ timeout: 8000 });
  if (parentId) {
    // "Add Child" creates the element with a default title — set the real one.
    await page.locator('[data-testid="arch-title"]').fill(data.title);
  }
  // REQ-006/D5: arch-element-type-select is a free-text autocomplete input,
  // not a <select>, since backend element types are workspace-defined.
  await page.locator('[data-testid="arch-element-type-select"]').fill(data.elementType);
  if (data.description) {
    const descArea = page.locator('textarea').first();
    if (await descArea.count() > 0) {
      await descArea.fill(data.description);
    }
  }
  await page.locator('[data-testid="arch-save-btn"]').click();
  await page.waitForLoadState('networkidle');
  return id;
}

/**
 * Erstellt einen TraceLink im Requirement-Editor.
 */
export async function createTraceLinkViaUI(
  page: Page,
  sourceReqId: string,
  targetReqId: string,
  linkType: string
): Promise<void> {
  await page.goto(`${FRONTEND_URL}/requirements/${sourceReqId}`);
  await page.locator('[data-testid="req-title"]').waitFor({ timeout: 12000 });
  const panel = page.locator('[data-testid="req-tracelink-panel"]');
  await expect(panel).toBeVisible({ timeout: 8000 });
  await page.locator('[data-testid="req-tracelink-create-btn"]').click();
  const targetSelect = page.locator('[data-testid="req-tracelink-target-select"]');
  await targetSelect.waitFor({ timeout: 10000 });
  // Wait until the dropdown has been populated with at least one real option.
  await targetSelect.locator('option[value]:not([value=""])').first().waitFor({ state: 'attached', timeout: 10000 });
  await targetSelect.selectOption(targetReqId);
  await page.locator('[data-testid="req-tracelink-type-select"]').selectOption(linkType);
  await page.locator('[data-testid="req-tracelink-submit-btn"]').click();
  await page.waitForLoadState('networkidle');
}

/**
 * Erstellt einen TraceLink aus dem Architecture-Editor heraus.
 */
export async function createArchTraceLinkViaUI(
  page: Page,
  sourceArchId: string,
  targetReqId: string,
  linkType: string
): Promise<void> {
  await page.goto(`${FRONTEND_URL}/architecture/${sourceArchId}`);
  await page.locator('[data-testid="arch-title"]').waitFor({ timeout: 12000 });
  const panel = page.locator('[data-testid="arch-linked-reqs-panel"]');
  await expect(panel).toBeVisible({ timeout: 8000 });
  // The architecture side uses the unified CreateTraceLinkDialog (REQ-005),
  // not an inline form. With a fixed sourceId (this element), the dialog has
  // no source-select — only a searchable target picker and link-type select.
  await page.locator('[data-testid="trace-link-panel-open-dialog"]').click();
  await page.locator('[data-testid="create-trace-link-dialog"]').waitFor({ timeout: 8000 });
  await page.locator(`[data-testid="create-trace-link-target-element-${targetReqId}"]`).waitFor({ timeout: 8000 });
  await page.locator(`[data-testid="create-trace-link-target-element-${targetReqId}"]`).click();
  await page.locator('[data-testid="create-trace-link-type-select"]').selectOption(linkType);
  await page.locator('[data-testid="create-trace-link-submit"]').click();
  await page.waitForLoadState('networkidle');
}

/**
 * Erstellt ein Diagramm über die UI.
 */
export async function createDiagramViaUI(
  page: Page,
  data: {
    name: string;
    diagramType: 'block' | 'flow' | 'context';
    payloadFormat: 'mermaid' | 'plantuml' | 'json';
    content: string;
    description?: string;
  }
): Promise<void> {
  await page.goto(`${FRONTEND_URL}/diagrams`);
  await page.locator('[data-testid="create-diagram-btn"]').click();
  await page.locator('[data-testid="diagram-name-input"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="diagram-name-input"]').fill(data.name);
  await page.locator('[data-testid="diagram-type-select"]').selectOption(data.diagramType);
  await page.locator('[data-testid="diagram-format-select"]').selectOption(data.payloadFormat);
  await page.locator('[data-testid="diagram-source-textarea"]').fill(data.content);
  if (data.description) {
    await page.locator('[data-testid="diagram-description-input"]').fill(data.description);
  }
  await page.locator('[data-testid="diagram-save-btn"]').click();
  await page.waitForLoadState('networkidle');
}

/**
 * Erstellt ein ICD über die UI.
 */
export async function createIcdViaUI(
  page: Page,
  data: {
    name: string;
    sourceArchId: string;
    targetArchId: string;
    interfaceType: string;
    contract: string;
    direction?: 'unidirectional' | 'bidirectional';
  }
): Promise<void> {
  await page.goto(`${FRONTEND_URL}/icds`);
  await page.locator('[data-testid="create-icd-btn"]').click();
  await page.locator('[data-testid="icd-name-input"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="icd-name-input"]').fill(data.name);
  await page.locator('[data-testid="icd-source-select"]').selectOption(data.sourceArchId);
  await page.locator('[data-testid="icd-target-select"]').selectOption(data.targetArchId);
  if (data.direction) {
    await page.locator('[data-testid="icd-direction-select"]').selectOption(data.direction);
  }
  // icd-interface-type-select is a fixed-enum <select> (provides/requires/
  // event-in/event-out/data/control), not free text.
  await page.locator('[data-testid="icd-interface-type-select"]').selectOption(data.interfaceType);
  await page.locator('[data-testid="icd-contract-textarea"]').fill(data.contract);
  await page.locator('[data-testid="create-icd-submit"]').click();
  await page.waitForLoadState('networkidle');
}

/**
 * Setzt das Workspace-Preset über die UI.
 */
export async function setWorkspacePresetViaUI(
  page: Page,
  preset: 'minimal' | 'standard' | 'extended'
): Promise<void> {
  await page.goto(`${FRONTEND_URL}/workspace-settings`);
  await page.locator('[data-testid="preset-selector"]').waitFor({ timeout: 10000 });
  await page.locator(`[data-testid="preset-option-${preset}"]`).click();
  await page.waitForLoadState('networkidle');
}

/**
 * Sucht nach Text in der globalen Suche und klickt auf das erste Resultat.
 */
export async function globalSearchAndClick(
  page: Page,
  query: string
): Promise<number> {
  await page.goto(`${FRONTEND_URL}/`);
  await page.locator('[data-testid="global-search"]').click();
  // fill() triggers the 300ms-debounced handleSearchChange
  // (SidebarNavigation.tsx), which then GETs /search/. Wait for that
  // response instead of a fixed delay so the result count below reflects
  // the actually-loaded results.
  const responsePromise = page.waitForResponse(
    (resp) => resp.url().includes('/search/') && resp.request().method() === 'GET'
  );
  await page.locator('[data-testid="global-search"]').fill(query);
  await responsePromise;
  const results = page.locator('[data-testid="global-search-result"]');
  return await results.count();
}

// ---------------------------------------------------------------------------
// Neue UI-Helper für Issues, Risks, ADRs, TestCases, TestRuns, Baselines
// ---------------------------------------------------------------------------

/**
 * Erstellt ein Issue über die UI und liefert die neue ID zurück.
 */
export async function createIssueViaUI(
  page: Page,
  data: { title: string; description?: string; severity?: string; status?: string }
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/issues`);
  await page.locator('[data-testid="create-issue-btn"]').click();
  // "+ New" only opens an inline quick-create form (title input + Save);
  // the full editor navigates to /issues/:id afterwards. The detail form's
  // description/severity/status fields have no data-testid, so they can't
  // be set here without further UI-testability changes.
  await page.locator('[data-testid="issue-new-title-input"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="issue-new-title-input"]').fill(data.title);
  await page.locator('[data-testid="issue-new-save-btn"]').click();
  await page.waitForURL(/\/issues\/[0-9a-f-]+/, { timeout: 12000 });

  const url = page.url();
  const match = url.match(/\/issues\/([0-9a-f-]+)/);
  if (!match) throw new Error(`expected /issues/:id URL, got: ${url}`);
  return match[1];
}

/**
 * Erstellt ein Risk über die UI und liefert die neue ID zurück.
 */
export async function createRiskViaUI(
  page: Page,
  data: { title: string; description?: string; severity?: string; probability?: string; impact?: string }
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/risks`);
  await page.locator('[data-testid="create-risk-btn"]').click();
  // Same inline quick-create-form pattern as Issues; detail-view
  // description/severity/probability/impact fields have no data-testid.
  await page.locator('[data-testid="risk-new-title-input"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="risk-new-title-input"]').fill(data.title);
  await page.locator('[data-testid="risk-new-save-btn"]').click();
  await page.waitForURL(/\/risks\/[0-9a-f-]+/, { timeout: 12000 });

  const url = page.url();
  const match = url.match(/\/risks\/([0-9a-f-]+)/);
  if (!match) throw new Error(`expected /risks/:id URL, got: ${url}`);
  return match[1];
}

/**
 * Erstellt einen ADR über die UI und liefert die neue ID zurück.
 */
export async function createAdrViaUI(
  page: Page,
  data: { title: string; context?: string; decision?: string; status?: string }
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/adrs`);
  await page.locator('[data-testid="create-adr-btn"]').click();
  // Same inline quick-create-form pattern as Issues/Risks; detail-view
  // context/decision/status fields have no data-testid.
  await page.locator('[data-testid="adr-new-title-input"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="adr-new-title-input"]').fill(data.title);
  await page.locator('[data-testid="adr-new-save-btn"]').click();
  await page.waitForURL(/\/adrs\/[0-9a-f-]+/, { timeout: 12000 });

  const url = page.url();
  const match = url.match(/\/adrs\/([0-9a-f-]+)/);
  if (!match) throw new Error(`expected /adrs/:id URL, got: ${url}`);
  return match[1];
}

/**
 * Erstellt einen TestCase über die UI und liefert die neue ID zurück.
 */
export async function createTestCaseViaUI(
  page: Page,
  data: { title: string; description?: string; status?: string; priority?: string }
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/testcases`);
  await page.locator('[data-testid="create-tc-btn"]').click();
  // Same inline quick-create-form pattern as Issues/Risks/ADRs; detail-view
  // description/status/priority fields have no data-testid.
  await page.locator('[data-testid="tc-new-title-input"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="tc-new-title-input"]').fill(data.title);
  await page.locator('[data-testid="tc-new-save-btn"]').click();
  await page.waitForURL(/\/testcases\/[0-9a-f-]+/, { timeout: 12000 });

  const url = page.url();
  const match = url.match(/\/testcases\/([0-9a-f-]+)/);
  if (!match) throw new Error(`expected /testcases/:id URL, got: ${url}`);
  return match[1];
}

/**
 * Erstellt einen TestRun über die UI und liefert die neue ID zurück.
 */
export async function createTestRunViaUI(
  page: Page,
  data: { name: string; status?: string }
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/test-runs`);
  await page.locator('[data-testid="testrun-create-btn"]').click();
  await page.locator('[data-testid="testrun-create-form"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="testrun-name-input"]').fill(data.name);
  // No status select exists in the create form (TestRunsList.tsx) — a new
  // TestRun is always created server-side with status='in_progress'; use
  // transitionTestRunViaUI afterwards to reach closed/failed.
  await page.locator('[data-testid="testrun-create-submit-btn"]').click();
  // Suche das gerade erstellte Item anhand des Namens (robust gegen alte Runs)
  const item = page.locator('[data-testid^="testrun-item-"]').filter({ hasText: data.name }).first();
  await item.waitFor({ timeout: 8000 });
  return extractIdFromTestid(item, 'testrun-item-');
}

/**
 * Schließt einen TestRun über die UI.
 */
export async function transitionTestRunViaUI(
  page: Page,
  runId: string,
  _fromStatus: string,
  toStatus: string
): Promise<void> {
  await page.goto(`${FRONTEND_URL}/test-runs`);
  const item = page.locator(`[data-testid="testrun-item-${runId}"]`);
  await item.waitFor({ timeout: 8000 });
  await item.click();
  await page.locator('[data-testid="testrun-close-btn"]').waitFor({ timeout: 8000 });
  if (toStatus === 'closed' || toStatus === 'failed' || toStatus === 'passed' || toStatus === 'partial') {
    // Two-step inline confirmation replaced the window.confirm dialog.
    await page.locator('[data-testid="testrun-close-btn"]').click();
    await page.locator('[data-testid="testrun-confirm-close-btn"]').click();
    await expect(page.locator('[data-testid="testrun-close-btn"]')).toHaveCount(0, { timeout: 8000 });
  }
  await page.waitForLoadState('networkidle');
}

/**
 * Creates a baseline via the UI.
 *
 * BUG-03 (SYSTEMAUDIT_2026-08-18 §4): in a realistic, partially-incomplete SE
 * graph (which this bug-finding scenario deliberately builds up in stages),
 * the SE-Auditor gate (GH-490/GH-513) rejects a `project`-scope baseline
 * create with HTTP 400 `SE_AUDITOR_BLOCKED` as soon as individual
 * requirements are still missing `derives-from`/`verifies`/`allocated-to`
 * links — exactly the state this scenario is in between phases. That is
 * intended governance behaviour (BaselinesView shows a waiver panel with a
 * justification field for it), but this helper used to check success via
 * the wrong selector (`tbody tr` — the list is a `<ul><li>`, not a table)
 * and swallowed every failure in a `.catch(() => null)`. A blocked create
 * therefore looked identical to a successful one — the list stayed empty
 * without the test noticing (the real assertion in the calling test file
 * then failed separately, later, with no apparent connection).
 *
 * Fix: after submit, explicitly check for the waiver panel and fail loudly
 * (instead of swallowing) if neither the form closes nor the baseline shows
 * up. The waiver itself is opt-in (`allowGateOverride`) — silently waiving
 * a governance gate on every call would make it impossible to tell "gate
 * passed cleanly" from "gate blocked and we clicked through it" (review
 * finding F-4). Callers that expect a clean pass (no BLOCKER findings) get
 * a hard failure with the blocked rule ids instead; callers that
 * deliberately accept a WIP snapshot must opt in and get the waived rule
 * ids logged so the override is visible in the test log, not silently
 * absorbed.
 */
export async function createBaselineViaUI(
  page: Page,
  data: {
    scope: 'project' | 'document' | 'global';
    artifactId?: string;
    /**
     * Opt-in: if the SE-Auditor gate blocks the plain create, fill in the
     * waiver justification and resubmit (the documented GH-513 admin
     * override path) instead of failing. Defaults to false so a blocked
     * gate is a loud test failure by default, not a silent waiver.
     */
    allowGateOverride?: boolean;
  }
): Promise<void> {
  await page.goto(`${FRONTEND_URL}/baselines`);
  await page.waitForLoadState('networkidle');
  // Task 5.2: baseline creation is an overflow action, not a primary header
  // button — open the "..." menu first.
  await page.locator('[data-testid="page-header-overflow-trigger"]').click();
  await page.locator('[data-testid="create-baseline-btn"]').click();
  await page.locator('[data-testid="create-baseline-form"]').waitFor({ timeout: 8000 });
  await page.locator(`[data-testid="baseline-scope-${data.scope}"]`).check();
  if (data.scope === 'document' && data.artifactId) {
    await page.locator('[data-testid="baseline-artifact-select"]').selectOption(data.artifactId);
  }
  const submit = page.locator('[data-testid="baseline-submit-btn"]');
  await expect(submit).toBeEnabled({ timeout: 5000 });
  await submit.click();
  await page.waitForLoadState('networkidle');

  // The SE-Auditor gate may have rejected the plain create.
  //
  // `.isVisible()` alone does not poll/wait — it is a single, immediate DOM
  // check — so a plain `if (await panel.isVisible())` can race the React
  // re-render that follows the create response (networkidle only tracks
  // in-flight network requests, not render completion). `.waitFor()` is
  // Playwright's polling primitive; a `false` result here means the panel
  // genuinely never appeared within the window, not that the check ran too
  // early.
  const form = page.locator('[data-testid="create-baseline-form"]');
  const overridePanel = form.locator('[data-testid="baseline-override-panel"]');
  const overrideAppeared = await overridePanel
    .waitFor({ state: 'visible', timeout: 4000 })
    .then(() => true)
    .catch(() => false);

  if (overrideAppeared) {
    // The blocked-findings message (BaselinesView.tsx renders it as
    // role="alert" inside the create form) names every rule id that
    // tripped the gate — surface it in the test log either way, so a
    // blocked gate is never silent, whether or not we're allowed to waive it.
    const blockedMessage = await form.locator('[role="alert"]').first().innerText().catch(() => '(message unavailable)');

    if (!data.allowGateOverride) {
      throw new Error(
        `createBaselineViaUI: SE-Auditor gate blocked the create and allowGateOverride was not set. ` +
          `Blocked findings: ${blockedMessage}`
      );
    }

    // eslint-disable-next-line no-console
    console.log(`[createBaselineViaUI] SE-Auditor gate blocked (waiving via allowGateOverride): ${blockedMessage}`);

    await page
      .locator('[data-testid="baseline-override-reason"]')
      .fill('Bug-finding scenario snapshot; upstream links land in a later phase.');
    const overrideSubmit = page.locator('[data-testid="baseline-override-submit-btn"]');
    await expect(overrideSubmit).toBeEnabled({ timeout: 5000 });
    await overrideSubmit.click();
    await page.waitForLoadState('networkidle');
  }

  // Success indicator: the create form closes (BaselinesView.tsx only calls
  // setShowForm(false) on a successful create — the SE-Auditor-blocked path
  // keeps the form open with createError/gateBlocked set). Fail loudly
  // instead of silently continuing, so a genuine regression surfaces here
  // rather than as an unrelated, delayed assertion failure in the caller.
  await expect(form).toBeHidden({ timeout: 8000 });
}
