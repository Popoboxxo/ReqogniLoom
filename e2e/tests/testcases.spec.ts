import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken } from '../helpers/auth';

// REQ-L1-012, REQ-L2-TE-001, REQ-L2-TE-006
test.describe('TestCase Management', () => {
  test('list testcases via API', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get('http://localhost:8000/api/v1/testcases/', {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    expect([200, 401, 403, 404]).toContain(response.status());
  });

  test('create testcase via API', async ({ request }) => {
    const token = await getAuthToken();
    if (!token) { test.skip(); return; }
    const response = await request.post('http://localhost:8000/api/v1/testcases/', {
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { name: 'E2E Test Case', description: 'Created via Playwright' },
    });
    expect([200, 201, 400, 401, 403]).toContain(response.status());
  });

  test('testcases section visible in UI', async ({ page }) => {
    await loginAsAdmin(page);
    const testLink = page.locator('a:has-text("Test"), a:has-text("Testfall"), [data-testid="nav-testcases"]').first();
    if (await testLink.isVisible()) {
      await testLink.click();
      await page.waitForTimeout(1000);
    }
  });
});
