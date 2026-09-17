// REQ-L2-SM-001: SeMetrics API endpoint
import { test, expect } from '@playwright/test';
import { getAuthToken, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

test.describe('[REQ-L2-SM-001] SeMetrics API', () => {
  test('[REQ-L2-SM-001] GET /api/v1/metrics/ returns coverage metrics', async ({ request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };

    // Call metrics endpoint
    const response = await request.get(
      `${BACKEND_URL}/api/v1/metrics/?workspace_id=${SEEDED_WORKSPACE_ID}&type=coverage`,
      { headers },
    );
    expect(response.status()).toBe(200);

    const body = await response.json();
    // Verify at least one metric field is present (REQ-L2-SM-012 shape)
    expect(body).toBeDefined();
    expect(body.workspace_id).toBe(SEEDED_WORKSPACE_ID);
    expect(body.computed_at).toBeDefined();
    expect(body.timeframe).toBeDefined();
    // At least one metric sub-object should exist
    const hasMetricField =
      'traceability_coverage' in body ||
      'volatility' in body ||
      'workflow_gaps' in body ||
      'open_risks' in body;
    expect(hasMetricField).toBeTruthy();
  });
});
