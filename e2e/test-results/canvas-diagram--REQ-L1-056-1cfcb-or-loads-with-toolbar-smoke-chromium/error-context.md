# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: canvas-diagram.spec.ts >> [REQ-L1-056 / REQ-L2-DS-006] Canvas Editor >> [REQ-L1-056] test_canvas_editor_loads_with_toolbar @smoke
- Location: tests\canvas-diagram.spec.ts:55:7

# Error details

```
Error: Failed to create canvas diagram: 500 {"error":{"code":"INTERNAL_SERVER_ERROR","message":"JSON payload for diagram_type='block' is missing required key(s): ['nodes'].","details":[]}}
```

# Test source

```ts
  1   | // REQ-L1-056, REQ-L2-DS-006: Canvas Editor E2E User Journey Tests
  2   | //
  3   | // Validates the Canvas Editor workflow end-to-end:
  4   | // - Editor loads with toolbar and pen tool
  5   | // - Drawing simulation, tool switching, color/width changes
  6   | // - Undo via Ctrl+Z
  7   | // - Auto-save and manual save
  8   | // - Persistence after reload
  9   | import { test, expect } from '@playwright/test';
  10  | import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
  11  | 
  12  | const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
  13  | const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
  14  | 
  15  | test.describe('[REQ-L1-056 / REQ-L2-DS-006] Canvas Editor', () => {
  16  |   let diagramId: string;
  17  | 
  18  |   test.beforeAll(async ({ request }) => {
  19  |     const token = await getAuthToken();
  20  |     const resp = await request.post(`${BACKEND_URL}/api/v1/diagrams/`, {
  21  |       headers: { Authorization: `Bearer ${token}` },
  22  |       data: {
  23  |         workspace_id: SEEDED_WORKSPACE_ID,
  24  |         name: 'E2E Canvas Test Diagram',
  25  |         diagram_type: 'block',
  26  |         payload_format: 'json',
  27  |         content: JSON.stringify({ objects: [], background: '#ffffff' }),
  28  |         description: 'Created by E2E canvas test suite',
  29  |       },
  30  |     });
> 31  |     if (!resp.ok()) throw new Error(`Failed to create canvas diagram: ${resp.status()} ${await resp.text()}`);
      |                           ^ Error: Failed to create canvas diagram: 500 {"error":{"code":"INTERNAL_SERVER_ERROR","message":"JSON payload for diagram_type='block' is missing required key(s): ['nodes'].","details":[]}}
  32  |     const body = await resp.json();
  33  |     diagramId = body.id;
  34  |   });
  35  | 
  36  |   test.afterAll(async ({ request }) => {
  37  |     if (diagramId) {
  38  |       const token = await getAuthToken();
  39  |       await request
  40  |         .delete(`${BACKEND_URL}/api/v1/diagrams/${diagramId}/`, {
  41  |           headers: { Authorization: `Bearer ${token}` },
  42  |         })
  43  |         .catch(() => {});
  44  |     }
  45  |   });
  46  | 
  47  |   test.beforeEach(async ({ page }) => {
  48  |     await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
  49  |     await loginAsAdmin(page);
  50  |   });
  51  | 
  52  |   // -------------------------------------------------------------------------
  53  |   // Test 1 — Editor loads with toolbar and pen tool (smoke)
  54  |   // -------------------------------------------------------------------------
  55  |   test('[REQ-L1-056] test_canvas_editor_loads_with_toolbar @smoke', async ({ page }) => {
  56  |     await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);
  57  | 
  58  |     // Wait for editor to render and Fabric.js to initialize
  59  |     await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });
  60  |     await expect(page.locator('[data-testid="canvas-toolbar"]')).toBeVisible({ timeout: 10000 });
  61  |     await expect(page.locator('[data-testid="canvas-element"]')).toBeVisible({ timeout: 10000 });
  62  | 
  63  |     // All three tool buttons must be present
  64  |     await expect(page.locator('[data-testid="canvas-tool-pen"]')).toBeVisible();
  65  |     await expect(page.locator('[data-testid="canvas-tool-select"]')).toBeVisible();
  66  |     await expect(page.locator('[data-testid="canvas-tool-eraser"]')).toBeVisible();
  67  | 
  68  |     // Pen tool should be active by default (status bar shows "pen")
  69  |     await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('pen', { timeout: 8000 });
  70  | 
  71  |     // Undo/Redo buttons exist and are disabled initially
  72  |     const undoBtn = page.locator('[data-testid="canvas-undo"]');
  73  |     const redoBtn = page.locator('[data-testid="canvas-redo"]');
  74  |     await expect(undoBtn).toBeVisible();
  75  |     await expect(redoBtn).toBeVisible();
  76  |     await expect(undoBtn).toBeDisabled();
  77  |     await expect(redoBtn).toBeDisabled();
  78  |   });
  79  | 
  80  |   // -------------------------------------------------------------------------
  81  |   // Test 2 — Tool switching works
  82  |   // -------------------------------------------------------------------------
  83  |   test('[REQ-L1-056] test_canvas_tool_switching', async ({ page }) => {
  84  |     await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);
  85  |     await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });
  86  | 
  87  |     // Click select tool
  88  |     await page.locator('[data-testid="canvas-tool-select"]').click();
  89  |     await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('select', { timeout: 5000 });
  90  | 
  91  |     // Click eraser tool
  92  |     await page.locator('[data-testid="canvas-tool-eraser"]').click();
  93  |     await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('eraser', { timeout: 5000 });
  94  | 
  95  |     // Click back to pen
  96  |     await page.locator('[data-testid="canvas-tool-pen"]').click();
  97  |     await expect(page.locator('[data-testid="canvas-status-bar"]')).toContainText('pen', { timeout: 5000 });
  98  |   });
  99  | 
  100 |   // -------------------------------------------------------------------------
  101 |   // Test 3 — Color picker and width slider are interactive
  102 |   // -------------------------------------------------------------------------
  103 |   test('[REQ-L1-056] test_canvas_color_and_width_controls', async ({ page }) => {
  104 |     await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);
  105 |     await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });
  106 |     await expect(page.locator('[data-testid="canvas-color-picker"]')).toBeVisible({ timeout: 10000 });
  107 |     await expect(page.locator('[data-testid="canvas-width-slider"]')).toBeVisible();
  108 |     await expect(page.locator('[data-testid="canvas-width-label"]')).toHaveText('2px');
  109 | 
  110 |     // Change stroke width via JS evaluation (range input)
  111 |     await page.locator('[data-testid="canvas-width-slider"]').evaluate((el: HTMLInputElement) => {
  112 |       el.value = '10';
  113 |       el.dispatchEvent(new Event('input', { bubbles: true }));
  114 |       el.dispatchEvent(new Event('change', { bubbles: true }));
  115 |     });
  116 |     await expect(page.locator('[data-testid="canvas-width-label"]')).toHaveText('10px');
  117 | 
  118 |     // Change color using a quick-color palette button (blue #4f6ef7)
  119 |     await page.locator('[data-testid="canvas-color-4f6ef7"]').click();
  120 |     // Verify the color picker value changed
  121 |     const colorPicker = page.locator('[data-testid="canvas-color-picker"]');
  122 |     await expect(colorPicker).toHaveValue('#4f6ef7');
  123 |   });
  124 | 
  125 |   // -------------------------------------------------------------------------
  126 |   // Test 4 — Drawing on canvas triggers unsaved state and enables undo
  127 |   // -------------------------------------------------------------------------
  128 |   test('[REQ-L1-056] test_canvas_drawing_triggers_unsaved_state', async ({ page }) => {
  129 |     await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/canvas`);
  130 |     await expect(page.locator('[data-testid="canvas-editor"]')).toBeVisible({ timeout: 10000 });
  131 | 
```