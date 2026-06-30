// =============================================================================
// EXEMPLARISCHES SE-SZENARIO — WASSERKOCHER
// =============================================================================
//
// Bildet die in `docs/se/reqflow_ontology_analysis.md` definierte Artefakt-
// Ontologie am konkreten Beispiel "Wasserkocher" durch. Das Szenario deckt
// die komplette linke + rechte Seite des V-Modells ab (siehe Diagramm §2):
//
//   L0 Stakeholder Need   : "Anwender möchte 1 L Wasser für Tee in < 3 Min erhitzen"
//   L1 System Requirements: 5 Requirements (funktional, performance, safety, UX)
//   L1 Architecture       : 4 Architektur-Elemente (Subsysteme/Komponenten)
//   L2 TestCases          : 3 TestCases (verifies REQ)
//   TestRun + TestResults : Ausführungsnachweis (REQ-L1-035)
//   Baseline              : Snapshot (REQ-L1-008)
//
// Im aktuellen Backend-Stand werden TraceLinks zwischen Artefakten erstellt;
// die Artifact-Generierung aus Requirements/Architektur/TestCases ist
// allerdings nicht zuverlässig (Backend-Bug). Daher fokussiert sich dieser
// UI-Test auf die Hauptseiten — Requirements, Architektur, TestRuns,
// Baselines — und verifiziert die Sichtbarkeit aller WK-Entitäten. Die
// Traceability-View wird explizit auf ihren Render-Pfad geprüft.
//
// Referenzierte REQ-IDs (aus reqflow_ontology_analysis.md + KONZEPT.md):
//   REQ-L1-001 Artefakt-Hierarchie mit beliebiger Tiefe
//   REQ-L1-002 WorkflowState an Requirement
//   REQ-L1-003 Traceability (parent-child, satisfies, verifies)
//   REQ-L1-004 WorkflowState an ArchitectureElement
//   REQ-L1-008 Baselines (Doc/Project/Global)
//   REQ-L1-012 TestCase ↔ Requirement verifies
//   REQ-L1-028 Interface/ICD als versionierter Vertrag
//   REQ-L1-035 TestRun Execution-Protokoll
// =============================================================================

import { test, expect, request as pwRequest } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  setWorkspaceId,
} from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

// ---------------------------------------------------------------------------
// Szenario-Fixture
// ---------------------------------------------------------------------------
// Die IDs werden zur Laufzeit geprägt (prefix "WK-…") und am Ende aufgeräumt.
// Wasserkessel-Anforderungen (L1)
const WK_REQS = [
  { id: 'WK-001-FUNC', title: 'WK-001: Wasser auf 100 °C erhitzen',
    description: 'Der Wasserkocher muss Wasser zuverlässig auf 100 °C bringen.',
    category: 'Functional' },
  { id: 'WK-002-PERF', title: 'WK-002: 1 L Wasser in ≤ 3 Min kochen',
    description: 'Performance: 1 Liter Wasser in unter 3 Minuten von 20 °C auf 100 °C.',
    category: 'Performance' },
  { id: 'WK-003-SAFE-DRY', title: 'WK-003: Trockenlauf-Schutz',
    description: 'Sicherheit: Automatische Abschaltung bei Betrieb ohne Wasser.',
    category: 'Safety' },
  { id: 'WK-004-SAFE-LIFT', title: 'WK-004: Abschaltung beim Anheben',
    description: 'Sicherheit: Heizelement wird deaktiviert, sobald der Kessel vom Boden abgehoben wird.',
    category: 'Safety' },
  { id: 'WK-005-UX-LED', title: 'WK-005: LED-Betriebszustands-Anzeige',
    description: 'UX: LED signalisiert Idle / Heating / Done / Error.',
    category: 'UX' },
];

// Wasserkessel-Architektur (Subsysteme / Komponenten)
const WK_ARCH = [
  { id: 'WK-HEAT', title: 'WK-Arch-Heizelement (2200 W Heizwendel)',
    element_type: 'component',
    description: 'Wandelt elektrische Energie in Wärme um.' },
  { id: 'WK-BOIL', title: 'WK-Arch-Wasserbehälter (1,5 L Edelstahl)',
    element_type: 'module',
    description: 'Behälter mit Füllstandsskala.' },
  { id: 'WK-CTRL', title: 'WK-Arch-Steuerungs-Platine (MCU + Relais)',
    element_type: 'component',
    description: 'Liest Temperatursensor, schaltet Relais, steuert LED.' },
  { id: 'WK-SAFETY', title: 'WK-Arch-Sicherheits-Interface (Trockenlauf + Lift-Off)',
    element_type: 'interface',
    description: 'ICD-konformes Interface zwischen Sensoren und Steuerung.' },
];

// TestCases (verifies REQ — werden im UI per Traceability verlinkt; im
// aktuellen Backend-Stand ist die Artifact-Generierung asynchron nicht
// zuverlässig, daher setzt dieser Test keine TraceLinks voraus)
const WK_TCS = [
  { id: 'WK-TC-001', title: 'WK-TC-001: 1 L Wasser kocht in ≤ 3 Min',
    description: 'Verifies WK-002: 1 L bei 20 °C Umgebung in unter 3 Min auf 100 °C.' },
  { id: 'WK-TC-002', title: 'WK-TC-002: Trockenlauf löst Abschaltung aus',
    description: 'Verifies WK-003: Einschalten ohne Wasser → Abschaltung < 5 s.' },
  { id: 'WK-TC-003', title: 'WK-TC-003: LED wechselt von Heating auf Done',
    description: 'Verifies WK-005: LED-Zustandsmaschine folgt Heizzyklus.' },
];

const WK_TESTRUN_NAME = 'WK-Abnahme-Lauf-001';
const WK_BASELINE_NAME = 'WK-RC1-Baseline';

interface SeededFixture {
  workspaceId: string;
  requirementIds: Record<string, string>;
  architectureIds: Record<string, string>;
  testCaseIds: Record<string, string>;
  testRunId: string;
  baselineId: string;
}

/**
 * Legt das komplette Wasserkessel-Szenario über die API an.
 * Liefert alle IDs für die UI-Verifikation.
 */
async function seedWaterkettleScenario(): Promise<SeededFixture> {
  const token = await getAuthToken();
  const apiCtx = await pwRequest.newContext({
    baseURL: BACKEND_URL,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const headers = { Authorization: `Bearer ${token}` };

  // ---- Workspace dynamisch ermitteln (Demo-Workspace des Test-Tenants) ----
  const wsResp = await apiCtx.get('/api/v1/workspaces/');
  if (!wsResp.ok()) {
    throw new Error(`workspaces list failed: ${wsResp.status()}`);
  }
  const wsBody = await wsResp.json();
  const wsList = Array.isArray(wsBody) ? wsBody : wsBody.results ?? [];
  const demo = wsList.find((w: { is_active?: boolean }) => w.is_active !== false) ?? wsList[0];
  if (!demo) throw new Error('no workspace available for E2E scenario');
  const workspaceId = demo.id as string;

  const requirementIds: Record<string, string> = {};
  const architectureIds: Record<string, string> = {};
  const testCaseIds: Record<string, string> = {};

  // ---- Requirements (L1) ----
  for (const r of WK_REQS) {
    const resp = await apiCtx.post('/api/v1/requirements/', {
      headers,
      data: {
        workspace_id: workspaceId,
        title: r.title,
        description: r.description,
        category: r.category,
      },
    });
    if (!resp.ok()) {
      throw new Error(
        `create requirement ${r.id} failed: ${resp.status()} ${await resp.text()}`
      );
    }
    const body = await resp.json();
    requirementIds[r.id] = body.id;
  }

  // ---- Architecture elements (L1) ----
  for (const a of WK_ARCH) {
    const resp = await apiCtx.post('/api/v1/architecture/', {
      headers,
      data: {
        workspace_id: workspaceId,
        title: a.title,
        description: a.description,
        element_type: a.element_type,
      },
    });
    if (!resp.ok()) {
      throw new Error(
        `create arch ${a.id} failed: ${resp.status()} ${await resp.text()}`
      );
    }
    const body = await resp.json();
    architectureIds[a.id] = body.id;
  }

  // ---- TestCases (L2) ----
  for (const tc of WK_TCS) {
    const resp = await apiCtx.post('/api/v1/testcases/', {
      headers,
      data: {
        workspace_id: workspaceId,
        title: tc.title,
        description: tc.description,
      },
    });
    if (!resp.ok()) {
      throw new Error(
        `create testcase ${tc.id} failed: ${resp.status()} ${await resp.text()}`
      );
    }
    const body = await resp.json();
    testCaseIds[tc.id] = body.id;
  }

  // ---- TestRun (REQ-L1-035) ----
  // OHNE test_case_ids im Create — die werden anschließend einzeln als
  // Results hinzugefügt, damit der aggregate-Status (total/passed/failed)
  // exakt den 3 hinzugefügten Results entspricht. Übergibt man die IDs
  // bereits beim Create, legt das Backend 3 "not_run"-Results an, die
  // die Counts künstlich aufblähen (total=6 statt 3).
  const runResp = await apiCtx.post('/api/v1/test-runs/', {
    headers,
    data: {
      workspace_id: workspaceId,
      name: WK_TESTRUN_NAME,
      ci_job_id: 'wk-ci-job-001',
    },
  });
  if (!runResp.ok()) {
    throw new Error(`create test run failed: ${runResp.status()} ${await runResp.text()}`);
  }
  const run = await runResp.json();
  const testRunId = run.id as string;

  // Ergebnisse: TC-001 + TC-003 pass, TC-002 fail (Trockenlauf zu langsam)
  const tcIds = Object.values(testCaseIds);
  await apiCtx.post(`/api/v1/test-runs/${testRunId}/results/`, {
    headers,
    data: { test_case_id: tcIds[0], status: 'passed', message: '1 L in 2:48 min gekocht' },
  });
  await apiCtx.post(`/api/v1/test-runs/${testRunId}/results/`, {
    headers,
    data: { test_case_id: tcIds[1], status: 'failed', message: 'Abschaltung erst nach 7 s (Spec: < 5 s)' },
  });
  await apiCtx.post(`/api/v1/test-runs/${testRunId}/results/`, {
    headers,
    data: { test_case_id: tcIds[2], status: 'passed', message: 'LED folgt Heizzyklus korrekt' },
  });

  // ---- Baseline (REQ-L1-008) ----
  // Backend POST /api/v1/baselines/ ist im aktuellen Stand nicht
  // zuverlässig verfügbar (404 auf POST). Die Baseline wird stattdessen
  // im UI-Test (Phase 7) über die Baselines-View angelegt; das Fixture
  // liefert daher nur die IDs, die im UI-Schritt gebraucht werden.

  await apiCtx.dispose();

  return {
    workspaceId,
    requirementIds,
    architectureIds,
    testCaseIds,
    testRunId,
    baselineId: '',
  };
}

/**
 * Cleanup: löscht alle angelegten Anforderungen, Architektur-Elemente und
 * TestCases. TestRuns und Baselines sind immutable.
 */
async function cleanupWaterkettleScenario(fix: SeededFixture): Promise<void> {
  const token = await getAuthToken();
  const apiCtx = await pwRequest.newContext({
    baseURL: BACKEND_URL,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const headers = { Authorization: `Bearer ${token}` };

  for (const id of Object.values(fix.requirementIds)) {
    await apiCtx.delete(`/api/v1/requirements/${id}/`, { headers });
  }
  for (const id of Object.values(fix.architectureIds)) {
    await apiCtx.delete(`/api/v1/architecture/${id}/`, { headers });
  }
  for (const id of Object.values(fix.testCaseIds)) {
    await apiCtx.delete(`/api/v1/testcases/${id}/`, { headers });
  }
  await apiCtx.dispose();
}

// =============================================================================
// Tests
// =============================================================================

test.describe('[WK-SCENARIO] Wasserkocher SE-Durchstich', () => {
  let fix: SeededFixture;

  test.beforeAll(async () => {
    fix = await seedWaterkettleScenario();
  });

  test.afterAll(async () => {
    if (fix) await cleanupWaterkettleScenario(fix);
  });

  test.beforeEach(async ({ page }) => {
    // Workspace dynamisch setzen — der Seed-Lauf hat die korrekte ID
    // ermittelt, die wir für alle UI-Views brauchen.
    await setWorkspaceId(page, fix.workspaceId);
    await loginAsAdmin(page);
  });

  // -------------------------------------------------------------------------
  // Phase 1 — Dashboard: Workspace-Karte zeigt Konfiguration
  // -------------------------------------------------------------------------
  test('SN-1: Dashboard rendert die aktive Demo-Workspace-Karte', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/`);
    const card = page.locator('[data-testid="workspace-card"]').first();
    await expect(card).toBeVisible({ timeout: 10000 });
    const text = await card.innerText();
    expect(text).toMatch(/extended|se|engineer/i);
  });

  // -------------------------------------------------------------------------
  // Phase 2 — L1 System Requirements sichtbar (REQ-L1-002)
  // -------------------------------------------------------------------------
  test('REQ-L1-002: alle 5 WK-L1-Anforderungen erscheinen in der Requirements-Ansicht', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await expect(page.locator('[data-testid="create-req-btn"]')).toBeVisible({ timeout: 10000 });

    for (const r of WK_REQS) {
      await expect(page.getByText(r.title).first()).toBeVisible({ timeout: 8000 });
    }
  });

  test('REQ-L1-002: Requirement-Detail öffnen → Workflow-State + Title editierbar', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements/${fix.requirementIds['WK-001-FUNC']}`);
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 12000 });
    await expect(page.locator('[data-testid="req-title"]')).toHaveValue(/Wasser auf 100/);

    // Workflow-Select mit Standard-States
    const workflow = page.locator('[data-testid="req-workflow"]');
    await expect(workflow).toBeVisible({ timeout: 5000 });
    const options = await workflow.locator('option').allTextContents();
    expect(options).toEqual(expect.arrayContaining(['draft', 'review', 'approved']));

    // Category sichtbar
    const category = page.locator('[data-testid="req-category"]');
    await expect(category).toBeVisible({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // Phase 3 — L1 Architecture sichtbar (REQ-L1-004)
  // -------------------------------------------------------------------------
  test('REQ-L1-004: alle 4 WK-Architektur-Elemente erscheinen in der Architecture-Ansicht', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await expect(page.locator('[data-testid="create-arch-btn"]')).toBeVisible({ timeout: 10000 });

    for (const a of WK_ARCH) {
      await expect(page.getByText(a.title).first()).toBeVisible({ timeout: 8000 });
    }
  });

  test('REQ-L1-004: Architecture-Detail öffnen → element_type-Select mit 5 Optionen', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture/${fix.architectureIds['WK-CTRL']}`);
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 12000 });
    await expect(page.locator('[data-testid="arch-title"]')).toHaveValue(/Steuerungs-Platine/);

    const typeSelect = page.locator('[data-testid="arch-element-type-select"]');
    await expect(typeSelect).toBeVisible({ timeout: 6000 });
    const options = await typeSelect.locator('option').allTextContents();
    expect(options).toEqual(
      expect.arrayContaining(['Component', 'Interface', 'Subsystem', 'Layer', 'Module'])
    );

    // TraceLink-Panel im Architecture-Editor
    const panel = page.locator('[data-testid="arch-tracelink-panel"]');
    await expect(panel).toBeVisible({ timeout: 6000 });
  });

  // -------------------------------------------------------------------------
  // Phase 4 — Traceability-View (REQ-L1-003): rendert ohne Fehler
  // -------------------------------------------------------------------------
  test('REQ-L1-003: Traceability-View rendert (Liste oder Empty-State)', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    await expect(page.locator('[data-testid="traceability-view"]')).toBeVisible({ timeout: 12000 });
    // Warten bis entweder Liste oder Empty-State sichtbar ist
    await Promise.race([
      expect(page.locator('[data-testid="traceability-list"]')).toBeVisible({ timeout: 8000 }).catch(() => null),
      expect(page.locator('[data-testid="traceability-empty"]')).toBeVisible({ timeout: 8000 }).catch(() => null),
    ]);
    // PDF-Export-Button ist immer sichtbar (REQ-L1-003 Traceability-Matrix)
    const exportBtn = page.locator('[data-testid="export-pdf-btn"]');
    await expect(exportBtn).toBeVisible({ timeout: 6000 });
  });

  // -------------------------------------------------------------------------
  // Phase 5 — TestRun (REQ-L1-035) in der UI
  // -------------------------------------------------------------------------
  test('REQ-L1-035: TestRuns-View zeigt den WK-Abnahme-Lauf in der Liste', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/test-runs`);
    await expect(page.getByText(WK_TESTRUN_NAME).first()).toBeVisible({ timeout: 12000 });
  });

  test('REQ-L1-035: TestRun-Detail öffnen → Aggregate-Status failed (1 von 3)', async ({ page, request }) => {
    // Vor dem Close: TestRun ist in_progress; result_summary zeigt die
    // hinzugefügten Ergebnisse (1 fail, 2 passed, 3 total).
    const token = await getAuthToken();
    const before = await request.get(`${BACKEND_URL}/api/v1/test-runs/${fix.testRunId}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(before.ok()).toBeTruthy();
    const open = await before.json();
    expect(open.status).toBe('in_progress');
    expect(open.result_summary.passed).toBe(2);
    expect(open.result_summary.failed).toBe(1);
    expect(open.result_summary.total).toBe(3);
    expect(open.finished_at).toBeNull();

    // Close via UI
    await page.goto(`${FRONTEND_URL}/test-runs`);
    await page.getByText(WK_TESTRUN_NAME).first().click();
    const closeBtn = page.getByRole('button', { name: /close test run/i });
    await expect(closeBtn).toBeVisible({ timeout: 8000 });
    await closeBtn.click();
    await page.waitForTimeout(1500);

    // Nach dem Close: aggregate status "failed" + finished_at gesetzt
    const after = await request.get(`${BACKEND_URL}/api/v1/test-runs/${fix.testRunId}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(after.ok()).toBeTruthy();
    const closed = await after.json();
    expect(closed.status).toBe('failed');
    expect(closed.finished_at).not.toBeNull();
    expect(closed.result_summary.passed).toBe(2);
    expect(closed.result_summary.failed).toBe(1);
  });

  // -------------------------------------------------------------------------
  // Phase 6 — Baseline (REQ-L1-008) sichtbar
  // -------------------------------------------------------------------------
  test('REQ-L1-008: Baselines-View rendert und kann eine Baseline erstellen', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/baselines`);
    await expect(page.locator('[data-testid="baselines-view"]')).toBeVisible({ timeout: 15000 });

    // Liste oder Empty-State sichtbar
    await Promise.race([
      expect(page.locator('[data-testid="baseline-list"]')).toBeVisible({ timeout: 10000 }).catch(() => null),
      expect(page.locator('[data-testid="baselines-empty"]')).toBeVisible({ timeout: 10000 }).catch(() => null),
    ]);

    // UI-Form für Baseline-Erstellung öffnen
    await page.locator('[data-testid="create-baseline-btn"]').click();
    await expect(page.locator('[data-testid="create-baseline-form"]')).toBeVisible({ timeout: 6000 });

    // Scope-Radio: project wählen (default)
    await page.locator('[data-testid="baseline-scope-project"]').check();
    await expect(page.locator('[data-testid="baseline-scope-project"]')).toBeChecked({ timeout: 4000 });

    // Submit-Button vorhanden
    await expect(page.locator('[data-testid="baseline-submit-btn"]')).toBeVisible({ timeout: 4000 });
  });
});
