import { Page } from '@playwright/test';

export async function loginAsAdmin(page: Page) {
  await page.goto('/');
  await page.fill('[data-testid="email-input"], input[type="email"], input[name="email"]', 'admin@example.com');
  await page.fill('[data-testid="password-input"], input[type="password"], input[name="password"]', 'admin12345');
  await page.click('[data-testid="login-button"], button[type="submit"]');
  await page.waitForURL('**/dashboard', { timeout: 10000 }).catch(() => {});
}

export async function getAuthToken(): Promise<string> {
  const response = await fetch('http://localhost:8000/api/v1/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email: 'admin@example.com', password: 'admin12345' }),
  });
  const data = await response.json();
  return data.access_token || data.token || '';
}
