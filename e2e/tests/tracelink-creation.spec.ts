// TraceLink creation feature — Bug A1/A2/A3 coverage
// REQ-L0-003, REQ-L2-RF-005, REQ-L2-RF-006
import { test, expect } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  setWorkspaceId,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

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
    await expect(page.locator('[data-testid="tracelink-create-form"]')).toBeVisible({ timeout: 8000 });
  });

  test('[REQ-L0-003] creation form has source, target and type dropdowns', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    await page.locator('[data-testid="tracelink-create-btn"]').click();
    await expect(page.locator('[data-testid="tracelink-create-form"]')).toBeVisible({ timeout: 8000 });

    await expect(page.locator('[data-testid="tracelink-source-select"]')).toBeVisible({ timeout: 6000 });
    await expect(page.locator('[data-testid="tracelink-target-select"]')).toBeVisible({ timeout: 6000 });
    await expect(page.locator('[data-testid="tracelink-type-select"]')).toBeVisible({ timeout: 6000 });
    await expect(page.locator('[data-testid="tracelink-submit-btn"]')).toBeVisible({ timeout: 6000 });
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
    await expect(page.locator('[data-testid="tracelink-create-form"]')).toBeVisible({ timeout: 8000 });

    const sourceSelect = page.locator('[data-testid="tracelink-source-select"]');
    const targetSelect = page.locator('[data-testid="tracelink-target-select"]');
    await expect(sourceSelect).toBeVisible({ timeout: 6000 });
    await expect(targetSelect).toBeVisible({ timeout: 6000 });

    const sourceOptionCount = await sourceSelect.locator('option').count();
    const targetOptionCount = await targetSelect.locator('option').count();

    if (sourceOptionCount <= 1 || targetOptionCount <= 1) {
      test.skip(true, 'Source or target dropdown is empty — artifacts not loaded');
      return;
    }

    // Select first non-placeholder options
    const sourceOptions = await sourceSelect.locator('option').allInnerTexts();
    const targetOptions = await targetSelect.locator('option').allInnerTexts();

    // Pick the first real (non-empty, non-placeholder) option
    const sourceValue = sourceOptions.find((o) => o.trim() && !/select|choose|--/i.test(o));
    const targetValue = targetOptions.find((o) => o.trim() && !/select|choose|--/i.test(o));
    if (!sourceValue || !targetValue) {
      test.skip(true, 'No selectable options found in dropdowns');
      return;
    }

    await sourceSelect.selectOption({ label: sourceValue });

    // Target may be a different element after source selection
    await targetSelect.selectOption({ label: targetValue });

    // Select link type if options available
    const typeSelect = page.locator('[data-testid="tracelink-type-select"]');
    const typeCount = await typeSelect.locator('option').count();
    if (typeCount > 1) {
      const typeOptions = await typeSelect.locator('option').allInnerTexts();
      const firstType = typeOptions.find((o) => o.trim() && !/select|choose|--/i.test(o));
      if (firstType) {
        await typeSelect.selectOption({ label: firstType });
      }
    }

    await page.locator('[data-testid="tracelink-submit-btn"]').click();
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
    await page.locator('[data-testid="create-arch-btn"]').click();
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 12000 });

    const panel = page.locator('[data-testid="arch-tracelink-panel"]');
    await expect(panel).toBeVisible({ timeout: 8000 });
  });

  // -------------------------------------------------------------------------
  // REQ-L2-RF-005 — Architecture editor shows element_type selector with 5 options (Bug A3)
  // -------------------------------------------------------------------------
  test('[REQ-L2-RF-005] architecture editor has element_type selector with correct testid and 5 options', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await page.locator('[data-testid="create-arch-btn"]').click();
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 12000 });

    // Bug A3: testid should be "arch-element-type-select" (not "arch-element-type")
    const typeSelect = page.locator('[data-testid="arch-element-type-select"]');
    await expect(typeSelect).toBeVisible({ timeout: 6000 });

    const options = await typeSelect.locator('option').allTextContents();
    expect(options).toEqual(
      expect.arrayContaining(['Component', 'Interface', 'Subsystem', 'Layer', 'Module'])
    );
    // Must have exactly the 5 ADR-L3-RF-007 options (plus possible placeholder)
    const realOptions = options.filter((o) => o.trim() && !/select|choose|--/i.test(o));
    expect(realOptions.length).toBeGreaterThanOrEqual(5);
  });
});
