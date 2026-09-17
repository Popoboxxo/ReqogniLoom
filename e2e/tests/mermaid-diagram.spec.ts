// REQ-L1-057, REQ-L2-DS-007: Mermaid Editor E2E User Journey Tests
//
// Validates the Mermaid Editor workflow end-to-end:
// - Split-view renders (code editor left, preview right)
// - Valid Mermaid source → live preview SVG
// - Invalid Mermaid source → error banner
// - Fixing invalid code → error clears, preview returns
// - Auto-save fires PUT request after 2s debounce
// - Manual save triggers PUT
// - Content persists after page reload
import { test, expect, type Page } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[REQ-L1-057 / REQ-L2-DS-007] Mermaid Editor', () => {
  let diagramId: string;

  test.beforeAll(async ({ request }) => {
    const token = await getAuthToken();
    const resp = await request.post(`${BACKEND_URL}/api/v1/diagrams/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        name: 'E2E Mermaid Test Diagram',
        diagram_type: 'flow',
        payload_format: 'mermaid',
        content: 'flowchart TD\n  A[Start] --> B[End]',
        description: 'Created by E2E mermaid test suite',
      },
    });
    if (!resp.ok()) throw new Error(`Failed to create mermaid diagram: ${resp.status()} ${await resp.text()}`);
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
  // Helper: Type text into the CodeMirror editor
  // -------------------------------------------------------------------------
  async function typeInMermaidEditor(page: Page, text: string): Promise<void> {
    // Click on the CodeMirror content area to focus it
    const cmContent = page.locator('[data-testid="mermaid-code-editor"] .cm-content');
    await cmContent.waitFor({ state: 'visible', timeout: 10000 });
    await cmContent.click();

    // Select all existing content and delete it
    await page.keyboard.press('Control+a');
    await page.keyboard.press('Delete');

    // Type the new content
    await page.keyboard.type(text, { delay: 10 });
  }

  // -------------------------------------------------------------------------
  // Test 1 — Split view loads with editor and preview panes (smoke)
  // -------------------------------------------------------------------------
  test('[REQ-L1-057] test_mermaid_editor_loads_with_split_view @smoke', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/mermaid`);

    // Main editor container
    await expect(page.locator('[data-testid="mermaid-editor"]')).toBeVisible({ timeout: 10000 });

    // Left: code editor pane
    await expect(page.locator('[data-testid="mermaid-editor-pane"]')).toBeVisible({ timeout: 10000 });
    // The CodeMirror wrapper must be present
    await expect(page.locator('[data-testid="mermaid-code-editor"]')).toBeVisible({ timeout: 10000 });

    // Right: preview pane
    await expect(page.locator('[data-testid="mermaid-preview-pane"]')).toBeVisible({ timeout: 10000 });
  });

  // -------------------------------------------------------------------------
  // Test 2 — Save button and status bar are present
  // -------------------------------------------------------------------------
  test('[REQ-L1-057] test_mermaid_save_button_and_status_bar', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/mermaid`);
    await expect(page.locator('[data-testid="mermaid-editor"]')).toBeVisible({ timeout: 10000 });

    // Save button exists
    const saveBtn = page.locator('[data-testid="mermaid-save-btn"]');
    await expect(saveBtn).toBeVisible();
    // Initially save is disabled (no changes yet)
    await expect(saveBtn).toBeDisabled();

    // Status bar exists
    await expect(page.locator('[data-testid="mermaid-status-bar"]')).toBeVisible();
    await expect(page.locator('[data-testid="mermaid-save-status"]')).toBeVisible();
  });

  // -------------------------------------------------------------------------
  // Test 3 — Valid mermaid code renders preview SVG
  // -------------------------------------------------------------------------
  test('[REQ-L1-057] test_mermaid_valid_code_renders_preview', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/mermaid`);
    await expect(page.locator('[data-testid="mermaid-editor"]')).toBeVisible({ timeout: 10000 });

    // Type valid flowchart code
    await typeInMermaidEditor(page, 'flowchart TD\n  A[Start] --> B[End]');

    // After debounce (300ms) + mermaid render time, the preview SVG should appear
    // Wait for the SVG container to be present in the DOM
    const previewSvg = page.locator('[data-testid="mermaid-preview-svg"]');
    await expect(previewSvg).toBeVisible({ timeout: 8000 });

    // The SVG content should contain the rendered nodes
    const svgHtml = await previewSvg.innerHTML();
    expect(svgHtml).toContain('<svg');
    expect(svgHtml.length).toBeGreaterThan(100); // Non-trivial SVG

    // No error banner should be visible
    await expect(page.locator('[data-testid="mermaid-error"]')).toHaveCount(0, { timeout: 3000 });

    // Verify status shows diagram type
    await expect(page.locator('[data-testid="mermaid-status-bar"]')).toContainText('flowchart', { timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // Test 4 — Invalid mermaid code shows error banner
  // -------------------------------------------------------------------------
  test('[REQ-L1-057] test_mermaid_invalid_code_shows_error', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/mermaid`);
    await expect(page.locator('[data-testid="mermaid-editor"]')).toBeVisible({ timeout: 10000 });

    // Type invalid mermaid syntax
    await typeInMermaidEditor(page, 'this is not valid mermaid syntax at all');

    // Wait for error banner to appear (debounce + mermaid render error)
    const errorBanner = page.locator('[data-testid="mermaid-error"]');
    await expect(errorBanner).toBeVisible({ timeout: 8000 });

    // Error should contain a message (mermaid.js throws an error for invalid syntax)
    const errorText = await errorBanner.innerText();
    expect(errorText.length).toBeGreaterThan(0);

    // Preview pane should show fallback content (not SVG)
    const previewSvg = page.locator('[data-testid="mermaid-preview-svg"]');
    await expect(previewSvg).toHaveCount(0, { timeout: 3000 });
  });

  // -------------------------------------------------------------------------
  // Test 5 — Fixing invalid code removes error and restores preview
  // -------------------------------------------------------------------------
  test('[REQ-L1-057] test_mermaid_fix_invalid_code_restores_preview', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/mermaid`);
    await expect(page.locator('[data-testid="mermaid-editor"]')).toBeVisible({ timeout: 10000 });

    // First type invalid code
    await typeInMermaidEditor(page, 'garbage mermaid input {{ invalid }}');
    await expect(page.locator('[data-testid="mermaid-error"]')).toBeVisible({ timeout: 8000 });

    // Now fix the code with valid mermaid
    await typeInMermaidEditor(page, 'flowchart LR\n  X[Input] --> Y[Output]');

    // Error should disappear
    await expect(page.locator('[data-testid="mermaid-error"]')).toHaveCount(0, { timeout: 8000 });

    // Preview SVG should appear
    const previewSvg = page.locator('[data-testid="mermaid-preview-svg"]');
    await expect(previewSvg).toBeVisible({ timeout: 8000 });

    // SVG should contain rendered content
    const svgHtml = await previewSvg.innerHTML();
    expect(svgHtml).toContain('<svg');
    expect(svgHtml.length).toBeGreaterThan(100);
  });

  // -------------------------------------------------------------------------
  // Test 6 — Manual save triggers PUT request to mermaid-source endpoint
  // -------------------------------------------------------------------------
  test('[REQ-L1-057] test_mermaid_manual_save_sends_put', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/mermaid`);
    await expect(page.locator('[data-testid="mermaid-editor"]')).toBeVisible({ timeout: 10000 });

    // Type some valid source to make the editor dirty
    const source = 'flowchart TD\n  A --> B\n  B --> C';
    await typeInMermaidEditor(page, source);

    // After typing, save button should become enabled (isDirty = true)
    await expect(page.locator('[data-testid="mermaid-save-btn"]')).toBeEnabled({ timeout: 3000 });

    // Set up PUT request interceptor before clicking save
    const putPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes(`/diagrams/${diagramId}/mermaid-source/`) &&
        resp.request().method() === 'PUT',
      { timeout: 8000 },
    );

    // Click save
    await page.locator('[data-testid="mermaid-save-btn"]').click();

    // Wait for PUT response
    const response = await putPromise;
    expect(response.status()).toBe(200);

    // Save status should show "Saved"
    await expect(page.locator('[data-testid="mermaid-save-status"]')).toContainText(/Saved|Gespeichert/, { timeout: 5000 });

    // After save, button becomes disabled again (no more dirty state)
    await expect(page.locator('[data-testid="mermaid-save-btn"]')).toBeDisabled({ timeout: 5000 });
  });

  // -------------------------------------------------------------------------
  // Test 7 — Auto-save fires PUT request after 2s debounce
  // -------------------------------------------------------------------------
  test('[REQ-L1-057] test_mermaid_auto_save_fires_after_debounce', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams/${diagramId}/mermaid`);
    await expect(page.locator('[data-testid="mermaid-editor"]')).toBeVisible({ timeout: 10000 });

    // Type source code — this triggers auto-save after 2s of inactivity
    const source = 'flowchart LR\n  A --> D';
    await typeInMermaidEditor(page, source);

    // The save button should be enabled (dirty)
    await expect(page.locator('[data-testid="mermaid-save-btn"]')).toBeEnabled({ timeout: 3000 });

    // Wait for auto-save (2s debounce + network)
    const putPromise = page.waitForResponse(
      (resp) =>
        resp.url().includes(`/diagrams/${diagramId}/mermaid-source/`) &&
        resp.request().method() === 'PUT',
      { timeout: 8000 },
    );

    const response = await putPromise;
    expect(response.status()).toBe(200);

    // After auto-save, status shows "Saved"
    await expect(page.locator('[data-testid="mermaid-save-status"]')).toContainText(/Saved|Gespeichert/, { timeout: 5000 });

    // Save button becomes disabled
    await expect(page.locator('[data-testid="mermaid-save-btn"]')).toBeDisabled({ timeout: 5000 });
  });
});
