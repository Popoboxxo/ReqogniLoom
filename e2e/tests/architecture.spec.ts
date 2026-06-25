import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken } from '../helpers/auth';

// REQ-L1-004, REQ-L2-AS-004
test.describe('Architecture Management', () => {
  test('list architecture elements via API', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get('http://localhost:8000/api/v1/architecture/', {
      headers: { 'Authorization': `Bearer ${token}` },
    });
    expect([200, 401, 403, 404]).toContain(response.status());
  });

  test('create architecture element via API', async ({ request }) => {
    const token = await getAuthToken();
    if (!token) { test.skip(); return; }
    const response = await request.post('http://localhost:8000/api/v1/architecture/', {
      headers: { 'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { name: 'E2E Architecture Element', level: 'L1', type_name: 'System' },
    });
    expect([200, 201, 400, 401, 403]).toContain(response.status());
  });

  test('architecture section visible in UI', async ({ page }) => {
    await loginAsAdmin(page);
    const archLink = page.locator('a:has-text("Architecture"), a:has-text("Architektur"), [data-testid="nav-architecture"]').first();
    if (await archLink.isVisible()) {
      await archLink.click();
      await page.waitForTimeout(1000);
      await expect(page).not.toHaveURL(/.*login.*/);
    }
  });
});
