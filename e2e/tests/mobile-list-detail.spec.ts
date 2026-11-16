// @mobile — list → detail → back across the artifact routes (plan M5, REQ-209).
// The regression: on a phone, opening a detail rendered the two-column
// desktop branch instead of replacing the list. Each route is its own test so
// one failing route can never hide the others; every route asserts a seeded row
// (the /baselines route seeds one via the API) instead of skipping on emptiness.
import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  createIsolatedWorkspace,
  setWorkspaceId,
} from '../helpers/auth';
import { LIST_ROW_SELECTOR, openFirstListItem } from '../helpers/mobile';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

const ROUTES = [
  '/requirements',
  '/needs',
  '/risks',
  '/issues',
  '/adrs',
  '/testcases',
  '/glossary',
  '/baselines',
];

test.describe('@mobile list/detail flow', () => {
  for (const route of ROUTES) {
    test(`${route}: detail replaces the list and the back step returns`, { tag: '@mobile' }, async ({ page, request }: { page: Page; request: APIRequestContext }) => {
      // /baselines is the only route with no seed rows in a fresh CI DB. Seed one
      // into an isolated workspace so the list→detail→back flow has a
      // deterministic target instead of a false-green skip. The API POST pattern
      // mirrors baselines-tags.spec.ts (default/standard preset enables baselines).
      if (route === '/baselines') {
        const token = await getAuthToken();
        const workspaceId = await createIsolatedWorkspace(token);
        const baselineName = `e2e-mobile-baseline-${Date.now()}`;
        const seed = await request.post(`${BACKEND_URL}/api/v1/baselines/`, {
          headers: { Authorization: `Bearer ${token}` },
          data: { workspace_id: workspaceId, name: baselineName, scope: 'project' },
        });
        expect(seed.ok(), `baseline seed failed: ${seed.status()} ${await seed.text()}`).toBeTruthy();
        // addInitScript applies on the next navigation — point the app at the
        // seeded workspace before login navigates.
        await setWorkspaceId(page, workspaceId);
      }

      await loginAsAdmin(page);
      await page.goto(route);
      await expect(page.getByTestId('splitview-list')).toBeVisible();

      const rows = page.locator(LIST_ROW_SELECTOR);
      await rows.first().waitFor({ state: 'visible', timeout: 4000 }).catch(() => undefined);
      // Deterministic precondition: every route must expose at least one row.
      // /baselines gets one from the API seed above — no environment-dependent
      // skip that reports green while the detail flow goes untested.
      expect(await rows.count(), `${route}: expected at least one seeded list row`).toBeGreaterThan(0);

      await openFirstListItem(page);
      await expect(page.getByTestId('splitview-list')).toBeHidden();
      await expect(page.getByTestId('splitview-detail')).toBeVisible();

      await page.getByTestId('splitview-back').click();
      await expect(page.getByTestId('splitview-list')).toBeVisible();
      await expect(page.getByTestId('splitview-detail')).toBeHidden();
    });
  }
});
