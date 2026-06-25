// REQ-L1-003: Traceability links
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Traceability', () => {
  test.beforeEach(async ({ page }) => {
    await loginAsAdmin(page);
  });

  test('traceability page loads', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    await expect(page.locator('body')).toBeVisible();
  });

  test('list trace links via API', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/tracelinks/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.ok()).toBeTruthy();
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results;
    expect(Array.isArray(items)).toBeTruthy();
  });
});
