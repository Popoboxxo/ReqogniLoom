// Issue #985 — the Dialog primitive must close on Escape regardless of where
// focus currently sits.
//
// This is the CI failure that #985's first fix attempt surfaced, pinned as its
// own regression test. The dialog used to handle Escape with a *bubble-phase*
// keydown listener on its container, so the key only worked when the keydown
// target was already inside the panel. On a settled desktop page that holds;
// while the panel is still mounting — which is what the CI runner reliably
// hits — `document.activeElement` is `body`, the container never sees the key,
// and Escape does nothing.
//
// The test therefore does NOT rely on the dialog having taken focus by itself,
// which is what made the original spec pass locally and fail in CI. It moves
// focus away first and only then presses Escape.
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[REQ-L1-081] Dialog Escape robustness (issue #985)', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('Escape closes the dialog even when focus sits outside the panel', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);

    await page.locator('[data-testid="system-health-open-btn"]').click();

    const overlay = page.locator('[data-testid="system-health-dialog-overlay"]');
    await expect(overlay).toBeVisible();

    // Reproduce the state the CI runner was in: focus deliberately parked on
    // the document body, i.e. outside the panel. A container-scoped keydown
    // listener cannot see this key at all.
    await page.evaluate(() => {
      (document.activeElement as HTMLElement | null)?.blur?.();
      document.body.focus?.();
    });

    await page.keyboard.press('Escape');
    await expect(overlay).toBeHidden();
  });

  test('Escape closes the dialog even when the panel never took focus', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);

    await page.locator('[data-testid="system-health-open-btn"]').click();

    const overlay = page.locator('[data-testid="system-health-dialog-overlay"]');
    await expect(overlay).toBeVisible();

    // Same idea, one step harder: no blur at all, just assert the panel is
    // not the active element and then press Escape. If focus did land inside
    // the panel this test still passes — it only fails when the close depends
    // on the panel having focus.
    await page.keyboard.press('Escape');
    await expect(overlay).toBeHidden();
  });
});
