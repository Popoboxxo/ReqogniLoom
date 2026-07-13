// REQ-L1-035, REQ-L2-AS-030: Test-Run-Protokollierung
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

test.describe('TestRun Management', () => {
  let createdRunId: string | undefined;

  test.afterEach(async ({ request }) => {
    if (createdRunId) {
      const token = await getAuthToken();
      // TestRuns cannot be deleted (immutable) — skip cleanup
      createdRunId = undefined;
    }
  });

  test('[REQ-L2-AS-030] create a test run via API', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.post(`${BACKEND_URL}/api/v1/test-runs/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        name: 'E2E Test Run',
        ci_job_id: 'e2e-job-001',
      },
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    expect(body.id).toBeDefined();
    expect(body.name).toBe('E2E Test Run');
    expect(body.status).toBe('in_progress');
    createdRunId = body.id;
  });

  test('[REQ-L2-AS-030] list test runs via API', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/test-runs/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results;
    expect(Array.isArray(items)).toBeTruthy();
  });

  test('[REQ-L2-AS-030] close a test run recalculates aggregate status', async ({ request }) => {
    const token = await getAuthToken();

    // Create a test case first
    const tcResp = await request.post(`${BACKEND_URL}/api/v1/testcases/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: 'Status test TC',
      },
    });
    expect(tcResp.ok()).toBeTruthy();
    const tc = await tcResp.json();
    const tcId = tc.id;

    // Create test run (without test_case_ids, so no initial not_run results)
    const runResp = await request.post(`${BACKEND_URL}/api/v1/test-runs/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        name: 'Aggregate Test Run',
      },
    });
    expect(runResp.ok()).toBeTruthy();
    const run = await runResp.json();
    const runId = run.id;

    // Add a passed result
    const resultResp = await request.post(`${BACKEND_URL}/api/v1/test-runs/${runId}/results/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        test_case_id: tcId,
        status: 'passed',
        message: 'All good',
      },
    });
    expect(resultResp.ok()).toBeTruthy();

    // Close
    const closeResp = await request.post(`${BACKEND_URL}/api/v1/test-runs/${runId}/close/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(closeResp.ok()).toBeTruthy();
    const closed = await closeResp.json();
    expect(closed.status).toBe('passed');
    expect(closed.finished_at).toBeDefined();
  });

  test('[REQ-L2-AS-031] bulk result ingestion via API', async ({ request }) => {
    const token = await getAuthToken();

    // Create test cases
    const tcIds: string[] = [];
    for (let i = 0; i < 3; i++) {
      const resp = await request.post(`${BACKEND_URL}/api/v1/testcases/`, {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          workspace_id: SEEDED_WORKSPACE_ID,
          title: `Bulk TC ${i}`,
        },
      });
      expect(resp.ok()).toBeTruthy();
      const tc = await resp.json();
      tcIds.push(tc.id);
    }

    // Create test run
    const runResp = await request.post(`${BACKEND_URL}/api/v1/test-runs/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        name: 'Bulk Test Run',
      },
    });
    expect(runResp.ok()).toBeTruthy();
    const run = await runResp.json();
    const runId = run.id;

    // Bulk add results
    const bulkResp = await request.post(`${BACKEND_URL}/api/v1/test-runs/${runId}/results/bulk/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        results: tcIds.map((tcId, i) => ({
          test_case_id: tcId,
          status: i === 0 ? 'failed' : 'passed',
          message: `Result for TC ${i}`,
        })),
      },
    });
    expect(bulkResp.ok()).toBeTruthy();
    const bulkBody = await bulkResp.json();
    expect(bulkBody.count).toBe(3);
    expect(bulkBody.results.length).toBe(3);

    // Close and verify aggregate
    const closeResp = await request.post(`${BACKEND_URL}/api/v1/test-runs/${runId}/close/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(closeResp.ok()).toBeTruthy();
    const closed = await closeResp.json();
    expect(closed.status).toBe('failed');
  });
});
