// Smoke suite — core flows (themes 1+2, checks C01–C17).
//
// Every test is tagged `@smoke` so `npx playwright test --grep @smoke` picks it
// up. Each check drives a real browser action (login/navigation/click) and
// attaches a small text/plain evidence snapshot; one full-page screenshot is
// attached by C03. Shared setup plumbing lives in helpers/smoke-setup.ts.
//
// The seeded workspace and its admin account are shared with 74 other specs.
// The two sidebar checks snapshot the disclosure state they touch and put it
// back in afterEach; the preset/feature-visibility writes in beforeAll are
// restored in afterAll ONLY when their "as found" reads succeeded and a write
// actually happened — a failed read can never leak temporary state.
import { test, expect, request as pwRequest } from '@playwright/test';
import {
  getWorkspacePreset,
  setWorkspaceId,
  setWorkspacePreset,
  SEEDED_WORKSPACE_ID,
  type WorkspacePresetName,
} from '../helpers/auth';
import {
  appResponseError,
  attachEvidence,
  BACKEND_URL,
  createSmokeSession,
  expectOk,
  isKnownConsoleNoise,
} from '../helpers/smoke-setup';

const session = createSmokeSession();

/** The 12 routes the triage verified as rendered + axe-clean. */
const ROUTES: Array<[string, string]> = [
  ['dashboard', '/'],
  ['needs', '/needs'],
  ['requirements', '/requirements'],
  ['adrs', '/adrs'],
  ['architecture', '/architecture'],
  ['traceability', '/traceability'],
  ['testcases', '/testcases'],
  ['test-runs', '/test-runs'],
  ['baselines', '/baselines'],
  ['diagrams', '/diagrams'],
  ['settings', '/settings'],
  ['system-settings', '/system-settings'],
];

/** Disclosure group used by C04/C05; never the active route's group on `/`. */
const SIDEBAR_GROUP = 'requirements';

/** Disclosure state as found, restored after each of the two toggle checks. */
let groupAsFound: boolean | null = null;

let presetAsFound: WorkspacePresetName | null = null;
let presetReadOk = false;
let presetWriteHappened = false;

let featureVisibilityAsFound: Record<string, boolean> | null = null;
let featureVisibilityReadOk = false;
let featureVisibilityWriteHappened = false;

test.describe('Smoke — core flows @smoke', () => {
  test.beforeAll(async () => {
    await session.obtain();
    presetAsFound = await getWorkspacePreset(session.token);
    presetReadOk = true;
    if (presetAsFound !== 'extended') {
      await setWorkspacePreset('extended');
      presetWriteHappened = true;
    }

    const ctx = await pwRequest.newContext({ baseURL: BACKEND_URL });
    try {
      const headers = { Authorization: `Bearer ${session.token}` };
      const resp = await ctx.get('/api/v1/users/me/preferences/', {
        headers,
        params: { workspace_id: SEEDED_WORKSPACE_ID },
      });
      const bodyText = await resp.text();
      expect(resp.ok(), `preferences read failed: ${resp.status()} ${bodyText}`).toBeTruthy();
      featureVisibilityAsFound = ((JSON.parse(bodyText).optional_artifact_visibility ??
        {}) as Record<string, boolean>);
      featureVisibilityReadOk = true;
      if (featureVisibilityAsFound.diagrams !== true) {
        await expectOk(
          await ctx.patch('/api/v1/users/me/preferences/', {
            headers,
            data: {
              workspace_id: SEEDED_WORKSPACE_ID,
              optional_artifact_visibility: { diagrams: true },
            },
          }),
          'temporary diagrams visibility write'
        );
        featureVisibilityWriteHappened = true;
      }
    } finally {
      await ctx.dispose();
    }
  });

  test.afterAll(async () => {
    if (featureVisibilityWriteHappened && featureVisibilityReadOk && featureVisibilityAsFound) {
      const ctx = await pwRequest.newContext({ baseURL: BACKEND_URL });
      try {
        await expectOk(
          await ctx.patch('/api/v1/users/me/preferences/', {
            headers: { Authorization: `Bearer ${session.token}` },
            data: {
              workspace_id: SEEDED_WORKSPACE_ID,
              optional_artifact_visibility: featureVisibilityAsFound,
            },
          }),
          'feature-visibility restore'
        );
      } finally {
        await ctx.dispose();
      }
    }
    if (presetWriteHappened && presetReadOk && presetAsFound && presetAsFound !== 'extended') {
      await setWorkspacePreset(presetAsFound);
    }
  });

  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await session.apply(page);
  });

  test.afterEach(async ({ page }) => {
    if (groupAsFound === null) return;
    const toggle = page.locator(`[data-testid="sidebar-group-toggle-${SIDEBAR_GROUP}"]`);
    if (await toggle.count()) {
      const expanded = (await toggle.getAttribute('aria-expanded')) === 'true';
      if (expanded !== groupAsFound) {
        await toggle.click();
        await expect(toggle).toHaveAttribute('aria-expanded', String(groupAsFound));
      }
    }
    groupAsFound = null;
  });

  test('C01 login reaches dashboard with workspace cards @smoke', async ({ page }, testInfo) => {
    // The login check itself stays a real UI login: drop the injected fixture
    // cookies, log in through /login, then hand the fresh session to the pool.
    await page.context().clearCookies();
    await session.loginWithRetry(page);
    await session.refreshFromPage(page);
    await session.gotoRoute(page, '/');
    await expect(page.locator('[data-testid="workspace-list"]')).toBeVisible({ timeout: 10000 });
    const cards = page.locator('[data-testid="workspace-card"]');
    await expect(cards.first()).toBeVisible({ timeout: 10000 });
    expect(await cards.count()).toBeGreaterThan(0);
    await attachEvidence(
      testInfo,
      'C01-dashboard',
      page,
      'real UI login via loginAsAdmin + navigate to /',
      'workspace-list > workspace-card'
    );
  });

  test('C02 all 12 verified nav links are present @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/');
    await expect(page.locator('[data-testid="workspace-switcher"]')).toHaveCount(1, {
      timeout: 10000,
    });
    // The nav is populated by an async permission/preset query; poll until all
    // 12 anchors have landed instead of sampling the first render.
    const missing = async (): Promise<string[]> => {
      const result: string[] = [];
      for (const [slug, route] of ROUTES) {
        if ((await page.locator(`a[href="${route}"]`).count()) === 0) {
          result.push(`${slug} (${route})`);
        }
      }
      return result;
    };
    await expect.poll(missing, { timeout: 12000 }).toEqual([]);
    await attachEvidence(
      testInfo,
      'C02-nav-links',
      page,
      'inspected sidebar anchors after login',
      'a[href] in nav-group-* panels: all 12 present'
    );
  });

  test('C03 logout via nav-logout returns to /login @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/');
    const logout = page.locator('[data-testid="nav-logout"]');
    await expect(logout).toBeVisible({ timeout: 10000 });
    await logout.click();
    await expect(page).toHaveURL(/\/login/, { timeout: 10000 });
    const text = await page.locator('body').innerText();
    await testInfo.attach('smoke-C03-logout', {
      body: `ACTION: clicked [data-testid="nav-logout"]\nURL: ${page.url()}\n--- body (capped 600 chars) ---\n${text.slice(0, 600)}`,
      contentType: 'text/plain',
    });
    // The one full-page screenshot of this file lives on the small /login page.
    await testInfo.attach('smoke-core-fullpage', {
      body: await page.screenshot({ fullPage: true }),
      contentType: 'image/png',
    });
    // Logout revokes the refresh family used by the shared pool. Restore the
    // fixture session through the API (pure setup, after the checked logout).
    await session.obtain();
  });

  test('C04 collapsing a sidebar group hides its links from the tree @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/');
    const toggle = page.locator(`[data-testid="sidebar-group-toggle-${SIDEBAR_GROUP}"]`);
    await expect(toggle).toBeVisible({ timeout: 10000 });
    groupAsFound = (await toggle.getAttribute('aria-expanded')) === 'true';

    if (!groupAsFound) await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');

    const panelId = await toggle.getAttribute('aria-controls');
    expect(panelId).toBe(`sidebar-nav-group-panel-${SIDEBAR_GROUP}`);
    await expect(page.locator(`[data-testid="nav-group-${SIDEBAR_GROUP}"] a`).first()).toBeVisible();

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator(`#${panelId}`)).toBeHidden();
    await expect(page.locator(`#${panelId} a:visible`)).toHaveCount(0);
    await attachEvidence(
      testInfo,
      'C04-sidebar-collapse',
      page,
      `clicked [data-testid="sidebar-group-toggle-${SIDEBAR_GROUP}"]`,
      `aria-expanded=false; #${panelId} hidden; 0 visible links`
    );
  });

  test('C05 expanding the group restores its links and preference @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/');
    const toggle = page.locator(`[data-testid="sidebar-group-toggle-${SIDEBAR_GROUP}"]`);
    await expect(toggle).toBeVisible({ timeout: 10000 });
    groupAsFound = (await toggle.getAttribute('aria-expanded')) === 'true';

    if (groupAsFound) await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator(`[data-testid="nav-group-${SIDEBAR_GROUP}"] a`).first()).toBeHidden();

    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const links = page.locator(`[data-testid="nav-group-${SIDEBAR_GROUP}"] a:visible`);
    expect(await links.count()).toBeGreaterThan(0);
    await attachEvidence(
      testInfo,
      'C05-sidebar-expand',
      page,
      `clicked [data-testid="sidebar-group-toggle-${SIDEBAR_GROUP}"] twice`,
      `aria-expanded=true; ${await links.count()} visible links restored`
    );
  });

  // C06–C17: one browser navigation per verified route. Console + response
  // listeners are installed before the goto so the whole load is observed.
  for (const [index, [slug, route]] of ROUTES.entries()) {
    test(`C${index + 6} route ${route} renders without 404/500/429 or console errors @smoke`, async (
      { page },
      testInfo
    ) => {
      const consoleErrors: string[] = [];
      const badResponses: string[] = [];
      page.on('console', (msg) => {
        if (msg.type() === 'error' && !isKnownConsoleNoise(msg.text())) consoleErrors.push(msg.text());
      });
      page.on('pageerror', (err) => {
        if (!isKnownConsoleNoise(err.message)) consoleErrors.push(`UNCAUGHT: ${err.message}`);
      });
      page.on('response', (resp) => {
        const error = appResponseError(resp);
        if (error) badResponses.push(error);
      });

      await session.gotoRoute(page, route);
      await attachEvidence(
        testInfo,
        `route-${slug}`,
        page,
        `page.goto(${route})`,
        `main[role="main"] visible, no route-suspense-fallback; app response errors: ${badResponses.join(' | ') || 'none'}`
      );
      expect(badResponses, `no 404/500/429 while loading ${route}`).toEqual([]);
      expect(consoleErrors, `no console errors while loading ${route}`).toEqual([]);
    });
  }
});
