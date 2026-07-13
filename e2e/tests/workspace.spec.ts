// REQ-L2-RF-012: Workspace-Konfigurations-UI + Workspace-Switcher
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[COMP-RF-001] WorkspaceSwitcher', () => {
  test('[REQ-L2-RF-012] GET /api/v1/workspaces/ returns workspace list', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/workspaces/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results ?? [];
    expect(items.length).toBeGreaterThanOrEqual(1);
    expect(items[0]).toHaveProperty('id');
    expect(items[0]).toHaveProperty('name');
  });

  test('[REQ-L2-RF-012] workspace switcher is visible in sidebar after login', async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.waitForLoadState('networkidle');
    const switcher = page.locator('[data-testid="workspace-switcher"]');
    await expect(switcher).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L2-RF-012] workspace is auto-loaded on login (not zero-UUID)', async ({ page }) => {
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.waitForLoadState('networkidle');
    // The workspace switcher should show a real workspace name, not "Default Workspace"
    const switcher = page.locator('[data-testid="workspace-switcher"]');
    await expect(switcher).toBeVisible({ timeout: 10000 });
    const text = await switcher.textContent();
    expect(text).not.toContain('00000000');
  });
});
