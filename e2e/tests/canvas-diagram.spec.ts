// REQ-L1-056, REQ-L2-DS-006: Canvas Editor E2E User Journey Tests
//
// Validates the Canvas Editor workflow end-to-end:
// - Editor loads with toolbar (select tool active by default)
// - Drawing simulation, tool switching, color/width changes
// - Undo via Ctrl+Z
// - Auto-save and manual save
// - Persistence after reload
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[REQ-L1-056 / REQ-L2-DS-006] Canvas Editor', () => {
  let diagramId: string;

  test.beforeAll(async ({ request }) => {
    const token = await getAuthToken();
    const resp = await request.post(`${BACKEND_URL}/api/v1/diagrams/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        name: 'E2E Canvas Test Diagram',
        // Content shape below ({objects, background}) is the free-drawing
        // canvas payload (DiagramType.CANVAS) — 'block' requires a top-level
        // 'nodes' key (backend/diagram/validator.py _JSON_REQUIRED_KEYS) and
        // rejects this payload with a 400 VALIDATION_ERROR.
        diagram_type: 'canvas',
        payload_format: 'json',
        content: JSON.stringify({ objects: [], background: '#ffffff' }),
        description: 'Created by E2E canvas test suite',
      },
    });
    if (!resp.ok()) throw new Error(`Failed to create canvas diagram: ${resp.status()} ${await resp.text()}`);
    const body = await resp.json();
    diagramId = body.id;
  });

  test.afterAll(async ({ request }) => {
    if (diagramId) {
      const token = await getAuthToken();
      await request
        .delete(`${BACKEND_URL}/api/v1/diagrams/${diagramId}/`, {
          headers: { Authorization: `Bearer ${token}` },
        })
        .catch(() => {});
    }
  });

  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  // -------------------------------------------------------------------------
  // Test 1 — Editor loads with toolbar and pen tool (smoke)
  // -------------------------------------------------------------------------
  test('[REQ-L1-056] test_canvas_editor_loads_with_toolbar @smoke', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);

    // Wait for editor to render and Fabric.js to initialize
    await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="canvas-toolbar"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="canvas-element"]')).toBeVisible({ timeout: 10000 });

    // All three tool buttons must be present
    await expect(page.locator('[data-testid="canvas-tool-pen"]')).toBeVisible();
    await expect(page.locator('[data-testid="canvas-tool-select"]')).toBeVisible();
    await expect(page.locator('[data-testid="canvas-tool-eraser"]')).toBeVisible();

    // Select tool is active by default (diagram editing default since the
    // rect/ellipse/text/connector tools were added — see CanvasEditor.tsx
    // useState<CanvasTool>("select")); status bar reflects it.
    await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('select', { timeout: 8000 });

    // Undo/Redo buttons exist and are disabled initially
    const undoBtn = page.locator('[data-testid="canvas-undo"]');
    const redoBtn = page.locator('[data-testid="canvas-redo"]');
    await expect(undoBtn).toBeVisible();
    await expect(redoBtn).toBeVisible();
    await expect(undoBtn).toBeDisabled();
    await expect(redoBtn).toBeDisabled();
  });

  // -------------------------------------------------------------------------
  // Test 2 — Tool switching works
  // -------------------------------------------------------------------------
  test('[REQ-L1-056] test_canvas_tool_switching', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);
    await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });

    // Click select tool
    await page.locator('[data-testid="canvas-tool-select"]').click();
    await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('select', { timeout: 5000 });

    // Click eraser tool
    await page.locator('[data-testid="canvas-tool-eraser"]').click();
    await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('eraser', { timeout: 5000 });

    // Click back to pen
    await page.locator('[data-testid="canvas-tool-pen"]').click();
    await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('pen', { timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // Test 3 — Color picker and width slider are interactive
  // -------------------------------------------------------------------------
  test('[REQ-L1-056] test_canvas_color_and_width_controls', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);
    await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="canvas-color-picker"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="canvas-width-slider"]')).toBeVisible();
    await expect(page.locator('[data-testid="canvas-width-label"]')).toHaveText('2px');

    // Change stroke width via JS evaluation (range input)
    await page.locator('[data-testid="canvas-width-slider"]').evaluate((el: HTMLInputElement) => {
      el.value = '10';
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    });
    await expect(page.locator('[data-testid="canvas-width-label"]')).toHaveText('10px');

    // Change color using a quick-color palette button (blue #4f6ef7)
    await page.locator('[data-testid="canvas-color-4f6ef7"]').click();
    // Verify the color picker value changed
    const colorPicker = page.locator('[data-testid="canvas-color-picker"]');
    await expect(colorPicker).toHaveValue('#4f6ef7');
  });

  // -------------------------------------------------------------------------
  // Test 4 — Drawing on canvas triggers unsaved state and enables undo
  // -------------------------------------------------------------------------
  test('[REQ-L1-056] test_canvas_drawing_triggers_unsaved_state', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);
    await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });

    // Default tool is "select" (see test_canvas_editor_loads_with_toolbar);
    // switch to the pen tool so mouse-drag below draws a free-hand stroke.
    await page.locator('[data-testid="canvas-tool-pen"]').click();
    await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('pen', { timeout: 8000 });

    // Get canvas element position for drawing
    const canvasWrapper = page.locator('[data-testid="canvas-wrapper"]');
    await expect(canvasWrapper).toBeVisible();
    const box = await canvasWrapper.boundingBox();
    if (!box) throw new Error('Canvas wrapper has no bounding box');

    const centerX = box.x + box.width / 2;
    const centerY = box.y + box.height / 2;

    // Undo should be disabled before drawing
    await expect(page.locator('[data-testid="canvas-undo"]')).toBeDisabled();

    // Simulate drawing a stroke
    await page.mouse.move(centerX - 50, centerY - 50);
    await page.mouse.down();
    await page.mouse.move(centerX + 50, centerY + 50, { steps: 10 });
    await page.mouse.up();

    // Verify undo button becomes enabled (stroke pushed to undo stack)
    await expect(page.locator('[data-testid="canvas-undo"]')).toBeEnabled({ timeout: 3000 });

    // Save status should show "Unsaved changes" (isDirty = true)
    await expect(page.locator('[data-testid="canvas-save-status"]')).toContainText('Unsaved', { timeout: 3000 });
  });

  // -------------------------------------------------------------------------
  // Test 5 — Undo via Ctrl+Z removes drawing
  // -------------------------------------------------------------------------
  test('[REQ-L1-056] test_canvas_undo_via_ctrl_z', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);
    await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });

    // Default tool is "select"; switch to pen to draw a free-hand stroke.
    await page.locator('[data-testid="canvas-tool-pen"]').click();
    await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('pen', { timeout: 8000 });

    // Draw on canvas
    const canvasWrapper = page.locator('[data-testid="canvas-wrapper"]');
    const box = await canvasWrapper.boundingBox();
    if (!box) throw new Error('Canvas wrapper has no bounding box');

    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;

    await page.mouse.move(cx - 40, cy - 40);
    await page.mouse.down();
    await page.mouse.move(cx + 40, cy + 40, { steps: 8 });
    await page.mouse.up();

    // Wait for undo to become enabled
    await expect(page.locator('[data-testid="canvas-undo"]')).toBeEnabled({ timeout: 3000 });

    // Press Ctrl+Z to undo
    await page.keyboard.press('Control+z');

    // Undo button should be disabled again (undo stack is empty after single
    // stroke undo). expect(...).toBeDisabled() already polls/retries, so it
    // doubles as the wait for the undo state update — no fixed delay needed.
    await expect(page.locator('[data-testid="canvas-undo"]')).toBeDisabled({ timeout: 3000 });

    // After undo, the save status still shows unsaved (handleUndo sets isDirty = true)
    await expect(page.locator('[data-testid="canvas-save-status"]')).toContainText('Unsaved', { timeout: 2000 });
  });

  // -------------------------------------------------------------------------
  // Test 6 — Manual save triggers PUT request to canvas-strokes endpoint
  // -------------------------------------------------------------------------
  test('[REQ-L1-056] test_canvas_manual_save_sends_put', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);
    await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });

    // Default tool is "select"; switch to pen to draw a free-hand stroke.
    await page.locator('[data-testid="canvas-tool-pen"]').click();
    await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('pen', { timeout: 8000 });

    // Draw on canvas to make it dirty
    const canvasWrapper = page.locator('[data-testid="canvas-wrapper"]');
    const box = await canvasWrapper.boundingBox();
    if (!box) throw new Error('Canvas wrapper has no bounding box');

    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;

    await page.mouse.move(cx - 30, cy - 30);
    await page.mouse.down();
    await page.mouse.move(cx + 30, cy + 30, { steps: 6 });
    await page.mouse.up();

    // Wait for dirty state
    await expect(page.locator('[data-testid="canvas-save-status"]')).toContainText('Unsaved', { timeout: 3000 });

    // Set up PUT request interceptor
    const putPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes(`/diagrams/${diagramId}/canvas-strokes/`) &&
        resp.request().method() === 'PUT',
      { timeout: 10000 },
    );

    // Click manual save button
    await page.locator('[data-testid="canvas-save-btn"]').click();

    // Wait for the PUT response
    const response = await putPromise;
    expect(response.status()).toBe(200);

    // Save status should show "Saved"
    await expect(page.locator('[data-testid="canvas-save-status"]')).toContainText('Saved', { timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // Test 7 — Auto-save fires PUT request after 5s of inactivity
  // -------------------------------------------------------------------------
  test('[REQ-L1-056] test_canvas_auto_save_fires_after_drawing', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);
    await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });

    // Default tool is "select"; switch to pen to draw a free-hand stroke.
    await page.locator('[data-testid="canvas-tool-pen"]').click();
    await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('pen', { timeout: 8000 });

    // Draw on canvas to make it dirty
    const canvasWrapper = page.locator('[data-testid="canvas-wrapper"]');
    const box = await canvasWrapper.boundingBox();
    if (!box) throw new Error('Canvas wrapper has no bounding box');

    const cx = box.x + box.width / 2;
    const cy = box.y + box.height / 2;

    await page.mouse.move(cx - 20, cy - 20);
    await page.mouse.down();
    await page.mouse.move(cx + 20, cy + 20, { steps: 5 });
    await page.mouse.up();

    // Wait for dirty state
    await expect(page.locator('[data-testid="canvas-save-status"]')).toContainText('Unsaved', { timeout: 3000 });

    // Wait for auto-save (fires every 5s when dirty)
    const putPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes(`/diagrams/${diagramId}/canvas-strokes/`) &&
        resp.request().method() === 'PUT',
      { timeout: 10000 },
    );

    const response = await putPromise;
    expect(response.status()).toBe(200);

    // After auto-save, the dirty flag is cleared and status shows "Saved"
    await expect(page.locator('[data-testid="canvas-save-status"]')).toContainText('Saved', { timeout: 5000 });
  });
});
