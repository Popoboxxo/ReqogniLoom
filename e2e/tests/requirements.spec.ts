// REQ-L1-002, REQ-L2-AS-003: Requirements CRUD
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Requirements Management', () => {
  test.beforeEach(async ({ page }) => {
    // Inject real workspace ID so WorkspaceContext uses the seeded workspace
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L1-002] requirements list page loads', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await expect(page.locator('body')).toBeVisible();
    // The create button must be present
    await expect(page.locator('[data-testid="create-req-btn"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L1-002] can open new requirement form', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    // "+ New" opens an inline quick-create form first; Save navigates to
    // /requirements/:id where the title input renders.
    await page.locator('[data-testid="create-req-btn"]').click();
    await page.locator('[data-testid="req-new-title-input"]').fill('E2E New Requirement Form');
    await page.locator('[data-testid="req-new-save-btn"]').click();
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L1-002] create requirement via API', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: 'E2E Test Requirement',
        description: 'Created by Playwright E2E test',
        category: 'Functional',
      },
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.id).toBeDefined();
    expect(body.title).toBe('E2E Test Requirement');

    // Cleanup
    await request.delete(`${BACKEND_URL}/api/v1/requirements/${body.id}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  test('[REQ-L1-002] create and edit requirement via UI', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await page.locator('[data-testid="req-new-title-input"]').fill('E2E Create And Edit Requirement');
    await page.locator('[data-testid="req-new-save-btn"]').click();

    // Wait for navigation to /requirements/:id and the title input to appear
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="req-title"]').fill('UI E2E Requirement');

    // Save
    await page.locator('[data-testid="save-btn"]').click();
    // After save, the form persists or navigates — title field should have the value
    await expect(page.locator('[data-testid="req-title"]')).toHaveValue('UI E2E Requirement', { timeout: 8000 });
  });
});
