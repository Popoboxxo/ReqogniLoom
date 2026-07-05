// REQ-L0-016 / REQ-L2-DS-001: DiagramView UI smoke tests
// Validates the frontend surfaces the diagram list and the create-diagram affordance.
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[REQ-L0-016 / REQ-L2-DS-001] DiagramView UI', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L0-016] test_diagram_list_renders', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams`);

    // Page heading becomes visible once the view mounts
    await expect(
      page.getByRole('heading', { name: /Diagramme|Diagrams/i }),
    ).toBeVisible({ timeout: 10000 });

    // Wait for the loading text to disappear (or list/empty-state to render)
    await expect(page.getByText('Loading...')).not.toBeVisible({ timeout: 10000 });

    // Either the list or the empty-state placeholder must be on the page
    const list = page.locator('[data-testid="diagrams-list"]');
    const empty = page.locator('[data-testid="diagrams-empty"]');
    await expect(list.or(empty)).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L0-016] test_diagram_create_button_visible', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/diagrams`);

    await expect(
      page.getByRole('heading', { name: /Diagramme|Diagrams/i }),
    ).toBeVisible({ timeout: 10000 });
    await expect(page.getByText('Loading...')).not.toBeVisible({ timeout: 10000 });

    const createBtn = page.locator('[data-testid="create-diagram-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 10000 });
    await expect(createBtn).toBeEnabled();
  });
});
