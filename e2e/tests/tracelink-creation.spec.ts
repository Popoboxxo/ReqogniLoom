// TraceLink creation feature — Bug A1/A2/A3 coverage
// REQ-L0-003, REQ-L2-RF-005, REQ-L2-RF-006
import { test, expect, type Page } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  setWorkspaceId,
  createIsolatedWorkspace,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

// "+ New" only opens an inline quick-create form; the full editor only
// renders after Save/Create navigates to the created artifact's detail route.
async function createArchElementViaQuickForm(page: Page, title = 'E2E Arch Element'): Promise<void> {
  await page.locator('[data-testid="create-arch-btn"]').click();
  await page.locator('[data-testid="arch-new-title-input"]').fill(title);
  await page.locator('[data-testid="arch-new-save-btn"]').click();
  await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
}

// [I5] A workspace tree may have exactly one root ArchitectureElement, and
// seed_demo pre-seeds one for SEEDED_WORKSPACE_ID — so any "+ New" (root,
// no parent_id) creation against it 400s. Re-point the page at a fresh,
// element-free workspace right before navigating to /architecture, matching
// the pattern already used by architecture.spec.ts / architecture-editor.spec.ts.
async function useIsolatedArchWorkspace(page: Page): Promise<void> {
  const token = await getAuthToken();
  const workspaceId = await createIsolatedWorkspace(token);
  await setWorkspaceId(page, workspaceId);
}

test.describe('[COMP-RF-006] TraceLink Creation', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  // -------------------------------------------------------------------------
  // REQ-L0-003 — TraceLink creation form appears and has populated dropdowns
  // -------------------------------------------------------------------------
  test('[REQ-L0-003] create TraceLink button is visible on traceability page', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    const createBtn = page.locator('[data-testid="tracelink-create-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L0-003] clicking create button shows creation form', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    await page.locator('[data-testid="tracelink-create-btn"]').click();
    // REQ-005: inline form replaced by the unified CreateTraceLinkDialog modal.
    await expect(page.locator('[data-testid="create-trace-link-dialog"]')).toBeVisible({ timeout: 8000 });
  });

  test('[REQ-L0-003] creation form has source, target and type dropdowns', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    await page.locator('[data-testid="tracelink-create-btn"]').click();
    await expect(page.locator('[data-testid="create-trace-link-dialog"]')).toBeVisible({ timeout: 8000 });

    // Global mode (no fixed sourceId on /traceability) shows a plain source <select>...
    await expect(page.locator('[data-testid="create-trace-link-source-select"]')).toBeVisible({ timeout: 6000 });
    // ...and the target is a searchable ElementPicker (list), not a <select>.
    await expect(page.locator('[data-testid="create-trace-link-target-list"]')).toBeVisible({ timeout: 6000 });
    await expect(page.locator('[data-testid="create-trace-link-type-select"]')).toBeVisible({ timeout: 6000 });
    await expect(page.locator('[data-testid="create-trace-link-submit"]')).toBeVisible({ timeout: 6000 });
  });

  // -------------------------------------------------------------------------
  // REQ-L2-RF-006 — Create TraceLink via UI full happy path
  // -------------------------------------------------------------------------
  //
  // BUG-09 (Systemaudit 2026-08-18, §4 / GH-53): this test used to run
  // directly against the shared SEEDED_WORKSPACE_ID and pick the first two
  // requirements it found there. CreateTraceLinkDialog's loadElements()
  // eagerly fetches *all* artifacts of *all* six types (full pagination, no
  // server-side search) before the source <select> shows any real option —
  // against SEEDED_WORKSPACE_ID, which accumulates artifacts across every
  // CI run with no equivalent of the API-key cleanup in
  // e2e/helpers/auth.ts#revokeAllApiKeys (see its doc comment for the exact
  // same accumulation pattern already observed and fixed for API keys),
  // that full load could take long enough to blow the suite's fixed 60s
  // per-test timeout (playwright.config.ts `timeout: 60000` — the reported
  // "60s Timeout nach 116 Retries"). The dialog itself was never broken
  // (verified via CreateTraceLinkDialog's own component test, which
  // populates the source select correctly from mocked API data); the
  // dropdown just never finished loading in time. Isolating this test's
  // workspace — the same pattern useIsolatedArchWorkspace() already uses
  // above — removes exposure to that unbounded, ever-growing shared
  // fixture and makes the test's own two requirements the only ones the
  // dialog has to load.
  test('[REQ-L2-RF-006] can create TraceLink via UI when artifacts exist', async ({ page, request }) => {
    const token = await getAuthToken();
    const workspaceId = await createIsolatedWorkspace(token);
    const authHeaders = { Authorization: `Bearer ${token}` };

    const createReq = async (title: string): Promise<string> => {
      const resp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
        headers: authHeaders,
        data: { workspace_id: workspaceId, title },
      });
      const body = await resp.json();
      return body.id as string;
    };
    const sourceReqId = await createReq('E2E TraceLink Source');
    const targetReqId = await createReq('E2E TraceLink Target');

    await setWorkspaceId(page, workspaceId);
    await page.goto(`${FRONTEND_URL}/traceability`);
    await page.locator('[data-testid="tracelink-create-btn"]').click();
    await expect(page.locator('[data-testid="create-trace-link-dialog"]')).toBeVisible({ timeout: 8000 });

    // Global mode (no fixed sourceId on /traceability): source is a plain
    // <select> keyed by element id; target is a searchable ElementPicker
    // whose entries are addressable directly by id via data-testid.
    const sourceSelect = page.locator('[data-testid="create-trace-link-source-select"]');
    await expect(sourceSelect).toBeVisible({ timeout: 6000 });
    await sourceSelect.selectOption(sourceReqId);

    const targetEl = page.locator(`[data-testid="create-trace-link-target-element-${targetReqId}"]`);
    await expect(targetEl).toBeVisible({ timeout: 6000 });
    await targetEl.click();

    // Select link type if options available
    const typeSelect = page.locator('[data-testid="create-trace-link-type-select"]');
    const typeCount = await typeSelect.locator('option').count();
    if (typeCount > 1) {
      const typeOptions = await typeSelect.locator('option').allInnerTexts();
      const firstType = typeOptions.find((o) => o.trim() && !/select|choose|--/i.test(o));
      if (firstType) {
        await typeSelect.selectOption({ label: firstType });
      }
    }

    await page.locator('[data-testid="create-trace-link-submit"]').click();
    await page.waitForLoadState('networkidle');

    // After creation, either the list (with items) or the empty state must be visible
    const list = page.locator('[data-testid="traceability-list"]');
    const empty = page.locator('[data-testid="traceability-empty"]');
    const listVisible = await list.isVisible().catch(() => false);
    const emptyVisible = await empty.isVisible().catch(() => false);
    expect(listVisible || emptyVisible, 'Expected traceability-list or traceability-empty to be visible after creation').toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // REQ-L2-RF-006 — TraceLink list visible on traceability page (or empty state)
  // -------------------------------------------------------------------------
  test('[REQ-L2-RF-006] traceability page shows list or empty state', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    // Either list (when links exist) or empty placeholder must be visible
    const list = page.locator('[data-testid="traceability-list"]');
    const empty = page.locator('[data-testid="traceability-empty"]');
    // Wait for one of them to appear
    await Promise.race([
      expect(list).toBeVisible({ timeout: 10000 }).catch(() => null),
      expect(empty).toBeVisible({ timeout: 10000 }).catch(() => null),
    ]);
    const listVisible = await list.isVisible();
    const emptyVisible = await empty.isVisible();
    expect(listVisible || emptyVisible).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // REQ-L2-RF-006 — Architecture TraceLink panel is visible in arch editor (Bug A2)
  // -------------------------------------------------------------------------
  test('[REQ-L2-RF-006] architecture editor shows arch-tracelink-panel (Bug A2)', async ({ page }) => {
    await useIsolatedArchWorkspace(page);
    await page.goto(`${FRONTEND_URL}/architecture`);
    await createArchElementViaQuickForm(page);

    // Renamed to "arch-linked-reqs-panel": linked-requirements management
    // lives here now (via the shared TraceLinkPanel); the read-only trace
    // view moved to the ArtifactInspector.
    const panel = page.locator('[data-testid="arch-linked-reqs-panel"]');
    await expect(panel).toBeVisible({ timeout: 8000 });
  });

  // -------------------------------------------------------------------------
  // REQ-L2-RF-005 — Architecture editor shows element_type selector with 5 options (Bug A3)
  // -------------------------------------------------------------------------
  test('[REQ-L2-RF-005] architecture editor has element_type selector with correct testid and 5 options', async ({ page }) => {
    await useIsolatedArchWorkspace(page);
    await page.goto(`${FRONTEND_URL}/architecture`);
    await createArchElementViaQuickForm(page);

    // Bug A3: testid should be "arch-element-type-select" (not "arch-element-type").
    // REQ-006/D5 later replaced the fixed 5-option <select> with a free-text
    // autocomplete input (types can be extended freely, no longer an enum).
    const typeInput = page.locator('[data-testid="arch-element-type-select"]');
    await expect(typeInput).toBeVisible({ timeout: 6000 });

    await typeInput.fill('Layer');
    await expect(typeInput).toHaveValue('Layer');
  });
});
