// REQ-L1-081-THEME sibling feature — System & Workspace Banners (E2E lifecycle)
import { test, expect } from '@playwright/test';
import { loginAsAdmin } from '../helpers/auth';

test.describe('System & Workspace Banners', () => {
  test('admin sets a global banner, a member sees and dismisses it, it reappears on a fresh login', async ({
    page,
    browser,
  }) => {
    // Two full logins, several navigations and a second browser context —
    // see waterkettle-fullblown.spec.ts for the same pattern on multi-step flows.
    test.setTimeout(120_000);

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

    // Close the first context before opening a second one. Two live Chromium
    // contexts concurrently hammering the Vite dev server's unbundled-module
    // endpoint exhausted this host's resources (net::ERR_INSUFFICIENT_RESOURCES)
    // during local verification — an environment resource ceiling, not a product
    // behavior under test, since a "fresh login" scenario has no reason to keep
    // the old session's renderer alive anyway.
    await page.context().close();

    // 6. A fresh browser context (simulating "next login") sees it again.
    const freshContext = await browser.newContext();
    const freshPage = await freshContext.newPage();
    await loginAsAdmin(freshPage);
    await freshPage.goto('/');
    await expect(freshPage.getByTestId('banner-global')).toBeVisible();

    // 7. Clean up: disable the banner so this test is repeatable. Reuses the
    // fresh context (also logged in as admin) instead of opening a third one,
    // for the same resource-footprint reason as above.
    await freshPage.goto('/system-settings?tab=administration');
    await freshPage.getByTestId('banner-enabled-toggle').uncheck();
    await freshPage.getByTestId('banner-save-button').click();
    await expect(freshPage.getByText(/Saved\.|Gespeichert\./)).toBeVisible();
    await freshContext.close();
  });
});
