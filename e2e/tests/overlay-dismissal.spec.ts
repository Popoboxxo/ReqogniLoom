// Issue #985 — Overlays must be dismissible from the keyboard.
//
// Two overlays in beta.12 could not be closed with Escape, and the
// notification popover additionally ignored a click outside. Both trapped the
// user in a state they did not ask for; the system-health dialog in particular
// left keyboard-only users with no exit at all.
//
// These are regression pins, not exploratory tests: each one asserts the exact
// behaviour that was reported broken, so the class cannot come back.
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[REQ-L1-081] Overlay dismissal (issue #985)', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('notification popover closes on Escape', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/`);

    const toggle = page.locator('[data-testid="notification-bell-toggle"]');
    const dropdown = page.locator('[data-testid="notification-bell-dropdown"]');

    await toggle.click();
    await expect(dropdown).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(dropdown).toBeHidden();

    // Focus must not be lost to the document body: the trigger is the
    // element the user came from, so it is where focus belongs.
    await expect(toggle).toBeFocused();
  });

  test('notification popover closes on an outside click', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/`);

    const toggle = page.locator('[data-testid="notification-bell-toggle"]');
    const dropdown = page.locator('[data-testid="notification-bell-dropdown"]');

    await toggle.click();
    await expect(dropdown).toBeVisible();

    // A point on the page body, clear of both the sidebar and the popover.
    await page.mouse.click(900, 600);
    await expect(dropdown).toBeHidden();
  });

  test('system health dialog closes on Escape', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);

    await page.locator('[data-testid="system-health-open-btn"]').click();

    const overlay = page.locator('[data-testid="system-health-dialog-overlay"]');
    await expect(overlay).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(overlay).toBeHidden();
  });
  test('system health dialog closes on an outside click', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);

    await page.locator('[data-testid="system-health-open-btn"]').click();

    const overlay = page.locator('[data-testid="system-health-dialog-overlay"]');
    await expect(overlay).toBeVisible();

    // The overlay is the scrim: a click on it (not on the panel) dismisses.
    // This is the half of issue #985 that was broken — before the fix the
    // dialog ignored outside clicks entirely and stayed on top of the page.
    await overlay.click({ position: { x: 5, y: 5 } });
    await expect(overlay).toBeHidden();
  });

  test('system health dialog keeps focus restoration on the Escape path', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);

    const openButton = page.locator('[data-testid="system-health-open-btn"]');
    await openButton.click();

    const overlay = page.locator('[data-testid="system-health-dialog-overlay"]');
    await expect(overlay).toBeVisible();

    await page.keyboard.press('Escape');
    await expect(overlay).toBeHidden();

    // Issue #991: focus must return to the trigger, not be dropped to <body>.
    await expect(openButton).toBeFocused();
  });

  test('system health dialog keeps focus restoration on the pointer path', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/system-settings`);

    const openButton = page.locator('[data-testid="system-health-open-btn"]');
    await openButton.click();

    const overlay = page.locator('[data-testid="system-health-dialog-overlay"]');
    await expect(overlay).toBeVisible();

    // Dismiss via the scrim; the same restore must hold (#991).
    await overlay.click({ position: { x: 5, y: 5 } });
    await expect(overlay).toBeHidden();

    await expect(openButton).toBeFocused();
  });
});
