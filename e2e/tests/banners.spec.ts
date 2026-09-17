// REQ-L1-081-THEME sibling feature — System & Workspace Banners (E2E lifecycle)
import { test, expect, type APIRequestContext } from '@playwright/test';
import { loginAsAdmin, getAuthToken } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

// Mirrors deleteRequirement's shape in review-workflow.spec.ts: a plain API
// call, no UI dependency, so it can run in a `finally` regardless of which
// page/context (if any) is still valid when an earlier step throws. The
// backend defaults every field but `enabled` (see admin_ops/banner_rest.py
// _parse_write_payload), so this single field is enough to fully disable it.
async function disableGlobalBanner(request: APIRequestContext, token: string): Promise<void> {
  await request.put(`${BACKEND_URL}/api/v1/admin/banners/global/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { enabled: false },
  });
}

test.describe('System & Workspace Banners', () => {
  test('admin sets a global banner, a member sees and dismisses it, it reappears on a fresh login', async ({
    page,
    browser,
    request,
  }) => {
    // Two full logins, several navigations and a second browser context —
    // see waterkettle-fullblown.spec.ts for the same pattern on multi-step flows.
    test.setTimeout(120_000);

    // Fetched independently of any page/context state, so cleanup in the
    // `finally` below can always authenticate even if step 1's UI login
    // itself is what failed.
    const token = await getAuthToken();

    // BannerStack is mounted globally in NavigationShell.tsx and renders on
    // every authenticated route — if this test throws after enabling the
    // banner and before disabling it again, every other E2E spec touching
    // any page (most notably visual-regression.spec.ts's screenshot diffs)
    // would be polluted by a stray "Scheduled maintenance tonight" banner
    // until someone manually disabled it. Guard steps 2-6 with try/finally,
    // matching review-workflow.spec.ts / hermes-bugfix-campaign.spec.ts /
    // visual-regression.spec.ts's own state-mutation convention.
    try {
      // 1. Log in as the demo admin.
      await loginAsAdmin(page);

      // 2. Navigate to System Settings -> administration tab.
      await page.goto('/system-settings?tab=administration');
      await expect(page.getByTestId('banner-section')).toBeVisible();

      // 3. Configure and enable a global banner.
      await page.getByTestId('banner-message-input').fill('Scheduled maintenance tonight');
      await page.getByTestId('banner-level-warning').check();
      await page.getByTestId('banner-enabled-toggle').check();
      await page.getByTestId('banner-save-button').click();
      // Locale-independent: the app defaults to the browser's locale (de or en)
      // — see canvas-diagram.spec.ts / mermaid-diagram.spec.ts for the same pattern.
      await expect(page.getByText(/Saved\.|Gespeichert\./)).toBeVisible();

      // 4. Navigate to the dashboard (or any authenticated route) and see the banner.
      await page.goto('/');
      await expect(page.getByTestId('banner-global')).toBeVisible();
      await expect(page.getByTestId('banner-global')).toContainText(
        'Scheduled maintenance tonight'
      );

      // 5. Dismiss it — it disappears within the same session, even after reload.
      await page.getByTestId('banner-global-dismiss').click();
      await expect(page.getByTestId('banner-global')).not.toBeVisible();
      await page.reload();
      await expect(page.getByTestId('banner-global')).not.toBeVisible();

      // Close the first context before opening a second one. Two live
      // Chromium contexts concurrently hammering the Vite dev server's
      // unbundled-module endpoint exhausted this host's resources
      // (net::ERR_INSUFFICIENT_RESOURCES) during local verification — an
      // environment resource ceiling, not a product behavior under test,
      // since a "fresh login" scenario has no reason to keep the old
      // session's renderer alive anyway.
      await page.context().close();

      // 6. A fresh browser context (simulating "next login") sees it again.
      const freshContext = await browser.newContext();
      const freshPage = await freshContext.newPage();
      await loginAsAdmin(freshPage);
      await freshPage.goto('/');
      await expect(freshPage.getByTestId('banner-global')).toBeVisible();
      await freshContext.close();
    } finally {
      // 7. Clean up: disable the banner via the API so this test — and every
      // other spec that renders any authenticated page — stays repeatable
      // even if an assertion above threw.
      await disableGlobalBanner(request, token);
    }
  });
});
