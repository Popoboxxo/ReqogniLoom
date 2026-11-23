// Smoke suite — domain routes (theme 4, checks C25–C31).
//
// All checks are tagged `@smoke`. Every dialog is opened and closed again
// without saving, so this file does not mutate the shared seeded workspace.
// One full-page screenshot is attached by C25. Shared setup plumbing lives in
// helpers/smoke-setup.ts; every check below still performs real browser actions.
import { test, expect } from '@playwright/test';
import { setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
import { attachEvidence, createSmokeSession } from '../helpers/smoke-setup';

const session = createSmokeSession();

test.describe('Smoke — domain routes @smoke', () => {
  test.beforeAll(async () => {
    await session.obtain();
  });

  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await session.apply(page);
  });

  test('C25 architecture route exposes create button @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/architecture');
    const create = page.locator('[data-testid="create-arch-btn"]');
    await expect(create).toBeVisible({ timeout: 10000 });
    await attachEvidence(
      testInfo,
      'C25-architecture',
      page,
      'navigated to /architecture',
      'create-arch-btn visible'
    );
    await testInfo.attach('smoke-domain-fullpage', {
      body: await page.screenshot({ fullPage: true }),
      contentType: 'image/png',
    });
  });

  test('C26 architecture empty-title validation explains the refusal @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/architecture');
    const trigger = page.locator('[data-testid="create-arch-btn"]');
    const dialog = page.locator('[data-testid="arch-new-dialog"]');
    await trigger.click();
    const title = page.locator('[data-testid="arch-new-title-input"]');
    const save = page.locator('[data-testid="arch-new-save-btn"]');
    const error = page.locator('[data-testid="arch-new-title-error"]');
    await expect(title).toBeFocused({ timeout: 8000 });
    await expect(save).toBeEnabled();
    await save.click();
    await expect(error).toBeVisible({ timeout: 8000 });
    await expect(title).toHaveAttribute('aria-invalid', 'true');
    await attachEvidence(
      testInfo,
      'C26-arch-validation',
      page,
      'clicked create-arch-btn then arch-new-save-btn with an empty title',
      'arch-new-title-error visible + input aria-invalid=true'
    );
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test('C27 traceability opens the create-trace-link dialog (no save) @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/traceability');
    const trigger = page.locator('[data-testid="tracelink-create-btn"]');
    const dialog = page.locator('[data-testid="create-trace-link-dialog"]');
    await expect(trigger).toBeVisible({ timeout: 10000 });
    await trigger.click();
    await expect(dialog).toBeVisible({ timeout: 8000 });
    await attachEvidence(
      testInfo,
      'C27-tracelink-dialog',
      page,
      'clicked tracelink-create-btn',
      'create-trace-link-dialog visible'
    );
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test('C28 testcases route opens the create form (no save) @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/testcases');
    await expect(page.locator('[data-testid="testcases-page"]')).toBeVisible({ timeout: 10000 });
    const trigger = page.locator('[data-testid="create-tc-btn"]');
    const dialog = page.locator('[data-testid="tc-create-dialog"]');
    await trigger.click();
    await expect(page.locator('[data-testid="tc-new-title-input"]')).toBeVisible({ timeout: 8000 });
    await attachEvidence(
      testInfo,
      'C28-testcase-create',
      page,
      'clicked create-tc-btn',
      'tc-new-title-input visible'
    );
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test('C29 test-runs route loads with its create control @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/test-runs');
    await expect(page.locator('[data-testid="testrun-create-btn"]')).toBeVisible({ timeout: 10000 });
    await attachEvidence(
      testInfo,
      'C29-test-runs',
      page,
      'navigated to /test-runs',
      'main[role="main"] + testrun-create-btn visible'
    );
  });

  test('C30 baselines route exposes create form or a clean empty state @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/baselines');
    await expect(page.locator('[data-testid="baselines-view"]')).toBeVisible({ timeout: 10000 });
    // Only the baselines view's OWN loading status is relevant: the shell also
    // mounts a permanent QS-banner status (and the hidden interview-widget live
    // region), so a page-wide `[role="status"]:visible` count can never reach 0.
    await expect(
      page.locator('[data-testid="baselines-view"] [role="status"]')
    ).toHaveCount(0, { timeout: 10000 });

    const create = page.locator('[data-testid="create-baseline-btn"]');
    let visible: string;
    if (await create.count()) {
      await create.click();
      await expect(page.locator('[data-testid="create-baseline-form"]')).toBeVisible({
        timeout: 8000,
      });
      visible = 'create-baseline-form visible';
    } else {
      // A regression that removes the create action while rows exist must NOT
      // pass this check: the genuine empty state carries its own test id.
      await expect(page.locator('[data-testid="baselines-empty"]')).toBeVisible({ timeout: 8000 });
      visible = 'baselines-empty visible (create action gated by active preset)';
    }
    await attachEvidence(
      testInfo,
      'C30-baselines',
      page,
      'navigated to /baselines' + (visible.startsWith('create') ? ' and clicked create-baseline-btn' : ''),
      visible
    );
  });

  test('C31 diagrams route opens the create-dialog (no editor) @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/diagrams');
    const trigger = page.locator('[data-testid="create-diagram-btn"]');
    const dialog = page.locator('[data-testid="create-diagram-dialog"]');
    await expect(trigger).toBeVisible({ timeout: 10000 });
    await trigger.click();
    await expect(dialog).toBeVisible({ timeout: 8000 });
    await expect(page.locator('[data-testid="diagram-name-input"]')).toBeVisible({ timeout: 8000 });
    // Nothing is created: no editor route is entered.
    expect(page.url()).not.toMatch(/\/diagrams\/[0-9a-f-]+\/(canvas|mermaid|graph)/);
    await attachEvidence(
      testInfo,
      'C31-diagram-dialog',
      page,
      'clicked create-diagram-btn',
      'create-diagram-dialog + diagram-name-input visible; no editor opened'
    );
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });
});
