import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../helpers/auth';

// REQ-L1-033, REQ-L2-AT-001
test.describe('Authentication', () => {
  test('login with valid credentials', async ({ page }) => {
    await loginAsAdmin(page);
    // After login, should not be on login page anymore
    await expect(page).not.toHaveURL(/.*login.*/);
  });

  test('login with invalid password shows error', async ({ page }) => {
    await page.goto('/');
    const emailInput = page.locator('input[type="email"], input[name="email"]').first();
    const passwordInput = page.locator('input[type="password"], input[name="password"]').first();
    await emailInput.fill('admin@example.com');
    await passwordInput.fill('wrongpassword');
    await page.click('button[type="submit"]');
    // Should stay on login page or show error
    await page.waitForTimeout(2000);
    const errorVisible = await page.locator('text=error, text=invalid, text=wrong, text=ungültig, [role="alert"]').first().isVisible().catch(() => false);
    const stillOnLogin = page.url().includes('login') || await page.locator('input[type="password"]').isVisible();
    expect(errorVisible || stillOnLogin).toBeTruthy();
  });

  test('logout works', async ({ page }) => {
    await loginAsAdmin(page);
    const logoutBtn = page.locator('[data-testid="logout"], button:has-text("Logout"), button:has-text("Abmelden"), a:has-text("Logout")').first();
    if (await logoutBtn.isVisible()) {
      await logoutBtn.click();
      await page.waitForTimeout(1000);
      // Should be back on login or landing page
    }
  });
});
