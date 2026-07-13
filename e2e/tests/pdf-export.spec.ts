// REQ-L2-AS-016, REQ-L2-RF-005, REQ-L2-RF-006: PDF export E2E tests
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('PDF Export', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L2-AS-016] PDF report API returns valid PDF', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/reports/pdf/`,
      {
        headers: { Authorization: `Bearer ${token}` },
        params: { layout: 'requirement_document' },
      }
    );
    expect(response.ok()).toBeTruthy();
    expect(response.headers()['content-type']).toContain('application/pdf');

    const body = await response.body();
    // PDF magic bytes
    expect(body.slice(0, 5).toString()).toBe('%PDF-');
    expect(body.length).toBeGreaterThan(1024);
  });

  test('[REQ-L2-AS-016] PDF traceability matrix API returns valid PDF', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/reports/pdf/`,
      {
        headers: { Authorization: `Bearer ${token}` },
        params: { layout: 'traceability_matrix' },
      }
    );
    expect(response.ok()).toBeTruthy();
    const body = await response.body();
    expect(body.slice(0, 5).toString()).toBe('%PDF-');
  });

  test('[REQ-L2-RF-005] export PDF button visible on requirements page', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    const btn = page.locator('[data-testid="export-pdf-btn"]');
    await expect(btn).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L2-RF-006] export PDF button visible on traceability page', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    const btn = page.locator('[data-testid="export-pdf-btn"]');
    await expect(btn).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L2-AS-016] invalid layout returns 400', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/reports/pdf/`,
      {
        headers: { Authorization: `Bearer ${token}` },
        params: { layout: 'invalid_layout' },
      }
    );
    expect(response.status()).toBe(400);
  });
});
