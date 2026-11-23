// Smoke suite — requirements & sibling editors (themes 3+4, checks C18–C24).
//
// All checks are tagged `@smoke`. The only check that persists anything is
// C20; it deletes its own requirement in a `finally` block and asserts the
// cleanup status, so the shared seeded workspace is left as it was found.
// One full-page screenshot is attached by C24. Shared setup plumbing lives in
// helpers/smoke-setup.ts; every check below still performs real browser actions.
import { test, expect } from '@playwright/test';
import {
  setWorkspaceId,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';
import { collapseInspector } from '../helpers/inspector';
import {
  attachEvidence,
  BACKEND_URL,
  createSmokeSession,
  expectOk,
} from '../helpers/smoke-setup';

const session = createSmokeSession();

test.describe('Smoke — requirements @smoke', () => {
  test.beforeAll(async () => {
    await session.obtain();
  });

  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await session.apply(page);
  });

  test('C18 requirements list exposes create and search controls @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/requirements');
    await expect(page.locator('[data-testid="create-req-btn"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="req-list-search-input"]')).toBeVisible({ timeout: 10000 });
    await attachEvidence(
      testInfo,
      'C18-requirements-list',
      page,
      'navigated to /requirements',
      'create-req-btn + req-list-search-input visible'
    );
  });

  test('C19 create dialog opens and refuses an empty title @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/requirements');
    const trigger = page.locator('[data-testid="create-req-btn"]');
    const dialog = page.locator('[data-testid="req-new-dialog"]');
    await trigger.click();
    await expect(dialog).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="req-new-title-input"]')).toBeVisible({ timeout: 10000 });

    // Both form paths (definition-driven ArtifactForm and fallback form) render
    // the same required-title error; accept either test id.
    const titleError = page
      .locator('[data-testid="req-new-title-input-error"]')
      .or(page.locator('[data-testid="new-req-title-error"]'));
    await expect(titleError).toHaveCount(0);
    await page.locator('[data-testid="req-new-save-btn"]').click();
    await expect(titleError).toBeVisible({ timeout: 8000 });
    await attachEvidence(
      testInfo,
      'C19-empty-validation',
      page,
      'clicked create-req-btn then req-new-save-btn with an empty title',
      'req-new-dialog visible + required-title error visible'
    );
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test('C20 entering a title opens the detail editor with an editable title @smoke', async (
    { page, request },
    testInfo
  ) => {
    await session.gotoRoute(page, '/requirements');
    const title = `E2E smoke requirement ${Date.now()}`;
    let createdId: string | undefined;
    try {
      await page.locator('[data-testid="create-req-btn"]').click();
      await page.locator('[data-testid="req-new-title-input"]').fill(title);
      // Capture the id from the UI's OWN create response: cleanup must never
      // depend on the detail route having navigated (security note S-S02).
      const createResponsePromise = page.waitForResponse(
        (resp) =>
          resp.request().method() === 'POST' &&
          new URL(resp.url()).pathname === '/api/v1/requirements/',
        { timeout: 15000 }
      );
      await page.locator('[data-testid="req-new-save-btn"]').click();
      const createBody = await (await createResponsePromise).json().catch(() => ({}));
      createdId = typeof createBody?.id === 'string' ? createBody.id : undefined;

      const field = page.locator('[data-testid="artifact-field-title"]');
      await expect(field).toBeVisible({ timeout: 15000 });
      // URL match stays as an additional source, never a prerequisite for
      // cleanup; the detail-view assertion above is unchanged.
      createdId = createdId ?? page.url().match(/\/requirements\/([0-9a-f-]+)/)?.[1];
      // #1762 (M1): at 1280 px the inspector opens as a sheet over the detail
      // area and marks it inert; a fill() on an inert input silently keeps the
      // old value. Collapse it first, exactly like requirement-editor.spec.ts.
      await collapseInspector(page);
      const edited = `${title} (edited)`;
      await field.fill(edited);
      await expect(field).toHaveValue(edited, { timeout: 8000 });

      await attachEvidence(
        testInfo,
        'C20-detail-title',
        page,
        'created via req-new-save-btn, collapsed inspector, filled artifact-field-title',
        `artifact-field-title = "${edited}"`
      );
    } finally {
      if (createdId) {
        await expectOk(
          await request.delete(`${BACKEND_URL}/api/v1/requirements/${createdId}/`, {
            headers: { Authorization: `Bearer ${session.token}` },
            data: { change_reason: 'E2E smoke cleanup' },
          }),
          `C20 cleanup DELETE /requirements/${createdId}/`
        );
      }
    }
  });

  test('C21 list search filters without crashing @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/requirements');
    const search = page.locator('[data-testid="req-list-search-input"]');
    await expect(search).toBeVisible({ timeout: 10000 });
    const needle = `no-such-requirement-${Date.now()}`;
    await search.fill(needle);
    await expect(search).toHaveValue(needle);
    // Three states exist: rows (`req-list-tree`), genuinely empty workspace
    // (`req-list-empty`) and "rows exist but none match" (`req-list-no-match`,
    // RequirementList.tsx:698) — the last one is what a nonsense filter yields.
    await expect(
      page
        .locator('[data-testid="req-list-tree"]')
        .or(page.locator('[data-testid="req-list-empty"]'))
        .or(page.locator('[data-testid="req-list-no-match"]'))
        .first()
    ).toBeVisible({ timeout: 10000 });
    await expect(page.locator('main[role="main"]')).toBeVisible();
    const body = await page.locator('body').innerText();
    expect(body).not.toContain('TypeError');
    await attachEvidence(
      testInfo,
      'C21-list-search',
      page,
      `filled req-list-search-input with "${needle}"`,
      'search value retained; list/empty-state still rendered; no TypeError'
    );
  });

  test('C22 table view toggles on and back to list @smoke', async ({ page }, testInfo) => {
    // The per-user view preference is shared with 74 other specs: restore it in
    // `finally` whenever the table toggle was actually clicked, so a failed
    // table assertion or evidence attachment cannot leak "table" mode.
    let viewWriteHappened = false;
    try {
      await session.gotoRoute(page, '/requirements');
      await expect(page.locator('[data-testid="req-view-toggle-list"]')).toHaveAttribute(
        'aria-pressed',
        'true'
      );
      await page.locator('[data-testid="req-view-toggle-table"]').click();
      viewWriteHappened = true;
      await expect(page.locator('[data-testid="artifact-table-view"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="artifact-table"]')).toBeVisible({ timeout: 10000 });
      await attachEvidence(
        testInfo,
        'C22-table-view',
        page,
        'clicked req-view-toggle-table',
        'artifact-table-view + artifact-table visible'
      );
    } finally {
      if (viewWriteHappened) {
        // Restore in-app, not through the API, and assert the restored state.
        await page.locator('[data-testid="req-view-toggle-list"]').click();
        await expect(page.locator('[data-testid="req-view-toggle-list"]')).toHaveAttribute(
          'aria-pressed',
          'true'
        );
      }
    }
  });

  test('C23 need create form opens @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/needs');
    const trigger = page.locator('[data-testid="create-need-btn"]');
    const dialog = page.locator('[data-testid="need-new-dialog"]');
    await expect(trigger).toBeVisible({ timeout: 10000 });
    await trigger.click();
    await expect(dialog).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="need-new-title-input"]')).toBeVisible({ timeout: 8000 });
    await attachEvidence(
      testInfo,
      'C23-need-create',
      page,
      'clicked create-need-btn',
      'need-new-dialog + need-new-title-input visible'
    );
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test('C24 ADR create form opens @smoke', async ({ page }, testInfo) => {
    await session.gotoRoute(page, '/adrs');
    const trigger = page.locator('[data-testid="create-adr-btn"]');
    const dialog = page.locator('[data-testid="adr-create-dialog"]');
    await expect(trigger).toBeVisible({ timeout: 10000 });
    await trigger.click();
    await expect(page.locator('[data-testid="adr-new-title-input"]')).toBeVisible({ timeout: 10000 });
    await attachEvidence(
      testInfo,
      'C24-adr-create',
      page,
      'clicked create-adr-btn',
      'adr-new-title-input visible'
    );
    // One full-page screenshot per file, taken on the light ADR list.
    await testInfo.attach('smoke-requirements-fullpage', {
      body: await page.screenshot({ fullPage: true }),
      contentType: 'image/png',
    });
    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });
});
