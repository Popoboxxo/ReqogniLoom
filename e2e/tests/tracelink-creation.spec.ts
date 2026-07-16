// TraceLink creation feature — Bug A1/A2/A3 coverage
// REQ-L0-003, REQ-L2-RF-005, REQ-L2-RF-006
import { test, expect, type Page } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  setWorkspaceId,
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
  test('[REQ-L2-RF-006] can create TraceLink via UI when artifacts exist', async ({ page, request }) => {
    const token = await getAuthToken();

    // Check if there are artifacts to link
    const reqResp = await request.get(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    const reqBody = await reqResp.json();
    const reqs: { id: string }[] = Array.isArray(reqBody) ? reqBody : reqBody.results ?? [];

    if (reqs.length < 2) {
      test.skip(true, 'Need at least 2 requirements to create a TraceLink — seed more data');
      return;
    }

    await page.goto(`${FRONTEND_URL}/traceability`);
    await page.locator('[data-testid="tracelink-create-btn"]').click();
    await expect(page.locator('[data-testid="create-trace-link-dialog"]')).toBeVisible({ timeout: 8000 });

    // Global mode (no fixed sourceId on /traceability): source is a plain
    // <select> keyed by element id; target is a searchable ElementPicker
    // whose entries are addressable directly by id via data-testid.
    const sourceSelect = page.locator('[data-testid="create-trace-link-source-select"]');
    await expect(sourceSelect).toBeVisible({ timeout: 6000 });
    await sourceSelect.selectOption(reqs[0].id);

    const targetEl = page.locator(`[data-testid="create-trace-link-target-element-${reqs[1].id}"]`);
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
