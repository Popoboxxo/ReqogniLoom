// REQ-L1-033, REQ-L2-AT-001: Authentication flows
import { test, expect } from '@playwright/test';
import { loginAsAdmin, TEST_USER } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('Authentication', () => {
  test('login with valid credentials redirects to dashboard', async ({ page }) => {
    await loginAsAdmin(page);
    // After login, should be on the dashboard (not /login)
    await expect(page).not.toHaveURL(/\/login/);
    await expect(page.locator('body')).toBeVisible();
  });

  test('login with wrong password shows error', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/login`);
    await page.fill('#username-input', TEST_USER.email);
    await page.fill('#password-input', 'wrong-password-xyz');
    await page.click('button[type="submit"]');
    // Error alert must appear
    const alert = page.locator('[role="alert"]');
    await expect(alert).toBeVisible({ timeout: 8000 });
  });

  test('unauthenticated user is redirected to login', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await expect(page).toHaveURL(/\/login/, { timeout: 8000 });
  });
});
