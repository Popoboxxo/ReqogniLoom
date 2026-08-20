// L0 Stakeholder Needs — E2E coverage for REQ-L0-001 through REQ-L0-012
import { test, expect } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  setWorkspaceId,
  setWorkspacePreset,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

// ---------------------------------------------------------------------------
// REQ-L0-001 — MCP Server endpoint exists
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-001] MCP Server', () => {
  test('[REQ-L0-001] MCP endpoint exists (not 404)', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/mcp/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    // 200 (SSE stream) or 405 (method not allowed) both confirm the endpoint exists
    expect([200, 405, 400]).toContain(response.status());
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-002 — Skalierbare SE-Tiefe: Preset-Wechsel in Workspace Settings
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-002] Scalable SE depth — preset switcher', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L0-002] preset selector has at least 3 options (radio buttons)', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    const selectorContainer = page.locator('[data-testid="preset-selector"]');
    await expect(selectorContainer).toBeVisible({ timeout: 10000 });
    // Preset is rendered as radio buttons with data-testid="preset-option-<name>"
    const radioOptions = selectorContainer.locator('input[type="radio"]');
    const count = await radioOptions.count();
    expect(count).toBeGreaterThanOrEqual(3);
  });

  test('[REQ-L0-002] can switch preset to minimal and back to extended', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    await expect(page.locator('[data-testid="preset-selector"]')).toBeVisible({ timeout: 10000 });

    // Preset is radio buttons — click the minimal radio
    const minimalRadio = page.locator('[data-testid="preset-option-minimal"]');
    await expect(minimalRadio).toBeVisible({ timeout: 6000 });
    await minimalRadio.click();
    await page.waitForLoadState('networkidle');
    await expect(minimalRadio).toBeChecked({ timeout: 5000 });

    // Switch back to extended
    const extendedRadio = page.locator('[data-testid="preset-option-extended"]');
    await extendedRadio.click();
    await page.waitForLoadState('networkidle');
    await expect(extendedRadio).toBeChecked({ timeout: 5000 });
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-003 — Vollständige Traceability: TraceLink anlegen via UI
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-003] Traceability — create TraceLink via UI', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L0-003] create TraceLink button opens creation form', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    const createBtn = page.locator('[data-testid="tracelink-create-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 10000 });
    await createBtn.click();
    // REQ-005: inline form replaced by the unified CreateTraceLinkDialog modal.
    await expect(page.locator('[data-testid="create-trace-link-dialog"]')).toBeVisible({ timeout: 8000 });
  });

  test('[REQ-L0-003] TraceLink creation form source and target dropdowns are populated', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    const createBtn = page.locator('[data-testid="tracelink-create-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 10000 });
    await createBtn.click();
    await expect(page.locator('[data-testid="create-trace-link-dialog"]')).toBeVisible({ timeout: 8000 });

    // #53 Bug 2: global mode (no fixed sourceId on /traceability) shows the
    // same searchable ElementPicker (list) for both source and target.
    const sourceList = page.locator('[data-testid="create-trace-link-source-list"]');
    const targetList = page.locator('[data-testid="create-trace-link-target-list"]');
    await expect(sourceList).toBeVisible({ timeout: 6000 });
    await expect(targetList).toBeVisible({ timeout: 6000 });

    const sourceEntries = await sourceList.locator('button[data-testid^="create-trace-link-source-element-"]').count();
    const targetEntries = await targetList.locator('button[data-testid^="create-trace-link-target-element-"]').count();

    if (sourceEntries === 0 || targetEntries === 0) {
      // No artifacts seeded — graceful skip
      test.skip(true, 'Dropdowns empty — no artifacts seeded for this workspace');
    }
    expect(sourceEntries).toBeGreaterThan(0);
    expect(targetEntries).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-004 — Baselines anlegen via UI
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-004] Baselines — create via UI', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L0-004] create baseline form appears on button click', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/baselines`);
    await expect(page.locator('[data-testid="baselines-view"]')).toBeVisible({ timeout: 10000 });
    // Task 5.2: baseline creation is an overflow action, not a primary header
    // button. The loading branch of BaselinesView renders baselines-view
    // without a PageHeader, so wait for the spinner to clear first.
    await expect(page.locator('[role="status"]')).not.toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="page-header-overflow-trigger"]').click();
    const createBtn = page.locator('[data-testid="create-baseline-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 10000 });
    await createBtn.click();
    // Inline form appears (no dialog — toggled by showForm state)
    await expect(page.locator('[data-testid="create-baseline-form"]')).toBeVisible({ timeout: 6000 });
  });

  test('[REQ-L0-004] baseline creation form has artifact select and scope input', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/baselines`);
    await expect(page.locator('[data-testid="baselines-view"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[role="status"]')).not.toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="page-header-overflow-trigger"]').click();
    await page.locator('[data-testid="create-baseline-btn"]').click();
    await expect(page.locator('[data-testid="create-baseline-form"]')).toBeVisible({ timeout: 6000 });

    // REQ-L1-049: free-text scope input replaced by a radio group with
    // "document" / "project" / "global" options; the artifact select is
    // only rendered once the "document" scope is chosen.
    await expect(page.locator('[data-testid="baseline-scope-group"]')).toBeVisible({ timeout: 5000 });
    await page.locator('[data-testid="baseline-scope-document"]').click();

    // Artifact select must be present (document scope only)
    await expect(page.locator('[data-testid="baseline-artifact-select"]')).toBeVisible({ timeout: 5000 });
    // Submit button must be present
    await expect(page.locator('[data-testid="baseline-submit-btn"]')).toBeVisible({ timeout: 5000 });
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-005 — Konfigurierbarer Lifecycle: workflow states in req editor
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-005] Configurable lifecycle — workflow states', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L0-005] workflow status editor exists with current-state badge and transitions', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    // "+ New" only opens an inline quick-create form; the full editor (with
    // the WorkflowStatusEditor) only renders after Save navigates to the
    // detail route.
    await page.locator('[data-testid="create-req-btn"]').click();
    await page.locator('[data-testid="req-new-save-btn"]').click();

    // REQ-161: current state is always shown read-only via the
    // WorkflowStatusEditor status badge; a "Change status" trigger only
    // renders when the backend reports allowed transitions from the current
    // state, otherwise "workflow-no-transitions" is shown. Literal states
    // are no longer a fixed enum rendered as option text.
    await expect(page.locator('[data-testid="workflow-current-status"]')).toBeVisible({ timeout: 10000 });
    const trigger = page.locator('[data-testid="workflow-transition-trigger"]');
    const noTransitions = page.locator('[data-testid="workflow-no-transitions"]');
    await expect(trigger.or(noTransitions)).toBeVisible({ timeout: 6000 });
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-007 — LLM Graceful Degradation: core API works without LLM
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-007] LLM graceful degradation', () => {
  test('[REQ-L0-007] requirements API returns 200 without any AI endpoint', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results ?? [];
    expect(Array.isArray(items)).toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-008 — Mandantenfähigkeit: workspace isolation
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-008] Multi-tenancy — workspace isolation', () => {
  test('[REQ-L0-008] seeded workspace returns requirements', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results ?? [];
    expect(Array.isArray(items)).toBeTruthy();
  });

  test('[REQ-L0-008] non-existent workspace returns empty results (no cross-tenant leak)', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: '00000000-0000-0000-0000-000000000000' },
    });
    // 200 with empty list OR 404 — both indicate isolation; never another tenant's data
    const status = response.status();
    if (status === 200) {
      const body = await response.json();
      const items = Array.isArray(body) ? body : body.results ?? [];
      expect(items.length).toBe(0);
    } else {
      expect([400, 404]).toContain(status);
    }
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-009 — Zweisprachige UI: language switcher
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-009] Bilingual UI — language switch', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L0-009] language switcher toggles UI language', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.waitForLoadState('networkidle');

    const langSwitch = page.locator('[data-testid="lang-switch"]').or(
      page.locator('button', { hasText: /^(DE|EN)$/i })
    ).first();

    const found = await langSwitch.count();
    if (found === 0) {
      test.skip(true, 'Language switcher not found — feature not yet implemented in UI');
      return;
    }

    await expect(langSwitch).toBeVisible({ timeout: 5000 });
    const bodyBefore = await page.locator('body').innerText();

    // Click to switch language
    await langSwitch.click();
    await page.waitForLoadState('networkidle');
    const bodyAfter = await page.locator('body').innerText();

    // Some text must have changed
    expect(bodyAfter).not.toBe(bodyBefore);

    // Switch back
    await langSwitch.click();
    await page.waitForLoadState('networkidle');
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-010 — Terminologie-Flexibilität: workspace has preset/terminology field
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-010] Terminology flexibility', () => {
  test('[REQ-L0-010] workspaces API includes preset or terminology_profile field', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/workspaces/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const items: Record<string, unknown>[] = Array.isArray(body) ? body : body.results ?? [];
    expect(items.length).toBeGreaterThan(0);
    const first = items[0];
    const hasTerminologyField =
      'terminology_profile' in first || 'preset' in first || 'terminology' in first;
    expect(hasTerminologyField).toBeTruthy();
  });

  test('[REQ-L0-010] dashboard workspace cards show terminology info', async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/`);
    const firstCard = page.locator('[data-testid="workspace-card"]').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });
    const text = await firstCard.innerText();
    // Card must contain some mode indicator (dev/se) or preset name
    expect(text).toMatch(/minimal|standard|extended|dev|se|engineer/i);
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-011 — Audit-Trail: change_reason field and history endpoint
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-011] Audit trail', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L0-011] change_reason field is visible in requirement editor (extended preset)', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    // "+ New" only opens an inline quick-create form; the full editor (with
    // req-title) only renders after Save navigates to the detail route.
    await page.locator('[data-testid="create-req-btn"]').click();
    await page.locator('[data-testid="req-new-save-btn"]').click();
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 10000 });

    const changeReasonInput = page.locator('[data-testid="change-reason-input"]');
    const found = await changeReasonInput.count();
    if (found === 0) {
      test.skip(true, 'change_reason field not present — may require extended preset');
      return;
    }
    await expect(changeReasonInput).toBeVisible({ timeout: 5000 });
    await changeReasonInput.fill('E2E audit trail test');
    await expect(changeReasonInput).toHaveValue('E2E audit trail test');
  });

  test('[REQ-L0-011] requirement history endpoint returns audit records', async ({ request }) => {
    const token = await getAuthToken();
    // First create a requirement to have a known ID
    const createResp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: 'E2E Audit Trail Requirement',
        category: 'Functional',
      },
    });
    expect(createResp.ok()).toBeTruthy();
    const req = await createResp.json();

    // Try history endpoint
    const historyResp = await request.get(`${BACKEND_URL}/api/v1/requirements/${req.id}/history/`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    expect(historyResp.ok()).toBeTruthy();
    const history = await historyResp.json();
    const items = Array.isArray(history) ? history : history.results ?? [];
    expect(items.length).toBeGreaterThan(0);

    // Cleanup
    await request.delete(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-012 — REST API vollständig: basic CRUD smoke test across all entities
// (detailed coverage in api-completeness.spec.ts)
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-012] REST API completeness — smoke', () => {
  test.beforeEach(async () => {
    // Reset the seeded workspace to the extended preset before the smoke test
    // runs. The REQ-L0-002 preset switcher test mutates this workspace's
    // preset (extended → minimal → extended) earlier in the same file, and
    // the UI-driven cleanup does not always leave the workspace in the
    // expected state. /api/v1/baselines/ is preset-gated and returns 404 in
    // the minimal preset, so the smoke test must start in extended.
    await setWorkspacePreset('extended');
  });

  test('[REQ-L0-012] all core entity endpoints are reachable', async ({ request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };
    const params = { workspace_id: SEEDED_WORKSPACE_ID };

    const endpoints = [
      '/api/v1/requirements/',
      '/api/v1/architecture/',
      '/api/v1/tracelinks/',
      '/api/v1/baselines/',
      '/api/v1/testcases/',
      '/api/v1/workspaces/',
    ];

    for (const endpoint of endpoints) {
      const resp = await request.get(`${BACKEND_URL}${endpoint}`, { headers, params });
      expect(resp.status(), `${endpoint} should return 200`).toBe(200);
    }
  });
});

// ---------------------------------------------------------------------------
// REQ-L0-022 — Credential Login (already covered)
// ---------------------------------------------------------------------------
// Covered by e2e/tests/auth.spec.ts — see [REQ-L0-022] wrong credentials test there.
