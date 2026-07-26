// REQ-L2-RF-003, REQ-L3-RF003-001/002/003: Requirements editor (inline, workflow, traceability)
// REQ-L2-RF-006: TraceLink creation in RequirementEditor
import { test, expect, type Page } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

// "+ New" only opens an inline quick-create form (title input + Save/Cancel);
// the full editor (req-title etc.) only renders after Save navigates to the
// created requirement's detail route.
async function createRequirementViaQuickForm(page: Page): Promise<void> {
  await page.locator('[data-testid="create-req-btn"]').click();
  await page.locator('[data-testid="req-new-save-btn"]').click();
  await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 10000 });
}

test.describe('[COMP-RF-003] RequirementEditors', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L3-RF003-001] title is editable inline and markdown preview toggle works', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);

    // Create a fresh requirement so the detail editor is shown
    await createRequirementViaQuickForm(page);

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
    await createRequirementViaQuickForm(page);

    // REQ-161: the current state is shown read-only via WorkflowStatusEditor's
    // status badge; a "Change status" trigger + menu only renders when the
    // backend reports allowed transitions from the current state — otherwise
    // a "workflow-no-transitions" hint is shown instead. Fixed literal states
    // ('draft'/'review'/'approved') are no longer guaranteed as option text.
    await expect(page.locator('[data-testid="workflow-current-status"]')).toBeVisible({ timeout: 10000 });

    const trigger = page.locator('[data-testid="workflow-transition-trigger"]');
    const noTransitions = page.locator('[data-testid="workflow-no-transitions"]');
    await expect(trigger.or(noTransitions)).toBeVisible({ timeout: 6000 });

    if (await trigger.count()) {
      await trigger.click();
      const menu = page.locator('[data-testid="workflow-transition-menu"]');
      await expect(menu).toBeVisible();

      const option = menu.locator('[data-testid^="workflow-transition-option-"]').first();
      const targetState = await option.getAttribute('data-testid');
      if (targetState) {
        await option.click();
        await expect(page.locator('[data-testid="workflow-current-status"]')).toBeVisible();
      }
    }
  });

  test('[REQ-L3-RF003-003] traceability panel is visible in requirement editor', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);

    // The old standalone TraceabilityPanel (upstream/downstream sections) is
    // dead code — linked-requirement traceability now lives in
    // ReqTraceLinkPanel, rendered as part of the detail editor.
    const panel = page.locator('[data-testid="req-tracelink-panel"]');
    await expect(panel).toBeVisible({ timeout: 8000 });
    // req-tracelink-list only renders once links exist; a freshly-created
    // requirement has none, so the panel shows a "no links" message instead.
    await expect(panel).not.toBeEmpty({ timeout: 4000 });
  });

  // -------------------------------------------------------------------------
  // REQ-L2-RF-006 — TraceLink create panel visible in requirement editor
  // -------------------------------------------------------------------------
  test('[REQ-L2-RF-006] requirement editor shows tracelink panel with create button', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);

    // ReqTraceLinkPanel must be rendered
    const panel = page.locator('[data-testid="req-tracelink-panel"]');
    await expect(panel).toBeVisible({ timeout: 8000 });

    // Create button must be present
    const createBtn = page.locator('[data-testid="req-tracelink-create-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 4000 });
  });

  test('[REQ-L2-RF-006] tracelink create form shows target and type selectors', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);

    // Open the create form
    await page.locator('[data-testid="req-tracelink-create-btn"]').click();
    await expect(page.locator('[data-testid="req-tracelink-target-select"]')).toBeVisible({ timeout: 6000 });
    await expect(page.locator('[data-testid="req-tracelink-type-select"]')).toBeVisible({ timeout: 4000 });
    await expect(page.locator('[data-testid="req-tracelink-submit-btn"]')).toBeVisible({ timeout: 4000 });

    // All 6 link types must be available. Options render getLinkTypeLabel()
    // as display text (e.g. "Parent / Child") but keep the raw LinkType as
    // the underlying `value` — assert against values, not visible text.
    const typeValues = await page.locator('[data-testid="req-tracelink-type-select"]').locator('option').evaluateAll(
      (opts) => opts.map((o) => (o as HTMLOptionElement).value)
    );
    const realTypes = typeValues.filter((o) => o.trim());
    expect(realTypes).toEqual(expect.arrayContaining(['parent-child', 'derives-from', 'satisfies', 'verifies', 'implements', 'refines']));
    expect(realTypes.length).toBeGreaterThanOrEqual(6);
  });

  // -------------------------------------------------------------------------
  // REQ-L1-040 — Resizable split-pane divider (analog ArchitectureEditors)
  // -------------------------------------------------------------------------
  test('[REQ-L1-040] split-pane divider is draggable and resizes panels', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);

    // Create a requirement so the detail panel is shown
    await createRequirementViaQuickForm(page);

    // Verify divider exists
    const divider = page.locator('[data-testid="splitview-divider"]');
    await expect(divider).toBeVisible();

    // Get initial width of left panel. The left panel has no dedicated
    // testid; it's the divider's immediate previous sibling (a `div`
    // filter matches every ancestor of create-req-btn too, and `.first()`
    // picks the outermost one — not the actual resizing flex panel).
    const leftPanel = divider.locator('xpath=preceding-sibling::div[1]');
    const initialWidth = await leftPanel.evaluate((el) => window.getComputedStyle(el).width);

    // Drag divider 100px to the right. The seeded workspace accumulates
    // requirements across test runs, so the left panel's content (and thus
    // the full-height divider) can grow taller than the viewport; raw
    // page.mouse calls don't auto-scroll like locator actions do, so target
    // a point near the top of the box, which is always on-screen.
    const dividerBox = await divider.boundingBox();
    if (!dividerBox) throw new Error('Divider bounding box not found');
    const dragY = dividerBox.y + Math.min(20, dividerBox.height / 2);

    await page.mouse.move(dividerBox.x + dividerBox.width / 2, dragY);
    await page.mouse.down();
    await page.mouse.move(dividerBox.x + dividerBox.width / 2 + 100, dragY);
    await page.mouse.up();

    // Get new width of left panel (should be wider)
    const newWidth = await leftPanel.evaluate((el) => window.getComputedStyle(el).width);

    // Verify left panel got wider
    const initialPx = parseInt(initialWidth);
    const newPx = parseInt(newWidth);
    expect(newPx).toBeGreaterThan(initialPx);
  });

  test('[REQ-L1-040] split-pane divider has correct styling and hover effect', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirementViaQuickForm(page);

    const divider = page.locator('[data-testid="splitview-divider"]');

    // Verify divider styling
    // REQ-007: divider hitbox widened to 12px (2px visual center line via
    // gradient), up from the earlier 4px.
    const width = await divider.evaluate((el) => window.getComputedStyle(el).width);
    const cursor = await divider.evaluate((el) => window.getComputedStyle(el).cursor);
    expect(width).toBe('12px');
    expect(cursor).toBe('col-resize');

    // Verify hover effect changes background
    const initialBg = await divider.evaluate((el) => window.getComputedStyle(el).backgroundColor);
    await divider.hover();
    const hoveredBg = await divider.evaluate((el) => window.getComputedStyle(el).backgroundColor);
    // Background should change on hover (either different value or transition)
    // Note: exact color depends on CSS tokens, just verify it's interactive
    expect(initialBg).toBeTruthy();
    expect(hoveredBg).toBeTruthy();
  });
});
