import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Ontology Simulation & Trace Link Config', () => {
  let testWorkspaceId: string;

  test.beforeEach(async ({ request, page }) => {
    const token = await getAuthToken();

    // 1. Create a dedicated workspace for this ontology test
    const createResp = await request.post(`${BACKEND_URL}/api/v1/workspaces/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        name: `Ontology Test ${Date.now()}`,
        preset: 'extended',
        terminology_profile: 'se_mode',
        language: 'en'
      }
    });
    expect(createResp.ok()).toBeTruthy();
    const ws = await createResp.json();
    testWorkspaceId = ws.id;

    // 2. Set decomposition_link_type to 'derives-from'
    const patchResp = await request.patch(`${BACKEND_URL}/api/v1/workspaces/${testWorkspaceId}/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        decomposition_link_type: 'derives-from'
      }
    });
    expect(patchResp.ok()).toBeTruthy();

    // 3. Inject this workspace into the session so UI uses it
    await setWorkspaceId(page, testWorkspaceId);
    await loginAsAdmin(page);
  });

  test('simulate L1 to L2 decomposition with derives-from', async ({ page }) => {
    // ---------------------------------------------------------
    // 1. Create Level 1 Requirement (System Req)
    // ---------------------------------------------------------
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await expect(page.locator('[data-testid="req-new-title-input"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="req-new-title-input"]').fill('SYS-REQ-001: Main System Function');
    
    // There might not be a type selector in the quick create form, so we just save
    await page.locator('[data-testid="req-new-save-btn"]').click();
    
    // Now wait for the detail view to load
    await expect(page.locator('[data-testid="req-title"]')).toHaveValue('SYS-REQ-001: Main System Function', { timeout: 8000 });
    
    // Choose SyReq (System Requirement) in the detail view
    // The type is SyReq by default, so we don't need to change it.


    const currentUrl = page.url();
    const l1ReqId = currentUrl.split('/').pop();
    expect(l1ReqId).toBeDefined();

    // ---------------------------------------------------------
    // 2. Create Level 1 Architecture Element (System Arch)
    // ---------------------------------------------------------
    await page.goto(`${FRONTEND_URL}/architecture`);
    await page.locator('[data-testid="create-arch-btn"]').click();
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="arch-title"]').fill('SYS-ARCH-001: Core System Component');
    await page.locator('[data-testid="arch-save-btn"]').click();
    await expect(page.locator('[data-testid="arch-title"]')).toHaveValue('SYS-ARCH-001: Core System Component', { timeout: 8000 });

    const archUrl = page.url();
    const l1ArchId = archUrl.split('/').pop();
    expect(l1ArchId).toBeDefined();

    // ---------------------------------------------------------
    // 3. Link them via satisfies
    // ---------------------------------------------------------
    // Go back to the Requirement
    await page.goto(`${FRONTEND_URL}/requirements/${l1ReqId}`);
    
    // Create new trace link
    await page.locator('[data-testid="req-tracelink-create-btn"]').click();
    await page.locator('[data-testid="req-tracelink-target-select"]').selectOption(l1ArchId!);
    await page.locator('[data-testid="req-tracelink-type-select"]').selectOption('satisfies');
    await page.locator('[data-testid="req-tracelink-submit-btn"]').click();

    // Verify link appears in the UI
    await expect(page.locator('[data-testid="req-tracelink-item"]').filter({ hasText: 'satisfies' })).toBeVisible({ timeout: 8000 });

    // ---------------------------------------------------------
    // 4. Derive L2 Requirement (Subsystem Req)
    // ---------------------------------------------------------
    // Use the derive functionality from the L1 requirement
    await page.locator('[data-testid="req-tracelink-derive-btn"]').click();
    
    // The inline form opens for derivation
    await expect(page.locator('[data-testid="req-derive-title-input"]')).toBeVisible({ timeout: 8000 });
    await page.locator('[data-testid="req-derive-title-input"]').fill('SUB-REQ-001: Subsystem Function');
    
    // Choose the architecture element for the derived requirement
    await page.locator('[data-testid="req-derive-architecture-select"]').selectOption(l1ArchId!);
    
    // Submit the form (it has no explicit submit testid in the view snippet, but it's a form submit button. Let's find it. Wait, the snippet showed it as a form submit button. I will press Enter inside the input or click the generic submit if possible. Let's just use Enter key)
    await page.locator('[data-testid="req-derive-title-input"]').press('Enter');

    // Wait for the new child requirement to load
    await expect(page.locator('[data-testid="req-title"]')).toHaveValue('SUB-REQ-001: Subsystem Function', { timeout: 10000 });

    // Check its traceability to confirm it's linked via derives-from instead of parent-child
    // We look for 'derives-from' text inside the trace link item list
    await expect(page.locator('[data-testid="req-tracelink-item"]').filter({ hasText: 'derives-from' })).toBeVisible({ timeout: 8000 });
  });
});
