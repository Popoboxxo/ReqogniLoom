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
      await page.locator('[data-testid="save-btn"]').click();
      await page.waitForLoadState('networkidle');
    }
  }
  if (data.category) {
    await page.locator('[data-testid="req-category"]').selectOption(data.category).catch(() => null);
    await page.locator('[data-testid="save-btn"]').click();
    await page.waitForLoadState('networkidle');
  }
  return id;
}

/**
 * Erstellt ein Architektur-Element über die UI.
 */
export async function createArchitectureElementViaUI(
  page: Page,
  data: { title: string; elementType: string; description?: string }
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/architecture`);
  await page.locator('[data-testid="create-arch-btn"]').click();
  await page.waitForURL(/\/architecture\/[0-9a-f-]+/, { timeout: 12000 });

  const url = page.url();
  const match = url.match(/\/architecture\/([0-9a-f-]+)/);
  if (!match) throw new Error(`expected /architecture/:id URL, got: ${url}`);
  const id = match[1];

  await page.locator('[data-testid="arch-title"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="arch-title"]').fill(data.title);
  await page.locator('[data-testid="arch-element-type-select"]').selectOption(data.elementType);
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
  const panel = page.locator('[data-testid="arch-tracelink-panel"]');
  await expect(panel).toBeVisible({ timeout: 8000 });
  await page.locator('[data-testid="arch-tracelink-create-btn"]').click();
  await page.locator('[data-testid="arch-tracelink-source-select"]').waitFor({ timeout: 6000 });
  await page.locator('[data-testid="arch-tracelink-target-select"]').waitFor({ timeout: 6000 });
  await page.locator('[data-testid="arch-tracelink-target-select"]').selectOption(targetReqId);
  await page.locator('[data-testid="arch-tracelink-type-select"]').selectOption(linkType);
  await page.locator('[data-testid="arch-tracelink-save-btn"]').click();
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
  await page.locator('[data-testid="icd-interface-type-input"]').fill(data.interfaceType);
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
  await page.locator('[data-testid="global-search"]').fill(query);
  await page.waitForTimeout(600);
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
  await page.locator('[data-testid="issue-create-btn"]').click();
  await page.locator('[data-testid="issue-create-form"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="issue-title-input"]').fill(data.title);
  if (data.description) {
    await page.locator('[data-testid="issue-description-input"]').fill(data.description);
  }
  if (data.severity) {
    await page.locator('[data-testid="issue-severity-select"]').selectOption(data.severity);
  }
  if (data.status) {
    await page.locator('[data-testid="issue-status-select"]').selectOption(data.status);
  }
  await page.locator('[data-testid="issue-save-btn"]').click();
  const item = page.locator('[data-testid^="issue-item-"]').first();
  return extractIdFromTestid(item, 'issue-item-');
}

/**
 * Erstellt ein Risk über die UI und liefert die neue ID zurück.
 */
export async function createRiskViaUI(
  page: Page,
  data: { title: string; description?: string; severity?: string; probability?: string; impact?: string }
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/risks`);
  await page.locator('[data-testid="risk-create-btn"]').click();
  await page.locator('[data-testid="risk-create-form"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="risk-title-input"]').fill(data.title);
  if (data.description) {
    await page.locator('[data-testid="risk-description-input"]').fill(data.description);
  }
  if (data.severity) {
    await page.locator('[data-testid="risk-severity-select"]').selectOption(data.severity);
  }
  if (data.probability) {
    await page.locator('[data-testid="risk-probability-select"]').selectOption(data.probability);
  }
  if (data.impact) {
    await page.locator('[data-testid="risk-impact-select"]').selectOption(data.impact);
  }
  await page.locator('[data-testid="risk-save-btn"]').click();
  const item = page.locator('[data-testid^="risk-item-"]').first();
  return extractIdFromTestid(item, 'risk-item-');
}

/**
 * Erstellt einen ADR über die UI und liefert die neue ID zurück.
 */
export async function createAdrViaUI(
  page: Page,
  data: { title: string; context?: string; decision?: string; status?: string }
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/adrs`);
  await page.locator('[data-testid="adr-create-btn"]').click();
  await page.locator('[data-testid="adr-create-form"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="adr-title-input"]').fill(data.title);
  if (data.context) {
    await page.locator('[data-testid="adr-context-input"]').fill(data.context);
  }
  if (data.decision) {
    await page.locator('[data-testid="adr-decision-input"]').fill(data.decision);
  }
  if (data.status) {
    await page.locator('[data-testid="adr-status-select"]').selectOption(data.status);
  }
  await page.locator('[data-testid="adr-save-btn"]').click();
  const item = page.locator('[data-testid^="adr-item-"]').first();
  return extractIdFromTestid(item, 'adr-item-');
}

/**
 * Erstellt einen TestCase über die UI und liefert die neue ID zurück.
 */
export async function createTestCaseViaUI(
  page: Page,
  data: { title: string; description?: string; status?: string; priority?: string }
): Promise<string> {
  await page.goto(`${FRONTEND_URL}/testcases`);
  await page.locator('[data-testid="testcase-create-btn"]').click();
  await page.locator('[data-testid="testcase-create-form"]').waitFor({ timeout: 8000 });
  await page.locator('[data-testid="testcase-title-input"]').fill(data.title);
  if (data.description) {
    await page.locator('[data-testid="testcase-description-input"]').fill(data.description);
  }
  if (data.status) {
    await page.locator('[data-testid="testcase-status-select"]').selectOption(data.status);
  }
  if (data.priority) {
    await page.locator('[data-testid="testcase-priority-select"]').selectOption(data.priority);
  }
  await page.locator('[data-testid="testcase-save-btn"]').click();
  const item = page.locator('[data-testid^="testcase-item-"]').first();
  return extractIdFromTestid(item, 'testcase-item-');
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
  if (data.status) {
    await page.locator('[data-testid="testrun-status-select"]').selectOption(data.status);
  }
  await page.locator('[data-testid="testrun-save-btn"]').click();
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
    await page.locator('[data-testid="testrun-close-btn"]').click();
    await expect(page.locator('[data-testid="testrun-close-btn"]')).toHaveCount(0, { timeout: 8000 });
  }
  await page.waitForLoadState('networkidle');
}

/**
 * Erstellt eine Baseline über die UI.
 */
export async function createBaselineViaUI(
  page: Page,
  data: { scope: 'project' | 'document' | 'global'; artifactId?: string }
): Promise<void> {
  await page.goto(`${FRONTEND_URL}/baselines`);
  await page.waitForLoadState('networkidle');
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
  // Erfolgs-Indikator: Liste enthält mindestens ein Item oder leerer State erscheint neu
  await Promise.race([
    page.locator('[data-testid="baseline-list"] tbody tr').first().waitFor({ timeout: 8000 }).catch(() => null),
    page.locator('[data-testid="baselines-empty"]').waitFor({ timeout: 8000 }).catch(() => null),
  ]);
}
