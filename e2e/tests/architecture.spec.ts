// REQ-L1-004, REQ-L2-AS-004: Architecture elements CRUD
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, createIsolatedWorkspace } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Architecture Management', () => {
  let workspaceId: string;

  test.beforeEach(async ({ page }) => {
    // Each test gets its own empty workspace so architecture-root creation
    // (invariant [I5]: one root per workspace) never collides across specs.
    const token = await getAuthToken();
    workspaceId = await createIsolatedWorkspace(token);
    await setWorkspaceId(page, workspaceId);
    await loginAsAdmin(page);
  });

  test('[REQ-L1-004] architecture list page loads', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await expect(page.locator('body')).toBeVisible();
    await expect(page.locator('[data-testid="create-arch-btn"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L1-004] can open new architecture element form', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    // "+ New" opens an inline quick-create form first; title is required
    // before Create is enabled, then it navigates to /architecture/:id.
    await page.locator('[data-testid="create-arch-btn"]').click();
    await page.locator('[data-testid="arch-new-title-input"]').fill('E2E Arch Element');
    await page.locator('[data-testid="arch-new-save-btn"]').click();
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L1-004] create architecture element via API', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.post(`${BACKEND_URL}/api/v1/architecture/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: workspaceId,
        title: 'E2E Test Architecture Element',
        element_type: 'component',
      },
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.id).toBeDefined();
    expect(body.title).toBe('E2E Test Architecture Element');

    // Cleanup
    await request.delete(`${BACKEND_URL}/api/v1/architecture/${body.id}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  test('[REQ-L1-004] create and save architecture element via UI', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await page.locator('[data-testid="create-arch-btn"]').click();
    await page.locator('[data-testid="arch-new-title-input"]').fill('E2E Arch Element');
    await page.locator('[data-testid="arch-new-save-btn"]').click();

    // Wait for navigation to /architecture/:id and the title input to appear
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="arch-title"]').fill('UI E2E Arch Element');
    await page.locator('[data-testid="arch-save-btn"]').click();

    await expect(page.locator('[data-testid="arch-title"]')).toHaveValue('UI E2E Arch Element', { timeout: 8000 });
  });
});
