// REQ-L1-012, REQ-L2-TE-001: TestCase management
import { test, expect, type APIResponse } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/**
 * Assert a 2xx response and put the response body into the failure message.
 *
 * The body is read ONLY on the failure path: the caller's `response.json()`
 * must still be able to consume it on success. #1520 reported a bare
 * `Received: false` here and left the actual 400 (a rejected payload field)
 * invisible in CI.
 */
async function expectRequestOk(response: APIResponse, label: string): Promise<void> {
  if (response.ok()) return;
  expect(response.ok(), `${label} ${response.status()}: ${await response.text()}`).toBeTruthy();
}

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
    await expectRequestOk(reqResponse, 'POST /api/v1/requirements/');
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
    await expectRequestOk(tcResponse, 'POST /api/v1/testcases/');
    const testCase = await tcResponse.json();

    // TraceLink endpoints are ARTIFACT ids — `TraceLinkSerializer.source_id`
    // is documented as "Canonical Artifact id of the source endpoint (not the
    // entity PK)" — and `_test_to_dict` exposes the TestCase's backing
    // `artifact_id`. Do NOT fall back to the entity pk: the link would then be
    // filed in the wrong id space while the POST still answers 201, and the
    // detail panel (which queries with `artifact_id ?? id`) would silently stay
    // empty. Fail loudly instead of hiding that in a fallback.
    expect(testCase.artifact_id, 'POST /api/v1/testcases/ must return a non-null artifact_id').toBeTruthy();
    expect(requirement.artifact_id, 'POST /api/v1/requirements/ must return a non-null artifact_id').toBeTruthy();

    // `TraceLinkSerializer` accepts source_id / target_id / link_type (+
    // rationale) and nothing else: it declares no `workspace_id`, and
    // `UnknownFieldRejectionMixin` (#851) rejects undeclared keys with 400
    // "Unknown field." — the workspace is derived from the source artifact's
    // own row (`validate_link_pair(source.workspace_id, …)`), never from the
    // request. 'verifies' allows exactly (TestCase -> Requirement |
    // ArchitectureElement), see backend/link_types/builtin.py.
    const linkResponse = await request.post(`${BACKEND_URL}/api/v1/tracelinks/`, {
      headers,
      data: {
        source_id: testCase.artifact_id,
        target_id: requirement.artifact_id,
        link_type: 'verifies',
      },
    });
    await expectRequestOk(linkResponse, 'POST /api/v1/tracelinks/');
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
