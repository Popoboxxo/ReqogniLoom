// REQ-L2-RF-004, REQ-L3-RF004-001/002/003: Architecture editor (CRUD, markdown, linked reqs)
import { test, expect, type Page } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, createIsolatedWorkspace } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

// "+ New" only opens an inline quick-create form (title input + Create/Cancel,
// Create disabled until a title is entered); the full editor (arch-title etc.)
// only renders after Create navigates to the created element's detail route.
async function createArchElementViaQuickForm(page: Page, title = 'E2E Arch Element'): Promise<void> {
  await page.locator('[data-testid="create-arch-btn"]').click();
  await page.locator('[data-testid="arch-new-title-input"]').fill(title);
  await page.locator('[data-testid="arch-new-save-btn"]').click();
  await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
}

test.describe('[COMP-RF-004] ArchitectureEditors', () => {
  test.beforeEach(async ({ page }) => {
    // Each test gets its own empty workspace so architecture-root creation
    // (invariant [I5]: one root per workspace) never collides across specs.
    const token = await getAuthToken();
    const workspaceId = await createIsolatedWorkspace(token);
    await setWorkspaceId(page, workspaceId);
    await loginAsAdmin(page);
  });

  test('[REQ-L3-RF004-001] element-type dropdown and delete confirmation dialog work', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await createArchElementViaQuickForm(page);

    // REQ-006/D5: element type is now a free-text input with autocomplete
    // suggestions (types can be extended freely), not a fixed <select>.
    const typeInput = page.locator('[data-testid="arch-element-type-select"]');
    await expect(typeInput).toBeVisible();
    await typeInput.fill('Interface');
    await expect(typeInput).toHaveValue('Interface');

    // Delete button is visible
    const deleteBtn = page.locator('[data-testid="arch-delete-btn"]');
    await expect(deleteBtn).toBeVisible();

    // Clicking delete must show the confirmation dialog
    await deleteBtn.click();
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 4000 });
    await expect(page.locator('[data-testid="confirm-delete-btn"]')).toBeVisible();

    // Cancel the dialog so we don't leave dangling state
    await page.locator('[role="dialog"] button', { hasText: /cancel|abbrechen/i }).click();
    await expect(page.locator('[role="dialog"]')).toBeHidden({ timeout: 4000 });
  });

  test('[REQ-L3-RF004-002] description field with markdown preview toggle is present', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await createArchElementViaQuickForm(page);

    // Markdown toggle controls exist for the description field
    const previewBtn = page.locator('[data-testid="md-preview-btn"]').first();
    const editBtn = page.locator('[data-testid="md-edit-btn"]').first();
    await expect(previewBtn).toBeVisible();
    await expect(editBtn).toBeVisible();

    // Edit mode reveals a textarea
    await editBtn.click();
    await expect(page.locator('textarea').first()).toBeVisible({ timeout: 4000 });
  });

  test('[REQ-L3-RF004-003] linked-requirements sidebar is rendered (empty state ok)', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await createArchElementViaQuickForm(page);

    // Linked-requirements panel must be rendered
    const panel = page.locator('[data-testid="arch-linked-reqs-panel"]');
    await expect(panel).toBeVisible({ timeout: 6000 });

    // Either has linked items list OR shows "none" message — both are valid
    const panelText = await panel.innerText();
    expect(panelText.length).toBeGreaterThan(0);
  });

  test('bundle export panel does not fetch on view load, only on activation', async ({ page }) => {
    const bundleRequests: string[] = [];
    page.on('request', (req) => {
      if (req.url().includes('/requirement-bundle/')) bundleRequests.push(req.url());
    });

    await page.goto(`${FRONTEND_URL}/architecture`);
    await createArchElementViaQuickForm(page);

    // View is open, element selected — no bundle request yet.
    await page.locator('[data-testid="page-header-overflow-trigger"]').click();
    await expect(page.locator('[data-testid="arch-bundle-export-overflow-btn"]')).toBeVisible();
    expect(bundleRequests).toHaveLength(0);

    await page.locator('[data-testid="arch-bundle-export-overflow-btn"]').click();
    await expect(page.locator('[data-testid="arch-bundle-export-dialog"]')).toBeVisible();
    // Dialog open, but still no fetch until the user submits.
    expect(bundleRequests).toHaveLength(0);

    await page.locator('[data-testid="arch-bundle-export-submit"]').click();
    await expect(page.locator('[data-testid="arch-bundle-export-result"]')).toBeVisible({ timeout: 15000 });
    expect(bundleRequests.length).toBeGreaterThan(0);
  });
});
