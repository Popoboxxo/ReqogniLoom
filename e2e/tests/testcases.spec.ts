// REQ-L1-012, REQ-L2-TE-001: TestCase management
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
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

  // Plan C T-C3-1 (PR-C10, ENT-C1 = B): the test case detail area renders the
  // shared TraceLinkPanel (same as Risk/ADR/Issue/Need), so a `verifies` link
  // is visible with its per-link delete affordance. Fixtures are created over
  // the API and removed again, so the case never depends on seed data.
  test('[REQ-L1-012] test case detail shows the verifies trace link with delete affordance', async ({ page, request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };
    const stamp = Date.now();

    const reqResponse = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: `E2E trace target ${stamp}`,
        category: 'Functional',
      },
    });
    expect(reqResponse.ok()).toBeTruthy();
    const requirement = await reqResponse.json();

    const tcResponse = await request.post(`${BACKEND_URL}/api/v1/testcases/`, {
      headers,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: `E2E trace test case ${stamp}`,
        description: 'Created by the trace-link detail E2E case',
        test_type: 'unit',
      },
    });
    expect(tcResponse.ok()).toBeTruthy();
    const testCase = await tcResponse.json();

    // Trace links live in the Artifact id space; the read path exposes
    // `artifact_id` (the detail editor binds to exactly that).
    const linkResponse = await request.post(`${BACKEND_URL}/api/v1/tracelinks/`, {
      headers,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        source_id: testCase.artifact_id ?? testCase.id,
        target_id: requirement.artifact_id ?? requirement.id,
        link_type: 'verifies',
      },
    });
    expect(linkResponse.ok()).toBeTruthy();
    const link = await linkResponse.json();

    try {
      await page.goto(`${FRONTEND_URL}/testcases/${testCase.id}`);

      // The link-type badge for the created 'verifies' link …
      await expect(page.locator('[data-testid="trace-type-verifies"]')).toBeVisible({ timeout: 15000 });
      // … and its delete affordance, per link id.
      await expect(page.locator(`[data-testid="trace-link-delete-${link.id}"]`)).toBeVisible();
    } finally {
      await request.delete(`${BACKEND_URL}/api/v1/tracelinks/${link.id}/`, { headers });
      await request.delete(`${BACKEND_URL}/api/v1/testcases/${testCase.id}/`, {
        headers,
        data: { change_reason: 'e2e cleanup' },
      });
      await request.delete(`${BACKEND_URL}/api/v1/requirements/${requirement.id}/`, {
        headers,
        data: { change_reason: 'e2e cleanup' },
      });
    }
  });
});
