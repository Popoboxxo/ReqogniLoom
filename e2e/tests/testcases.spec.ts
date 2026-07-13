// REQ-L1-012, REQ-L2-TE-001: TestCase management
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('TestCase Management', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L1-012] list test cases via API', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/testcases/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    // Accepts both paginated {results: []} and plain array []
    const items = Array.isArray(body) ? body : body.results;
    expect(Array.isArray(items)).toBeTruthy();
  });

  test('[REQ-L1-012] create test case via API', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.post(`${BACKEND_URL}/api/v1/testcases/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: 'E2E Test Case',
        description: 'Created by Playwright E2E test',
      },
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.id).toBeDefined();

    // Cleanup
    await request.delete(`${BACKEND_URL}/api/v1/testcases/${body.id}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });
});
