import { Page, request } from '@playwright/test';

const BASE_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

export const TEST_USER = {
  email: 'admin@example.com',
  password: 'admin12345',
};

/**
 * Login via UI on the /login page.
 * Uses real selectors: #username-input, #password-input, button[type="submit"]
 */
export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto(`${FRONTEND_URL}/login`);
  await page.fill('#username-input', TEST_USER.email);
  await page.fill('#password-input', TEST_USER.password);
  await page.click('button[type="submit"]');
  // Wait for redirect away from /login
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10000 });
}

/**
 * Get a JWT token directly via API (no browser needed).
 */
export async function getAuthToken(): Promise<string> {
  const ctx = await request.newContext({ baseURL: BASE_URL });
  const response = await ctx.post('/api/v1/auth/login/', {
    data: { email: TEST_USER.email, password: TEST_USER.password },
  });
  if (!response.ok()) {
    throw new Error(`Login failed: ${response.status()} ${await response.text()}`);
  }
  const body = await response.json();
  await ctx.dispose();
  // Token field may be 'token' or 'access' depending on backend implementation
  return body.token || body.access || body.access_token;
}

/**
 * Inject JWT into sessionStorage so tests skip the login UI.
 */
export async function setAuthToken(page: Page, token: string): Promise<void> {
  await page.addInitScript((t) => {
    sessionStorage.setItem('reqflow_token', t);
  }, token);
}
