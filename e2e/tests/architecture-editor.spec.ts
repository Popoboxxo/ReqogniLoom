// REQ-L2-RF-004, REQ-L3-RF004-001/002/003: Architecture editor (CRUD, markdown, linked reqs)
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[COMP-RF-004] ArchitectureEditors', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L3-RF004-001] element-type dropdown and delete confirmation dialog work', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await page.locator('[data-testid="create-arch-btn"]').click();
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 12000 });

    // Element-type dropdown is visible with the 5 ADR-L3-RF-007 options
    const typeSelect = page.locator('[data-testid="arch-element-type"]');
    await expect(typeSelect).toBeVisible();
    const options = await typeSelect.locator('option').allTextContents();
    expect(options).toEqual(
      expect.arrayContaining(['Component', 'Interface', 'Subsystem', 'Layer', 'Module'])
    );

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
    await page.locator('[data-testid="create-arch-btn"]').click();
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 12000 });

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
    await page.locator('[data-testid="create-arch-btn"]').click();
    await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 12000 });

    // Linked-requirements panel must be rendered
    const panel = page.locator('[data-testid="arch-linked-reqs-panel"]');
    await expect(panel).toBeVisible({ timeout: 6000 });

    // Either has linked items list OR shows "none" message — both are valid
    const panelText = await panel.innerText();
    expect(panelText.length).toBeGreaterThan(0);
  });
});
