/**
 * Shared setup plumbing for the four `smoke-*.spec.ts` files.
 *
 * Everything here is FIXTURE/setup-level: one API login per spec file, its
 * httpOnly cookies injected into each fresh browser context, a bounded UI-login
 * retry for transient auth bounces, a single navigate-and-settle helper and one
 * evidence attachment helper. No check's assertions live here — every smoke
 * check still drives real browser actions (clicks, keyboard, form fills,
 * navigation, axe scans) and asserts visible results in its own spec file.
 *
 * The legacy `setAuthToken(page, token)` writes sessionStorage `reqflow_token`,
 * which the current frontend does not read (auth is the httpOnly
 * `reqogniloom_access` cookie, see frontend/src/api/client.ts). That is why the
 * working fixture setup injects the real login cookies instead.
 */
import {
  expect,
  request as pwRequest,
  type APIResponse,
  type Page,
  type TestInfo,
} from '@playwright/test';
import { loginAsAdmin, TEST_USER } from './auth';

export const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
export const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

const COOKIE_DOMAIN = new URL(FRONTEND_URL).hostname;

/** Only auth-adjacent cookies may enter the shared pool (review F-08). */
const SESSION_COOKIE_NAME = /^(reqogniloom_|csrftoken$)/;

export interface SessionCookie {
  name: string;
  value: string;
  domain: string;
  path: string;
  httpOnly?: boolean;
  secure?: boolean;
  sameSite?: 'Strict' | 'Lax' | 'None';
}

function authCookies(cookies: ReadonlyArray<SessionCookie>): SessionCookie[] {
  return cookies.filter((c) => SESSION_COOKIE_NAME.test(c.name));
}

/**
 * Fail loudly on a rejected restore/cleanup write, printing the status and the
 * response body (read on the failure path only). Same precedent as
 * a11y-smoke.spec.ts's theme PUT.
 */
export async function expectOk(response: APIResponse, label: string): Promise<void> {
  if (response.ok()) return;
  const body = await response.text().catch(() => '(unreadable body)');
  throw new Error(`${label} failed: ${response.status()} ${body}`);
}

export interface SmokeSession {
  readonly token: string;
  obtain(): Promise<void>;
  apply(page: Page): Promise<void>;
  refreshFromPage(page: Page): Promise<void>;
  loginWithRetry(page: Page): Promise<void>;
  gotoRoute(page: Page, route: string): Promise<void>;
}

/**
 * Per-spec-file session state. A fresh instance per spec mirrors the previous
 * module-local state and prevents cross-file leakage even when a worker is
 * reused across spec files.
 */
export function createSmokeSession(): SmokeSession {
  let sessionCookies: SessionCookie[] = [];
  let fixtureToken = '';

  const toSessionCookie = (c: {
    name: string; value: string; path?: string;
    httpOnly?: boolean; secure?: boolean; sameSite?: string;
  }): SessionCookie => ({
    name: c.name,
    value: c.value,
    domain: COOKIE_DOMAIN,
    path: c.path || '/',
    httpOnly: c.httpOnly,
    secure: c.secure,
    sameSite: c.sameSite as SessionCookie['sameSite'],
  });

  return {
    get token(): string {
      return fixtureToken;
    },

    /** One fixture login: capture the token and the auth cookies together. */
    async obtain(): Promise<void> {
      const ctx = await pwRequest.newContext({ baseURL: BACKEND_URL });
      try {
        const resp = await ctx.post('/api/v1/auth/login/', {
          data: { username: TEST_USER.username, password: TEST_USER.password },
        });
        await expectOk(resp, 'fixture login');
        const body = await resp.json();
        fixtureToken = body.token || body.access || body.access_token || '';
        sessionCookies = authCookies(
          (await ctx.storageState()).cookies.map(toSessionCookie)
        );
      } finally {
        await ctx.dispose();
      }
    },

    async apply(page: Page): Promise<void> {
      await page.context().addCookies(sessionCookies);
    },

    /** Refresh only the auth cookies after a real UI login (review F-08). */
    async refreshFromPage(page: Page): Promise<void> {
      sessionCookies = authCookies(
        (await page.context().cookies()).map(toSessionCookie)
      );
    },

    /** Bounded retry around the shared helper for genuine UI-login recovery. */
    async loginWithRetry(page: Page): Promise<void> {
      let lastError: unknown;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          await loginAsAdmin(page);
          return;
        } catch (err) {
          lastError = err;
          await page.waitForTimeout(1500 * (attempt + 1));
        }
      }
      throw lastError;
    },

    /** Navigate + settle, with one bounded auth-bounce recovery. */
    async gotoRoute(page: Page, route: string): Promise<void> {
      // `commit` avoids the dev-server document-load wait; readiness is proved
      // by the visible assertions below, not the navigation lifecycle event.
      await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'commit' });
      await expect(
        page.locator('main[role="main"]').or(page.locator('#username-input')).first()
      ).toBeVisible({ timeout: 12000 });
      if (page.url().includes('/login')) {
        await this.loginWithRetry(page);
        await this.refreshFromPage(page);
        await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'commit' });
      }
      // Suspense/main are the real readiness gate; `networkidle` never settles
      // on the HMR dev stack and used to burn ~4 s per route check.
      await expect(page.locator('[data-testid="route-suspense-fallback"]')).toHaveCount(0, {
        timeout: 15000,
      });
      await expect(page.locator('main[role="main"]')).toBeVisible({ timeout: 10000 });
    },
  };
}

/** One compact "action + visible result" text proof per check (incl. dialog). */
export async function attachEvidence(
  testInfo: TestInfo,
  label: string,
  page: Page,
  action: string,
  selector: string
): Promise<void> {
  const main =
    (await page.locator('main[role="main"]').first().textContent().catch(() => null)) ??
    (await page.locator('body').textContent().catch(() => null)) ??
    '';
  const dialog = page.locator('[role="dialog"]').first();
  const dialogText = (await dialog.count()) ? ((await dialog.textContent()) ?? '') : '';
  await testInfo.attach(`smoke-${label}`, {
    body:
      `ACTION: ${action}\nVISIBLE: ${selector}\nURL: ${page.url()}\n` +
      `--- dialog (capped 500 chars) ---\n${dialogText.slice(0, 500)}\n` +
      `--- main (capped 1200 chars) ---\n${main.slice(0, 1200)}`,
    contentType: 'text/plain',
  });
}

/** Known non-application console noise, kept out of the console-error assertion. */
export function isKnownConsoleNoise(message: string): boolean {
  return (
    message.includes('favicon') ||
    message.includes('hot-update') ||
    message.includes('[HMR]') ||
    message.includes('WebSocket') ||
    message.includes('vite')
  );
}

/**
 * Classify an HTTP response as an application error. 429s from app API routes
 * are NOT noise (review F-07): they are reported so the check fails and the
 * evidence names them.
 */
export function appResponseError(resp: APIResponse): string | null {
  const status = resp.status();
  if (status !== 404 && status !== 500 && status !== 429) return null;
  const url = new URL(resp.url());
  const appOrigin = new URL(FRONTEND_URL).origin;
  if (url.origin !== appOrigin && url.hostname !== 'localhost') return null;
  if (url.pathname.includes('favicon')) return null;
  return `${status} ${url.pathname}`;
}
