// REQ-L1-004, REQ-L2-AS-004: Architecture elements CRUD
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Architecture Management', () => {
  test.beforeEach(async ({ page }) => {
    // Inject real workspace ID so WorkspaceContext uses the seeded workspace
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L1-004] architecture list page loads', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await expect(page.locator('body')).toBeVisible();
    await expect(page.locator('[data-testid="create-arch-btn"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L1-004] can open new architecture element form', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await page.locator('[data-testid="create-arch-btn"]').click();
    // Title input should appear after successful create + navigation to /architecture/:id
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L1-004] create architecture element via API', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.post(`${BACKEND_URL}/api/v1/architecture/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
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

    // Wait for navigation to /architecture/:id and the title input to appear
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="arch-title"]').fill('UI E2E Arch Element');
    await page.locator('[data-testid="arch-save-btn"]').click();

    await expect(page.locator('[data-testid="arch-title"]')).toHaveValue('UI E2E Arch Element', { timeout: 8000 });
  });
});
