/**
 * Plan E / WP E3.8 (#1308) — TOTP two-factor login end-to-end.
 *
 * Uses the dedicated staff account `e2e-mfa` that `seed_demo` creates only when
 * `E2E_MFA_PASSWORD` is set (review finding RB-12). It must never enroll the
 * shared `admin` account: parallel shards would then all hit the second step.
 *
 * Flow: enroll -> confirm -> logout -> login with TOTP -> recovery code ->
 * disable. The TOTP replay guard means each code is single-use per step, so the
 * test waits for the next 30 s window between factor uses.
 */

import { test, expect, type Page } from '@playwright/test';
import {
  currentTotpStep,
  generateTotp,
  waitForStepAfter,
} from '../helpers/totp';
import { setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const MFA_USERNAME = 'e2e-mfa';
const MFA_PASSWORD = process.env.E2E_MFA_PASSWORD;

async function submitPasswordStep(page: Page): Promise<void> {
  await page.goto(`${FRONTEND_URL}/login`);
  await page.fill('#username-input', MFA_USERNAME);
  await page.fill('#password-input', MFA_PASSWORD ?? '');
  await page.click('button[type="submit"]');
}

async function logout(page: Page): Promise<void> {
  await page.click('[data-testid="nav-logout"]');
  await page.waitForURL(/\/login/, { timeout: 15_000 });
}

test.describe('MFA TOTP', () => {
  test.skip(
    !MFA_PASSWORD,
    'E2E_MFA_PASSWORD is not set — seed_demo only creates the e2e-mfa user when it is.'
  );

  // Two replay-safe waits of up to 30 s each plus the UI round trips.
  test.setTimeout(180_000);

  test('[#1308] enroll, login with code and recovery code, disable', async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);

    // --- 1. Password login, then enroll the TOTP device ---------------- //
    await submitPasswordStep(page);
    await page.waitForURL((url) => !url.pathname.includes('/login'), {
      timeout: 15_000,
    });

    await page.goto(`${FRONTEND_URL}/profile`);
    await expect(page.locator('[data-testid="mfa-section"]')).toBeVisible({
      timeout: 15_000,
    });

    await page.click('[data-testid="mfa-enroll-btn"]');
    const secret = (
      (await page.locator('[data-testid="mfa-secret"]').textContent()) ?? ''
    ).trim();
    expect(secret.length).toBeGreaterThan(15);

    const confirmStep = currentTotpStep();
    await page.fill('[data-testid="mfa-confirm-code-input"]', generateTotp(secret));
    await page.click('[data-testid="mfa-confirm-btn"]');

    const recoveryBlock = page.locator('[data-testid="mfa-recovery-codes"]');
    await expect(recoveryBlock).toBeVisible({ timeout: 15_000 });
    const recoveryCodes = await recoveryBlock.locator('li').allTextContents();
    expect(recoveryCodes.length).toBeGreaterThan(0);

    // --- 2. Logout, login with a TOTP code ----------------------------- //
    await logout(page);

    await submitPasswordStep(page);
    await expect(page.locator('[data-testid="login-mfa-step"]')).toBeVisible({
      timeout: 15_000,
    });

    const loginStep = await waitForStepAfter(confirmStep);
    await page.fill('[data-testid="login-mfa-code-input"]', generateTotp(secret));
    await page.click('[data-testid="login-mfa-submit"]');
    await page.waitForURL((url) => !url.pathname.includes('/login'), {
      timeout: 15_000,
    });

    // --- 3. Logout, login with a recovery code ------------------------- //
    await logout(page);

    await submitPasswordStep(page);
    await page.click('[data-testid="login-mfa-recovery-toggle"]');
    await page.fill('[data-testid="login-mfa-recovery-input"]', recoveryCodes[0].trim());
    await page.click('[data-testid="login-mfa-submit"]');
    await page.waitForURL((url) => !url.pathname.includes('/login'), {
      timeout: 15_000,
    });

    // --- 4. Disable the factor (password + fresh code) ----------------- //
    await page.goto(`${FRONTEND_URL}/profile`);
    await page.click('[data-testid="mfa-disable-btn"]');
    await page.fill('[data-testid="mfa-disable-password-input"]', MFA_PASSWORD ?? '');
    await waitForStepAfter(loginStep);
    await page.fill('[data-testid="mfa-disable-code-input"]', generateTotp(secret));
    await page.click('[data-testid="mfa-disable-submit"]');

    // Back to "not set up": the enroll action is available again.
    await expect(page.locator('[data-testid="mfa-enroll-btn"]')).toBeVisible({
      timeout: 15_000,
    });
  });
});
