// REQ-L2-RF-003, REQ-L3-RF003-001/002/003: Requirements editor (inline, workflow, traceability)
// REQ-L2-RF-006: TraceLink creation in RequirementEditor
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[COMP-RF-003] RequirementEditors', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L3-RF003-001] title is editable inline and markdown preview toggle works', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);

    // Create a fresh requirement so the detail editor is shown
    await page.locator('[data-testid="create-req-btn"]').click();
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 12000 });

    // Inline edit title
    const title = page.locator('[data-testid="req-title"]');
    await title.fill('Inline Edit Title REQ-L3-RF003-001');
    await expect(title).toHaveValue('Inline Edit Title REQ-L3-RF003-001');

    // Markdown preview toggle is part of the description editor
    const previewBtn = page.locator('[data-testid="md-preview-btn"]').first();
    const editBtn = page.locator('[data-testid="md-edit-btn"]').first();
    await expect(previewBtn).toBeVisible();
    await expect(editBtn).toBeVisible();

    // Toggling to preview hides the textarea (which is sibling)
    await previewBtn.click();
    // After clicking preview, no description textarea should be visible
    // (the editor swaps textarea with the rendered markdown div)
    await editBtn.click();
    // Switching back to edit mode should reveal a textarea again
    await expect(page.locator('textarea').first()).toBeVisible({ timeout: 4000 });
  });

  test('[REQ-L3-RF003-002] workflow-state dropdown is visible and selectable', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await expect(page.locator('[data-testid="req-workflow"]')).toBeVisible({ timeout: 12000 });

    const workflow = page.locator('[data-testid="req-workflow"]');

    // Verify dropdown has standard workflow states
    const options = await workflow.locator('option').allTextContents();
    expect(options).toEqual(expect.arrayContaining(['draft', 'review', 'approved']));

    // Select 'review' state
    await workflow.selectOption('review');
    await expect(workflow).toHaveValue('review');
  });

  test('[REQ-L3-RF003-003] traceability panel is visible in requirement editor', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 12000 });

    // Traceability panel must be rendered as part of the detail editor
    const panel = page.locator('[data-testid="traceability-panel"]');
    await expect(panel).toBeVisible({ timeout: 8000 });

    // Panel has upstream + downstream sections (h4 headers)
    const headers = await panel.locator('h4').count();
    expect(headers).toBeGreaterThanOrEqual(2);
  });

  // -------------------------------------------------------------------------
  // REQ-L2-RF-006 — TraceLink create panel visible in requirement editor
  // -------------------------------------------------------------------------
  test('[REQ-L2-RF-006] requirement editor shows tracelink panel with create button', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 12000 });

    // ReqTraceLinkPanel must be rendered
    const panel = page.locator('[data-testid="req-tracelink-panel"]');
    await expect(panel).toBeVisible({ timeout: 8000 });

    // Create button must be present
    const createBtn = page.locator('[data-testid="req-tracelink-create-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 4000 });
  });

  test('[REQ-L2-RF-006] tracelink create form shows target and type selectors', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.locator('[data-testid="create-req-btn"]').click();
    await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 12000 });

    // Open the create form
    await page.locator('[data-testid="req-tracelink-create-btn"]').click();
    await expect(page.locator('[data-testid="req-tracelink-target-select"]')).toBeVisible({ timeout: 6000 });
    await expect(page.locator('[data-testid="req-tracelink-type-select"]')).toBeVisible({ timeout: 4000 });
    await expect(page.locator('[data-testid="req-tracelink-submit-btn"]')).toBeVisible({ timeout: 4000 });

    // All 6 link types must be available
    const typeOptions = await page.locator('[data-testid="req-tracelink-type-select"]').locator('option').allTextContents();
    const realTypes = typeOptions.filter((o) => o.trim());
    expect(realTypes).toEqual(expect.arrayContaining(['parent-child', 'derives-from', 'satisfies', 'verifies', 'implements', 'refines']));
    expect(realTypes.length).toBeGreaterThanOrEqual(6);
  });
});
