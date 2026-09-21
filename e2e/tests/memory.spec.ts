// RFC #1002 (PR D): Workspace memory hub ("Gedächtnis"), artifact memory panel
// and the profile self-service list — the three UI surfaces of the unified
// memory REST API.
import { test, expect, type Page } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

async function createRequirementViaQuickForm(page: Page, title: string): Promise<void> {
  await page.locator('[data-testid="create-req-btn"]').click();
  await page.locator('[data-testid="req-new-title-input"]').fill(title);
  await page.locator('[data-testid="req-new-save-btn"]').click();
  await expect(page.locator('[data-testid="artifact-field-title"]')).toBeVisible({ timeout: 10000 });
}

test.describe('[RFC #1002] Workspace memory page (Gedächtnis)', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('opens the page and switches between the three scope tabs', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/memory`);

    await expect(page.locator('[data-testid="memory-page"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="memory-tab-workspace"]')).toHaveAttribute(
      'aria-selected',
      'true'
    );

    await page.locator('[data-testid="memory-tab-user"]').click();
    await expect(page.locator('[data-testid="memory-tab-user"]')).toHaveAttribute(
      'aria-selected',
      'true'
    );

    await page.locator('[data-testid="memory-tab-artifact"]').click();
    await expect(page.locator('[data-testid="memory-artifact-select"]')).toBeVisible();
  });

  test('semantic search shows the result container', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/memory`);
    await expect(page.locator('[data-testid="memory-page"]')).toBeVisible({ timeout: 10000 });

    await page.locator('[data-testid="memory-search-input"]').fill('Wasser');
    await page.locator('[data-testid="memory-search-submit"]').click();

    // Either hits or the explicit empty state — both prove the search round-trip.
    await expect(page.locator('[data-testid="memory-search-results"]')).toBeVisible({
      timeout: 15000,
    });
  });

  test('adds a team fact, then forgets it', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/memory`);
    await expect(page.locator('[data-testid="memory-page"]')).toBeVisible({ timeout: 10000 });

    const content = `E2E memory fact ${Date.now()}`;

    await page.locator('[data-testid="memory-add-fact-btn"]').click();
    await expect(page.locator('[data-testid="memory-add-fact-dialog"]')).toBeVisible();
    await page.locator('[data-testid="memory-add-content"]').fill(content);
    await page.locator('[data-testid="memory-add-submit"]').click();

    await expect(page.getByText(content)).toBeVisible({ timeout: 15000 });

    const row = page.locator('[data-testid^="memory-row-"]').filter({ hasText: content });
    await row.locator('[data-testid^="memory-forget-"]').click();
    await page.locator('[data-testid="memory-forget-confirm-confirm"]').click();

    await expect(page.getByText(content)).toHaveCount(0, { timeout: 15000 });
  });
});

test.describe('[RFC #1002] Artifact memory panel', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('lists artifact facts and creates one from the requirement detail page', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page, `E2E Memory Artifact ${Date.now()}`);

    const panel = page.locator('[data-testid="artifact-memory-panel"]');
    await expect(panel).toBeVisible({ timeout: 10000 });
    await expect(panel.locator('[data-testid="artifact-memory-count"]')).toBeVisible();

    const content = `E2E artifact fact ${Date.now()}`;
    await panel.locator('[data-testid="artifact-memory-add-btn"]').click();
    await expect(page.locator('[data-testid="memory-add-fact-dialog"]')).toBeVisible();
    await page.locator('[data-testid="memory-add-content"]').fill(content);
    await page.locator('[data-testid="memory-add-submit"]').click();

    await expect(page.getByText(content)).toBeVisible({ timeout: 15000 });

    // The panel is admin-authenticated here, so the per-row forget action is present.
    const row = panel.locator('[data-testid^="artifact-memory-row-"]').filter({ hasText: content });
    await row.locator('[data-testid^="artifact-memory-forget-"]').click();
    await page.locator('[data-testid="artifact-memory-forget-confirm-confirm"]').click();

    await expect(page.getByText(content)).toHaveCount(0, { timeout: 15000 });
  });
});

test.describe('[RFC #1002] Profile memory self-service list', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('renders the own-facts list or the empty state with the purge control', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/profile`);

    const section = page.locator('[data-testid="memory-self-service-section"]');
    await expect(section).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="memory-self-service-count"]')).toBeVisible();
    await expect(page.locator('[data-testid="memory-self-service-delete-btn"]')).toBeVisible();

    // Exactly one of the two states must render once loading has settled.
    await expect(
      page.locator('[data-testid="memory-self-service-list"], [data-testid="memory-self-service-empty"]')
    ).toBeVisible({ timeout: 10000 });
  });
});
