// =============================================================================
// WK-FULL-BLOWN — Wasserkocher SysEng über 4 Ebenen, UI-gesteuert
// =============================================================================
//
// Bildet die komplette SE-Ontologie (reqflow_ontology_analysis.md) am
// Beispiel "Wasserkocher" durch — diesmal über 4 Ebenen mit Issues, Risks,
// ADRs, mehreren Baselines, Versions, ICD-Versionierung und Diagrammen.
//
// STEUERUNG: Vollständig über die Browser-UI. API wird nur noch für
// Test-Daten-Setup verwendet (z. B. TestRun-Results), wo die UI keine
// Eingabeform hat.
//
// MISSION: Bug-Finding — der Test versucht die UI systematisch auszuhebeln
// (Race Conditions, Encoding-Probleme, fehlende UI-Elemente, Cross-Cutting-
// Inkonsistenzen) und schreibt die Funde in `wk-bug-report.md`.
//
// Verwendet: e2e/tests/wk-helpers.ts
// =============================================================================

import { test, expect, request as pwRequest } from '@playwright/test';
import * as fsSync from 'fs';
import { promises as fs } from 'fs';
import * as path from 'path';
import {
  loginAsAdmin,
  getAuthToken,
  setWorkspaceId,
  createIsolatedWorkspace,
} from '../helpers/auth';
import {
  createRequirementViaUI,
  createArchitectureElementViaUI,
  createDiagramViaUI,
  createIcdViaUI,
  createTraceLinkViaUI,
  createIssueViaUI,
  createRiskViaUI,
  createAdrViaUI,
  createTestCaseViaUI,
  createTestRunViaUI,
  createBaselineViaUI,
  transitionTestRunViaUI,
  setWorkspacePresetViaUI,
  globalSearchAndClick,
  BACKEND_URL,
  FRONTEND_URL,
} from './wk-helpers';

// ---------------------------------------------------------------------------
// Szenario-Fixture: 4-Ebenen-Wasserkessel
// ---------------------------------------------------------------------------

const SCENARIO = {
  // L0 — Stakeholder Need (als Requirement dokumentiert)
  L0_SN: {
    title: 'WK-SN-001: Stakeholder Need — Tee in unter 3 Min',
    description: 'Endanwender erwartet, dass 1 L Wasser in ≤ 3 Min auf 100 °C erhitzt wird.',
  },
  // L1 — System Requirements
  L1: [
    { id: 'L1-FUNC', title: 'WK-L1-001-FUNC: Wasser auf 100 °C erhitzen', category: 'Functional' },
    { id: 'L1-PERF', title: 'WK-L1-002-PERF: 1 L in ≤ 3 Min', category: 'Performance' },
    { id: 'L1-SAFE-DRY', title: 'WK-L1-003-SAFE-DRY: Trockenlauf-Schutz', category: 'Safety' },
    { id: 'L1-SAFE-LIFT', title: 'WK-L1-004-SAFE-LIFT: Lift-Off-Abschaltung', category: 'Safety' },
    { id: 'L1-UX-LED', title: 'WK-L1-005-UX-LED: LED-Betriebszustand', category: 'UX' },
  ],
  // L2 — Subsystem Requirements
  L2: [
    { id: 'L2-HEAT-001', title: 'WK-L2-HEAT-001: Heizwendel 2200 W', parent: 'L1-PERF' },
    { id: 'L2-HEAT-002', title: 'WK-L2-HEAT-002: Thermosicherung 130 °C', parent: 'L1-SAFE-DRY' },
    { id: 'L2-CTRL-001', title: 'WK-L2-CTRL-001: MCU STM32F030', parent: 'L1-FUNC' },
    { id: 'L2-CTRL-002', title: 'WK-L2-CTRL-002: Relais 16 A', parent: 'L1-FUNC' },
    { id: 'L2-SAFE-001', title: 'WK-L2-SAFE-001: Trockenlaufsensor', parent: 'L1-SAFE-DRY' },
    { id: 'L2-SAFE-002', title: 'WK-L2-SAFE-002: Lift-Off-Mikroschalter', parent: 'L1-SAFE-LIFT' },
    { id: 'L2-UX-001', title: 'WK-L2-UX-001: LED-Treiber PWM', parent: 'L1-UX-LED' },
  ],
  // L3 — Komponenten Requirements
  L3: [
    { id: 'L3-HEAT-001-A', title: 'WK-L3-HEAT-001-A: CrNi 80/20 Heizdraht', parent: 'L2-HEAT-001' },
    { id: 'L3-HEAT-001-B', title: 'WK-L3-HEAT-001-B: Mineralwolle-Isolation', parent: 'L2-HEAT-001' },
    { id: 'L3-CTRL-001-A', title: 'WK-L3-CTRL-001-A: GPIO PA0 = Heiz-Relais', parent: 'L2-CTRL-001' },
    { id: 'L3-CTRL-001-B', title: 'WK-L3-CTRL-001-B: ADC1_IN1 = NTC-Sensor', parent: 'L2-CTRL-001' },
    { id: 'L3-SAFE-001-A', title: 'WK-L3-SAFE-001-A: Widerstands-Mess-Brücke', parent: 'L2-SAFE-001' },
  ],
  // L1-L3 — Architektur-Elemente
  ARCH: [
    { id: 'A-KESSEL', title: 'WK-Arch-Kessel (Modul)', elementType: 'module' },
    { id: 'A-HEAT', title: 'WK-Arch-Heizelement', elementType: 'component' },
    { id: 'A-CTRL', title: 'WK-Arch-Steuerung-MCU', elementType: 'component' },
    { id: 'A-RELAY', title: 'WK-Arch-Relais-Layer', elementType: 'layer' },
    { id: 'A-SAFETY-IF', title: 'WK-Arch-Safety-Interface', elementType: 'interface' },
    { id: 'A-LED', title: 'WK-Arch-LED-Modul', elementType: 'module' },
    { id: 'A-SENSOR-T', title: 'WK-Arch-Temperatursensor', elementType: 'component' },
    { id: 'A-POWER', title: 'WK-Arch-Stromversorgung', elementType: 'subsystem' },
  ],
};

// Bug-Report: jeder Bug wird in eine INDIVIDUELLE Datei geschrieben.
// Das Verzeichnis wird NICHT beim Modul-Load gelöscht (würde mit Modul-
// Reloads kollidieren). Stattdessen werden alle Bug-Dateien am Ende
// des Test-Runs im `afterAll` zu einem konsolidierten Report
// zusammengeführt.
const BUG_REPORT_DIR = path.join(__dirname, 'wk-bugs');
const BUG_REPORT_PATH = path.join(__dirname, 'wk-bug-report.md');
fsSync.mkdirSync(BUG_REPORT_DIR, { recursive: true });
const G2 = globalThis as unknown as {
  __WK_BUG_COUNTER__?: number;
  __WK_BUG_IDS__?: Set<string>;
};
if (G2.__WK_BUG_COUNTER__ === undefined) G2.__WK_BUG_COUNTER__ = 0;
if (!G2.__WK_BUG_IDS__) G2.__WK_BUG_IDS__ = new Set<string>();

function logBug(id: string, title: string, details: string): void {
  const key = `${id}::${title}`;
  // WICHTIG: IDs persistent in globalThis speichern (umgeht Modul-Reloads)
  if (G2.__WK_BUG_IDS__!.has(key)) return;
  G2.__WK_BUG_IDS__!.add(key);
  G2.__WK_BUG_COUNTER__!++;
  const n = G2.__WK_BUG_COUNTER__!;
  const file = path.join(BUG_REPORT_DIR, `bug-${String(n).padStart(4, '0')}-${id}.md`);
  const content = `# Bug ${n}: [${id}] ${title}\n\n${details}\n`;
  fsSync.writeFileSync(file, content, 'utf-8');
  // eslint-disable-next-line no-console
  console.warn(`\n🐛 BUG ${id}: ${title}\n  → ${file}\n${details}\n`);
}

interface ApiIds {
  workspaceId: string;
  requirementIds: Record<string, string>;
  architectureIds: Record<string, string>;
  testCaseIds: Record<string, string>;
  issueIds: string[];
  riskIds: string[];
  adrIds: string[];
  testRunIds: Record<string, string>;
  /**
   * Issue #947: keyed by scenario key ('BLOCK' | 'CONTEXT' | 'FLOW') so Phase 4d
   * can address *its* diagram by ID instead of by name + `.first()`, and so
   * `cleanupViaAPI` actually has something to delete. `createDiagramViaUI`
   * returned `void` before, which left this map permanently empty and made the
   * diagram-cleanup loop dead code.
   */
  diagramIds: Record<string, string>;
  icdIds: string[];
  baselineIds: string[];
}

/**
 * Soft-delete every artifact this run created.
 *
 * Baselines and TestRuns are immutable and stay behind by design. Diagrams/ICDs
 * used to be in the same bucket only because their helpers never returned an id
 * (issue #947) — they are deleted now.
 *
 * Requirements need a `change_reason` body: `RequirementService.delete_requirement`
 * enforces the workspace's change_reason preset policy (#604) and this scenario
 * sets the workspace to `extended` in Phase 0, so a body-less DELETE is answered
 * with 400 VALIDATION_ERROR. The previous `.delete(url)` call ignored the
 * response, so the failure was invisible — same silent-no-op class as the
 * diagram leak, found while verifying #947.
 *
 * Failures are reported instead of swallowed: a cleanup that silently no-ops is
 * exactly how the diagram leak went unnoticed, and it makes the next run's
 * "is this state fresh?" question unanswerable.
 */
async function cleanupViaAPI(ids: ApiIds, token: string): Promise<void> {
  const apiCtx = await pwRequest.newContext({
    baseURL: BACKEND_URL,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const headers = { Authorization: `Bearer ${token}` };
  const failures: string[] = [];

  const remove = async (
    path: string,
    data?: Record<string, string>
  ): Promise<void> => {
    const response = await apiCtx.delete(path, { headers, ...(data ? { data } : {}) });
    // 404 is tolerated: an earlier phase may already have removed the artifact
    // (or a previous run cleaned it up), which is not a cleanup defect.
    if (!response.ok() && response.status() !== 404) {
      failures.push(`${path} -> ${response.status()}`);
    }
  };

  // Diagrams: löschbar
  for (const id of Object.values(ids.diagramIds)) {
    await remove(`/api/v1/diagrams/${id}/`);
  }
  // ICDs: löschbar
  for (const id of ids.icdIds) {
    await remove(`/api/v1/icds/${id}/`);
  }
  // Issues/Risks/ADRs: löschbar
  for (const id of ids.issueIds) {
    await remove(`/api/v1/issues/${id}/`);
  }
  for (const id of ids.riskIds) {
    await remove(`/api/v1/risks/${id}/`);
  }
  for (const id of ids.adrIds) {
    await remove(`/api/v1/adrs/${id}/`);
  }
  // TestCases
  for (const id of Object.values(ids.testCaseIds)) {
    await remove(`/api/v1/testcases/${id}/`);
  }
  // Architektur
  for (const id of Object.values(ids.architectureIds)) {
    await remove(`/api/v1/architecture/${id}/`);
  }
  // Requirements — change_reason required under the extended preset policy.
  for (const id of Object.values(ids.requirementIds)) {
    await remove(`/api/v1/requirements/${id}/`, {
      change_reason: 'E2E cleanup (waterkettle-fullblown afterAll)',
    });
  }

  await apiCtx.dispose();
  if (failures.length > 0) {
    // eslint-disable-next-line no-console
    console.warn(
      `\n⚠️  cleanupViaAPI: ${failures.length} artifact(s) could not be deleted ` +
        `(the run leaves them behind in workspace ${ids.workspaceId}):\n  ` +
        failures.join('\n  ')
    );
  }
}

// ---------------------------------------------------------------------------
// TestRun-Result Seed (API): Die UI hat keine Form für einzelne Results.
// Dieser Seed dient ausschließlich dazu, den 4-Phase-Lifecycle bis
// "closed/failed" zu ermöglichen.
// ---------------------------------------------------------------------------
async function seedTestRunResult(
  token: string,
  runId: string,
  testCaseId: string,
  resultStatus: 'passed' | 'failed' | 'blocked' | 'not_run',
  message?: string
): Promise<void> {
  const apiCtx = await pwRequest.newContext({
    baseURL: BACKEND_URL,
    extraHTTPHeaders: { Authorization: `Bearer ${token}` },
  });
  const resp = await apiCtx.post(`/api/v1/test-runs/${runId}/results/`, {
    data: { test_case_id: testCaseId, status: resultStatus, message: message ?? '' },
  });
  if (!resp.ok()) {
    const body = await resp.text().catch(() => '<disposed>');
    throw new Error(`seedTestRunResult failed (${resp.status()}): ${body}`);
  }
  await apiCtx.dispose();
}

// =============================================================================
// Tests
// =============================================================================

test.describe('[WK-FULL-BLOWN] Wasserkocher SE über 4 Ebenen (UI-driven, Bug-Finding)', () => {
  test.setTimeout(120_000); // Mehrere UI-Create-Aktionen brauchen Zeit

  let ids: ApiIds;
  let token: string;

  test.beforeAll(async () => {
    token = await getAuthToken();
    // Eigene, leere Workspace — verhindert [I5]-Kollisionen (max. 1 Root-
    // ArchitectureElement pro Workspace) mit der geteilten Demo-Workspace.
    const workspaceId = await createIsolatedWorkspace(token);

    ids = {
      workspaceId,
      requirementIds: {},
      architectureIds: {},
      testCaseIds: {},
      issueIds: [],
      riskIds: [],
      adrIds: [],
      testRunIds: {},
      diagramIds: {},
      icdIds: [],
      baselineIds: [],
    };
  });

  test.afterAll(async () => {
    if (ids) {
      await cleanupViaAPI(ids, token);
    }
    // Bug-Report aus den einzelnen Bug-Dateien zusammenbauen,
    // dedupliziert nach Bug-ID (über mehrere Worker-Reloads hinweg
    // kann dieselbe Bug-ID mehrfach auftauchen, da der Counter neu
    // beginnt — wir behalten die erste Version).
    try {
      const files = fsSync.readdirSync(BUG_REPORT_DIR)
        .filter((f) => f.startsWith('bug-') && f.endsWith('.md'))
        .sort();
      const seen = new Set<string>();
      const unique: string[] = [];
      const fileByKey = new Map<string, string>();
      for (const f of files) {
        const content = fsSync.readFileSync(path.join(BUG_REPORT_DIR, f), 'utf-8');
        const m = content.match(/^# Bug \d+: \[([^\]]+)\] (.+?)$/m);
        if (!m) continue;
        const key = `${m[1]}::${m[2]}`;
        if (seen.has(key)) continue;
        seen.add(key);
        unique.push(content);
        fileByKey.set(key, f);
      }
      const report = [
        `# WK-FULL-BLOWN Bug-Report`,
        ``,
        `Generiert: ${new Date().toISOString()}`,
        `Total: ${unique.length} unique Bug(s) (aus ${files.length} Funde)`,
        ``,
        ...unique,
        `---`,
        ``,
      ].join('\n');
      fsSync.writeFileSync(BUG_REPORT_PATH, report, 'utf-8');
      // eslint-disable-next-line no-console
      console.warn(`\n📝 Bug-Report: ${BUG_REPORT_PATH} (${unique.length} unique Funde)\n`);
      // Bug-Dateien NICHT aufräumen — bleiben für Inspektion im wk-bugs/ Verzeichnis
    } catch (err) {
      // eslint-disable-next-line no-console
      console.error('Bug-Report finalisieren fehlgeschlagen:', err);
    }
  });

  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, ids.workspaceId);
    await loginAsAdmin(page);
  });

  // ===========================================================================
  // PHASE 0 — Preset-Wechsel (UI)
  // ===========================================================================
  test('Phase 0: Preset extended via UI setzen (Voraussetzung für Baselines/ICDs)', async ({ page }) => {
    await setWorkspacePresetViaUI(page, 'extended');
  });

  // ===========================================================================
  // PHASE 1a — Stakeholder Need (L0) über UI
  // ===========================================================================
  test('Phase 1a: Stakeholder Need WK-SN-001 über UI anlegen', async ({ page }) => {
    const id = await createRequirementViaUI(page, {
      title: SCENARIO.L0_SN.title,
      description: SCENARIO.L0_SN.description,
      category: 'Functional',
    });
    ids.requirementIds['L0_SN'] = id;
    expect(id).toMatch(/^[0-9a-f-]+$/);
  });

  // ===========================================================================
  // PHASE 1b — L1 + L2 + L3 System Requirements über UI
  // (alle 17 REQs in einem Test, weil Browser-Context-Reset zu langsam ist)
  // ===========================================================================
  test('Phase 1b: 17 System-Requirements (L1+L2+L3) über UI anlegen', async ({ page }) => {
    for (const r of [...SCENARIO.L1, ...SCENARIO.L2, ...SCENARIO.L3]) {
      const id = await createRequirementViaUI(page, {
        title: r.title,
        category: 'Functional',
      });
      ids.requirementIds[r.id] = id;
    }
    // Total-Check: 1 SN + 5 L1 + 7 L2 + 5 L3 = 18
    const total = Object.keys(ids.requirementIds).length;
    expect(total).toBe(18);
  });

  // ===========================================================================
  // PHASE 1e — BUG: Encoding-Test mit Umlauten/°C
  // ===========================================================================
  test('Phase 1e: BUG-FINDING — Encoding mit °C und Umlauten in REQ-Titeln', async ({ page }) => {
    const tricky = 'WK-L1-999-ENCODING: Heizt auf 100 °C — ä ö ü ß Ω µ';
    const id = await createRequirementViaUI(page, {
      title: tricky,
      category: 'Functional',
    });
    ids.requirementIds['L1-999-ENC'] = id;

    await page.goto(`${FRONTEND_URL}/requirements/${id}`);
    const titleInput = page.locator('[data-testid="artifact-field-title"]');
    const value = await titleInput.inputValue();
    if (value !== tricky) {
      logBug(
        'B-ENC-001',
        'Encoding-Fehler im Requirement-Editor: Sonderzeichen werden falsch gespeichert',
        `Erwartet: "${tricky}"\nTatsächlich: "${value}"`
      );
    }
  });

  // ===========================================================================
  // PHASE 1f — 8 Architektur-Elemente über UI
  // ===========================================================================
  test('Phase 1f: 8 Architektur-Elemente über UI anlegen (alle 5 element_types)', async ({ page }) => {
    // [I5]: nur ein Root-ArchitectureElement pro Workspace erlaubt — das
    // erste Element wird als Root angelegt, alle weiteren als seine Kinder.
    const [root, ...rest] = SCENARIO.ARCH;
    const rootId = await createArchitectureElementViaUI(page, {
      title: root.title,
      elementType: root.elementType,
    });
    ids.architectureIds[root.id] = rootId;
    for (const a of rest) {
      const id = await createArchitectureElementViaUI(
        page,
        { title: a.title, elementType: a.elementType },
        rootId
      );
      ids.architectureIds[a.id] = id;
    }
    // 5 element_types abgedeckt: module, component, layer, interface, subsystem
    const types = new Set(SCENARIO.ARCH.map((a) => a.elementType));
    expect(types.size).toBe(5);
  });

  // ===========================================================================
  // PHASE 1g — BUG: Sehr lange Titel in der UI
  // ===========================================================================
  test('Phase 1g: BUG-FINDING — Sehr langer REQ-Titel (UI-Layout-Bruch)', async ({ page }) => {
    test.setTimeout(30_000);
    const longTitle = 'WK-L1-998-LONG: ' + 'X'.repeat(30);
    const id = await createRequirementViaUI(page, { title: longTitle, category: 'Functional' });
    ids.requirementIds['L1-998-LONG'] = id;

    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.waitForLoadState('networkidle');
    // Wait for the requirement tree to actually render (RequirementList.tsx
    // data-testid="req-list-tree") instead of a fixed delay, before probing
    // for the long-title card below. Scoped to the tree (issue #947): the bare
    // getByText could also resolve a matching node in the sidebar/header.
    const tree = page.getByTestId('req-list-tree');
    await expect(tree).toBeVisible({ timeout: 8000 });
    const card = tree.getByText(longTitle.slice(0, 25)).first();
    const visible = await card.isVisible().catch(() => false);
    if (visible) {
      const overflow = await card.evaluate((el) => {
        const s = window.getComputedStyle(el);
        return { width: s.width, overflowWrap: s.overflowWrap, wordBreak: s.wordBreak };
      }).catch(() => null);
      if (overflow && overflow.wordBreak === 'normal' && overflow.overflowWrap === 'normal') {
        logBug(
          'B-UI-001',
          'Lange REQ-Titel brechen das Sidebar-Layout',
          `overflow-wrap=${overflow.overflowWrap}, word-break=${overflow.wordBreak}, width=${overflow.width}`
        );
      }
    }
  });

  // ===========================================================================
  // PHASE 2 — Traceability über UI
  // ===========================================================================
  test('Phase 2a: derives-from Link zwischen Requirements über UI', async ({ page }) => {
    const fromId = ids.requirementIds['L1-FUNC'];
    const toId = ids.requirementIds['L2-CTRL-001'];
    if (!fromId || !toId) {
      test.skip(true, 'IDs fehlen — Phase 1b fehlgeschlagen');
      return;
    }
    await createTraceLinkViaUI(page, fromId, toId, 'derives-from');
    await page.goto(`${FRONTEND_URL}/requirements/${fromId}`);
    await expect(page.locator('[data-testid="req-tracelink-panel"]')).toBeVisible({ timeout: 8000 });
  });

  test('Phase 2b: Requirement → Architektur allocated-to Links über UI', async ({ page }) => {
    const archId = ids.architectureIds['A-HEAT'];
    const reqId = ids.requirementIds['L1-PERF'];
    if (!archId || !reqId) {
      test.skip(true, 'IDs fehlen — Phase 1 fehlgeschlagen');
      return;
    }
    // link-types catalog migration (2026-09): 'satisfies' (ArchitectureElement
    // -> Requirement) was retired and folded into 'allocated-to', with the
    // endpoints swapped (Requirement -> ArchitectureElement) — see Task 17 of
    // docs/superpowers/plans/2026-09-03-traceability-semantik.md. Created from
    // the requirement side now, not the architecture side.
    await createTraceLinkViaUI(page, reqId, archId, 'allocated-to');
    await page.goto(`${FRONTEND_URL}/architecture/${archId}`);
    // Renamed to arch-linked-reqs-panel; link items carry a per-type badge
    // testid (trace-type-<linkType>), not a generic "-item" wrapper.
    await expect(page.locator('[data-testid="arch-linked-reqs-panel"]')).toBeVisible({ timeout: 8000 });
    await expect(page.locator('[data-testid="trace-type-allocated-to"]')).toBeVisible({ timeout: 8000 });
  });

  // ===========================================================================
  // PHASE 3 — ICDs mit Versionierung über UI
  // ===========================================================================
  test('Phase 3a: ICD-Create-Form hat source/target Selects mit Arch-Elementen', async ({ page }) => {
    test.setTimeout(15_000);
    const ctrlId = ids.architectureIds['A-CTRL'];
    if (!ctrlId) {
      test.skip(true, 'Architektur-IDs fehlen');
      return;
    }
    await page.goto(`${FRONTEND_URL}/icds`);
    await page.locator('[data-testid="create-icd-btn"]').click();
    await page.locator('[data-testid="create-icd-form"]').waitFor({ timeout: 6000 });
    const sourceOptions = await page.locator('[data-testid="icd-source-select"] option').count();
    if (sourceOptions < 2) {
      logBug(
        'B-ICD-003',
        'ICD source-select hat zu wenige Optionen',
        `Erwartet ≥ 2 (placeholder + ≥1 arch), gefunden: ${sourceOptions}`
      );
    }
    const trySource = await page.locator('[data-testid="icd-source-select"]')
      .selectOption(ctrlId, { timeout: 3000 })
      .then(() => true)
      .catch(() => false);
    if (!trySource) {
      const optionTexts = await page.locator('[data-testid="icd-source-select"] option')
        .allTextContents({ timeout: 2000 });
      logBug(
        'B-ICD-004',
        'ICD source-select enthält nicht die Arch-Element-IDs',
        `Versucht: ${ctrlId.slice(0, 8)}…, Optionen: ${optionTexts.slice(0, 5).join(', ')}`
      );
    }
    const list = page.locator('[data-testid="icds-list"], [data-testid="icds-empty"]');
    await expect(list.first()).toBeVisible({ timeout: 6000 });
  });

  test('Phase 3b: ICD-View rendert (Liste oder Empty-State)', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/icds`);
    await expect(page.locator('[data-testid="icd-view"]')).toBeVisible({ timeout: 10000 });
    await Promise.race([
      expect(page.locator('[data-testid="icds-list"]')).toBeVisible({ timeout: 6000 }).catch(() => null),
      expect(page.locator('[data-testid="icds-empty"]')).toBeVisible({ timeout: 6000 }).catch(() => null),
    ]);
  });

  test('Phase 3c: ICD zwischen Arch-Elementen über UI anlegen', async ({ page }) => {
    const sourceId = ids.architectureIds['A-CTRL'];
    const targetId = ids.architectureIds['A-SENSOR-T'];
    if (!sourceId || !targetId) {
      test.skip(true, 'Architektur-IDs fehlen');
      return;
    }
    const icdId = await createIcdViaUI(page, {
      name: 'WK-ICD-001: MCU ↔ Temperatursensor',
      sourceArchId: sourceId,
      targetArchId: targetId,
      // icd-interface-type-select is a fixed enum (provides/requires/
      // event-in/event-out/data/control); ADC voltage reading is a data feed.
      interfaceType: 'data',
      contract: 'ADC1_IN1 liest NTC-Spannung; Update-Rate ≥ 1 Hz.',
      direction: 'unidirectional',
    });
    // Issue #947: ID festhalten, damit `cleanupViaAPI` das ICD wirklich löscht
    // (der Helper gab vorher `void` zurück → `ids.icdIds` blieb leer) und die
    // Assertion auf *dieses* ICD geht statt auf "irgendeine Zeile in der Liste".
    ids.icdIds.push(icdId);
    await page.goto(`${FRONTEND_URL}/icds`);
    await expect(page.getByTestId(`icd-item-${icdId}`)).toBeVisible({ timeout: 10000 });
  });

  // ===========================================================================
  // PHASE 4 — Diagramme über UI
  // ===========================================================================
  //
  // Issue #947: alle vier Phase-4-Tests adressieren ihr Diagramm ab jetzt über
  // die von `createDiagramViaUI` zurückgegebene ID (`diagram-item-<id>`) statt
  // über den Namen mit `.first()`. Feste Namen + `.first()` treffen in einem
  // Workspace, in dem derselbe Lauf bzw. ein früherer Lauf mehrere Diagramme
  // hinterlässt, irgendeinen Treffer — die Assertion war damit nicht an *dieses*
  // Diagramm gebunden.
  test('Phase 4a: Block-Diagramm Wasserkessel über UI', async ({ page }) => {
    const id = await createDiagramViaUI(page, {
      name: 'WK-Block-001: Wasserkessel Top-Level',
      diagramType: 'block',
      payloadFormat: 'mermaid',
      description: 'Übersicht der Hauptkomponenten',
      content: `graph LR
  A[Stromversorgung] --> B[Heizelement]
  B --> C[Wasserbehälter]
  D[Steuerung MCU] --> B
  D --> E[LED-Modul]
  D --> F[Safety-IF]
  F --> D`,
    });
    ids.diagramIds['BLOCK'] = id;
    await page.goto(`${FRONTEND_URL}/diagrams`);
    await expect(page.getByTestId(`diagram-item-${id}`)).toBeVisible();
  });

  test('Phase 4b: Context-Diagramm Anwender-Wasserkasser über UI', async ({ page }) => {
    const id = await createDiagramViaUI(page, {
      name: 'WK-Context-001: User-System',
      diagramType: 'context',
      payloadFormat: 'mermaid',
      description: 'Anwender im Kontext',
      content: `graph TD
  User((Anwender))
  WK[Wasserkessel]
  Power[Stromnetz]
  User -->|füllt Wasser ein| WK
  User -->|stellt an| WK
  WK -->|kocht| User
  Power -->|230 V| WK`,
    });
    ids.diagramIds['CONTEXT'] = id;
    await page.goto(`${FRONTEND_URL}/diagrams`);
    await expect(page.getByTestId(`diagram-item-${id}`)).toBeVisible();
  });

  test('Phase 4c: Flow-Diagramm State-Machine über UI', async ({ page }) => {
    test.setTimeout(45_000);
    const id = await createDiagramViaUI(page, {
      name: 'WK-Flow-001: State Machine',
      diagramType: 'flow',
      payloadFormat: 'mermaid',
      description: 'Zustandsmaschine',
      content: `graph LR\n  A[Idle] --> B[Heating]\n  B --> C[Done]\n  B --> D[Error]\n  C --> A\n  D --> A`,
    });
    ids.diagramIds['FLOW'] = id;
    // Deterministische Zielwahl: die Zeile des *gerade erzeugten* Diagramms,
    // aufgelöst über seine ID — keine Namenssuche, kein `.first()`.
    await page.goto(`${FRONTEND_URL}/diagrams`);
    await expect(page.getByTestId(`diagram-item-${id}`)).toBeVisible({ timeout: 10000 });
  });

  test('Phase 4d: Diagramm editieren — erzeugt das eine neue Version?', async ({ page }) => {
    const diagramId = ids.diagramIds['BLOCK'];
    if (!diagramId) {
      test.skip(true, 'Diagramm-ID fehlt — Phase 4a fehlgeschlagen');
      return;
    }

    // Direkt über die ID ins Detail — kein Suchfeld, kein `.first()`.
    await page.goto(`${FRONTEND_URL}/diagrams`);
    await page.getByTestId(`diagram-item-${diagramId}`).click();

    // Issue #947: Version NICHT mehr über `page.content().includes('v2')`
    // prüfen. Der Detail-Pane rendert den Quellcode (diagram-source-preview),
    // und der Test schreibt selbst "Heizelement v2" hinein — der Substring war
    // also immer wahr und der Check konnte nie anschlagen (false negative).
    // Gelesen wird jetzt das Versions-Label selbst.
    //
    // Prefix-Match statt `getByTestId` (das exakt matcht): das Label ist heute
    // ungescoped, aber ein Suffix je Diagramm-ID ist der Haus-Stil
    // (`diagram-item-<id>`, `artifact-field-cell-<name>`), also bleibt der
    // Locator auch dann korrekt, wenn das Label später gescoped wird.
    const versionLabel = page.locator('[data-testid^="diagram-version-label"]');
    await expect(versionLabel).toHaveCount(1, { timeout: 10000 });
    const versionBefore = (await versionLabel.innerText()).trim();

    await expect(page.locator('[data-testid="diagram-open-editor-btn"]')).toBeVisible();
    await page.locator('[data-testid="diagram-open-editor-btn"]').click();
    await expect(page.locator('[data-testid="mermaid-editor"]')).toBeVisible({ timeout: 10000 });

    const newContent = `graph LR
  A[Stromversorgung] --> B[Heizelement]
  B --> C[Wasserbehälter]`;
    // CodeMirror renders a contenteditable div, not a textarea — select-all
    // and retype (same helper shape as tests/mermaid-diagram.spec.ts).
    const cmContent = page.locator('[data-testid="mermaid-code-editor"] .cm-content');
    await cmContent.waitFor({ state: 'visible', timeout: 10000 });
    await cmContent.click();
    await page.keyboard.press('Control+a');
    await page.keyboard.press('Delete');
    await page.keyboard.type(newContent, { delay: 10 });

    // The fullscreen editor owns its own state and persists the source through
    // PUT /diagrams/{id}/mermaid-source/ (diagramsApi.saveMermaidSource) — not
    // the PATCH the inline form used to send. Click before the 2s auto-save
    // timer fires, otherwise the manual save is a no-op (isDirty already false)
    // and nothing further would be sent.
    await Promise.all([
      page.waitForResponse(
        (resp) =>
          /\/diagrams\/[^/]+\/mermaid-source\/?($|\?)/.test(resp.url()) &&
          resp.request().method() === 'PUT' &&
          resp.status() < 400
      ),
      page.locator('[data-testid="mermaid-save-btn"]').click(),
    ]);

    // Back to the detail pane to read the (possibly bumped) version label.
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}`);
    await expect(versionLabel).toHaveCount(1, { timeout: 10000 });
    const versionAfter = (await versionLabel.innerText()).trim();

    const bumped = versionAfter !== versionBefore;
    if (!bumped) {
      logBug(
        'B-DIAG-001',
        'Diagramm-Edit erzeugt KEINE neue Version (REQ-L1-029 Immutability Bruch)',
        `Nach dem Edit sollte eine neue Version entstehen, der Quellcode ist aber direkt ` +
          `überschrieben. Versions-Label vorher: "${versionBefore}", nachher: "${versionAfter}" ` +
          `(diagram id ${diagramId}).`
      );
    }
  });

  // ===========================================================================
  // PHASE 5 — Baselines über UI (mehrere)
  // ===========================================================================
  test('Phase 5a: Baseline RC1 (project scope) über UI', async ({ page }) => {
    // This scenario deliberately builds up the SE graph in stages, so by
    // this phase several requirements are still missing
    // derives-from/verifies/allocated-to links — the SE-Auditor gate
    // (GH-490/GH-513) reliably reports BLOCKER findings and rejects a plain
    // project-scope create. allowGateOverride mirrors what an admin
    // snapshotting a WIP state would actually do (see wk-helpers.ts);
    // without it the gate block is a loud failure, not a silent no-op.
    await createBaselineViaUI(page, { scope: 'project', allowGateOverride: true });
    await page.goto(`${FRONTEND_URL}/baselines`);
    await expect(page.locator('[data-testid="baseline-list"]')).toBeVisible({ timeout: 10000 });
  });

  test('Phase 5b: Baseline doc1 (document scope) über UI', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/baselines`);
    // Task 5.2: creation lives in the PageHeader overflow menu (same as
    // createBaselineViaUI in wk-helpers.ts).
    await expect(page.locator('[role="status"]')).not.toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="page-header-overflow-trigger"]').click();
    await page.locator('[data-testid="create-baseline-btn"]').click();
    await page.locator('[data-testid="create-baseline-form"]').waitFor({ timeout: 6000 });
    await page.locator('[data-testid="baseline-scope-document"]').check();
    const artifactSelect = page.locator('[data-testid="baseline-artifact-select"]');
    await expect(artifactSelect).toBeVisible({ timeout: 5000 });
    const options = await artifactSelect.locator('option').count();
    if (options > 1) {
      const value = await artifactSelect.locator('option').nth(1).getAttribute('value');
      if (value) {
        // See the allowGateOverride note in Phase 5a — the same partially-
        // linked WIP state can trip the SE-Auditor gate for document scope too.
        await createBaselineViaUI(page, { scope: 'document', artifactId: value, allowGateOverride: true });
      }
    }
    await page.goto(`${FRONTEND_URL}/baselines`);
    await expect(page.locator('[data-testid="baseline-list"]')).toBeVisible({ timeout: 10000 });
  });

  // ===========================================================================
  // PHASE 6 — Issues / Risks / ADRs / TestCases / TestRuns über UI
  // ===========================================================================
  test('Phase 6a: Issue über UI anlegen', async ({ page }) => {
    const id = await createIssueViaUI(page, {
      title: 'WK-Issue-001: Trockenlauf-Test sporadisch fehlerhaft',
      description: 'In 3 von 10 Versuchen löst die Abschaltung zu spät aus.',
      severity: 'high',
      status: 'Open',
    });
    ids.issueIds.push(id);
    expect(id).toMatch(/^[0-9a-f-]+$/);
  });

  test('Phase 6b: Risk über UI anlegen', async ({ page }) => {
    const id = await createRiskViaUI(page, {
      title: 'WK-Risk-001: Thermosicherung fällt bei 130 °C aus',
      severity: 'high',
      probability: 'low',
      impact: 'high',
    });
    ids.riskIds.push(id);
    expect(id).toMatch(/^[0-9a-f-]+$/);
  });

  test('Phase 6c: ADR über UI anlegen', async ({ page }) => {
    const id = await createAdrViaUI(page, {
      title: 'WK-ADR-001: STM32F030 als MCU gewählt',
      context: 'Wir brauchen eine MCU mit ADC, GPIO und Watchdog unter 2 €/Stk.',
      decision: 'Kosten, Verfügbarkeit, ARM-Cortex-M0 Core. Lock-in auf STM32-Plattform. Toolchain STM32CubeIDE.',
      status: 'Approved',
    });
    ids.adrIds.push(id);
    expect(id).toMatch(/^[0-9a-f-]+$/);
  });

  test('Phase 6d: TestCases über UI anlegen', async ({ page }) => {
    for (const [k, title] of [
      ['TC-001', 'WK-TC-001: 1 L kocht in ≤ 3 Min'],
      ['TC-002', 'WK-TC-002: Trockenlauf-Abschaltung < 5 s'],
      ['TC-003', 'WK-TC-003: LED folgt Heizzyklus'],
      ['TC-004', 'WK-TC-004: Lift-Off deaktiviert Heizung'],
    ] as const) {
      const id = await createTestCaseViaUI(page, { title, status: 'active', priority: 'high' });
      ids.testCaseIds[k] = id;
    }
    expect(Object.keys(ids.testCaseIds).length).toBe(4);
  });

  // ===========================================================================
  // PHASE 6e — 4 TestRuns mit 4-Phase Lifecycle (UI)
  // ===========================================================================
  test('Phase 6e: 4 TestRuns mit Lifecycle open → in_progress → closed/failed über UI', async ({ page }) => {
    test.setTimeout(90_000);
    const testCases = Object.values(ids.testCaseIds);
    if (testCases.length < 4) {
      test.skip(true, 'TestCases fehlen — Phase 6d fehlgeschlagen');
      return;
    }

    const runs = [
      { key: 'SMOKE', name: 'WK-Run-Smoke', fail: false },
      { key: 'REGRESSION', name: 'WK-Run-Regression', fail: false },
      { key: 'ABNAHME', name: 'WK-Run-Abnahme RC1', fail: true },
      { key: 'HOTFIX', name: 'WK-Run-Hotfix', fail: true },
    ] as const;

    for (const run of runs) {
      const runId = await createTestRunViaUI(page, { name: run.name, status: 'in_progress' });
      ids.testRunIds[run.key] = runId;

      // Seed Results (API) — UI hat keine Result-Eingabeform
      for (let i = 0; i < testCases.length; i++) {
        const status = run.fail && i === 0 ? 'failed' : 'passed';
        await seedTestRunResult(token, runId, testCases[i], status, status === 'failed' ? 'Trockenlauf zu langsam' : 'OK');
      }

      // Close via UI und Status-Badge prüfen
      await transitionTestRunViaUI(page, runId, 'in_progress', run.fail ? 'failed' : 'passed');
      await page.goto(`${FRONTEND_URL}/test-runs`);
      const item = page.locator(`[data-testid="testrun-item-${runId}"]`);
      await expect(item).toBeVisible({ timeout: 8000 });
      // Scoped to the row's own StatusBadge (shared/StatusBadge.tsx,
      // data-testid="status-badge") instead of "any <span> inside the row
      // whose text contains the word" (issue #947).
      await expect(item.getByTestId('status-badge')).toHaveText(
        run.fail ? /failed/i : /passed/i,
        { timeout: 5000 }
      );
    }

    // Aggregate-Check: jeder Run zeigt im Detail das Result-Summary.
    // Prefix-Match: die Summary-Cards sind per artifact gescoped
    // (`testrun-result-summary-<runId>`), getByTestId matcht exakt.
    for (const runId of Object.values(ids.testRunIds)) {
      await page.goto(`${FRONTEND_URL}/test-runs`);
      await page.locator(`[data-testid="testrun-item-${runId}"]`).click();
      await expect(
        page.locator('[data-testid^="testrun-result-summary"]')
      ).toBeVisible({ timeout: 8000 });
    }
  });

  // ===========================================================================
  // PHASE 7a — Globale Suche
  // ===========================================================================
  test('Phase 7a: Globale Suche findet WK-Items', async ({ page }) => {
    const resultCount = await globalSearchAndClick(page, 'WK-L1');
    if (resultCount === 0) {
      logBug(
        'B-SRCH-001',
        'Globale Suche findet keine WK-Requirements',
        'Suche nach "WK-L1" lieferte 0 Resultate, obwohl 5+ WK-L1-Requirements existieren.'
      );
    }
  });

  // ===========================================================================
  // PHASE 7b — Metrics Dashboard
  // ===========================================================================
  test('Phase 7b: Metrics Dashboard rendert 5 Tiles (Coverage/Volatility/...)', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/metrics`);
    await expect(page.locator('[data-testid="metrics-dashboard"]')).toBeVisible({ timeout: 10000 });
    for (const name of ['coverage', 'volatility', 'workflowGap', 'openRisks', 'openRisksCritical']) {
      const tile = page.locator(`[data-testid="metric-tile-${name}"]`);
      await expect(tile).toBeVisible({ timeout: 5000 });
    }
  });

  // ===========================================================================
  // PHASE 7c — Dashboard-Terminologie-Check (REQ-L2-RF-008)
  // ===========================================================================
  test('Phase 7c: Dashboard rendert mit Workspace-Liste oder Empty-State', async ({ page }) => {
    test.setTimeout(30_000);
    await page.goto(`${FRONTEND_URL}/`);
    await page.waitForLoadState('networkidle');
    // Issue #947: beide Zustände haben einen eigenen data-testid
    // (DashboardViews.tsx) — der frühere Text-Regex ('no workspace|kein
    // workspace|empty|leer') traf auch jeden beliebigen Fließtext, der eines
    // dieser Wörter enthielt.
    const list = page.getByTestId('workspace-list');
    const empty = page.getByTestId('workspace-list-empty');
    await Promise.race([
      expect(list).toBeVisible({ timeout: 10000 }).catch(() => null),
      expect(empty).toBeVisible({ timeout: 10000 }).catch(() => null),
    ]);
    const cards = page.getByTestId('workspace-card');
    const count = await cards.count();
    if (count > 0) {
      const firstCard = cards.first();
      const text = await firstCard.innerText();
      if (!/extended|se|engineer|standard|minimal|dev|mode|preset/i.test(text)) {
        logBug(
          'B-UI-007',
          'Workspace-Karte zeigt kein Preset/Modus-Label',
          `Karten-Text enthält keinen Terminologie-Indikator: "${text.slice(0, 100)}"`
        );
      }
    }
  });

  // ===========================================================================
  // PHASE 7d — CSV-Import UI rendert (kein Upload-Test, nur Render-Check)
  // ===========================================================================
  test('Phase 7d: CSV-Import-Seite rendert mit Entity-Type-Selector', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/import`);
    await expect(page.locator('[data-testid="csv-import-page"]')).toBeVisible({ timeout: 10000 });
    for (const t of ['Requirement', 'ArchitectureElement', 'TestCase']) {
      await expect(page.locator(`[data-testid="entity-type-${t}"]`)).toBeVisible();
    }
    await expect(page.locator('[data-testid="csv-drop-zone"]')).toBeVisible();
  });
});
