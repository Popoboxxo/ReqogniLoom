// P1 Task 1.7: reordering and re-parenting in the requirement tree.
//
// The keyboard path (Alt+↑/↓) is what this spec drives instead of HTML5
// drag-and-drop: it is the documented, deterministic alternative to dragging
// (WCAG 2.1.1 / 2.5.7) and it exercises the same `WorkspaceTree` → `onReorder`
// → `POST /artifacts/{id}/move/` path a drop uses.
//
// The three fixtures are real requirements created through the API and filtered
// into view by their unique title prefix, so the sibling block under test is
// exactly those three — the seeded workspace has hundreds of root requirements
// and the tree is virtualized.
import { test, expect, type Page } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  setWorkspaceId,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

const PREFIX = `E2E-RECORDER-${Date.now()}`;

interface CreatedRequirement {
  id: string;
  title: string;
}

/** Tree row ids in the order the tree renders them (DOM order = sort order). */
async function treeOrder(page: Page): Promise<string[]> {
  return page
    .locator('[data-testid^="req-list-tree-node-"]')
    .evaluateAll((elements) =>
      elements.map((el) => el.getAttribute('data-testid') ?? ''),
    );
}

/** Index of `req`'s row inside the rendered order. */
async function positionOf(page: Page, req: CreatedRequirement): Promise<number> {
  const order = await treeOrder(page);
  return order.indexOf(`req-list-tree-node-${req.id}`);
}

test.describe('WorkspaceTree reorder (P1 Task 1.7)', () => {
  let created: CreatedRequirement[] = [];

  test.beforeEach(async ({ request }) => {
    created = [];
    const token = await getAuthToken();
    for (const suffix of ['A', 'B', 'C']) {
      const response = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          workspace_id: SEEDED_WORKSPACE_ID,
          title: `${PREFIX}-${suffix}`,
          description: 'Created by tree-reorder.spec.ts',
          category: 'Functional',
        },
      });
      expect(response.ok()).toBeTruthy();
      const body = await response.json();
      created.push({ id: body.id, title: body.title });
    }
  });

  test.afterEach(async ({ request }) => {
    const token = await getAuthToken();
    for (const req of created) {
      await request.delete(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    }
  });

  test('Alt+ArrowDown reorders a sibling and the order survives a reload', async ({
    page,
  }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/requirements`);

    // Narrow the tree to the three fixtures (appended last, in creation order).
    await page.getByTestId('req-list-search-input').fill(PREFIX);
    await expect(
      page.getByTestId(`req-list-tree-node-${created[0].id}`),
    ).toBeVisible({ timeout: 10000 });

    await expect
      .poll(async () => treeOrder(page))
      .toEqual(created.map((req) => `req-list-tree-node-${req.id}`));

    // Move the first row down one step. The tree's rows carry a roving
    // tabindex, so a keyboard user enters the tree by focusing the row — which
    // is what the assertion below pins before the shortcut is pressed (a plain
    // click selects the row but leaves DOM focus on the document, because the
    // custom row content is a non-focusable div).
    const firstRow = page.getByTestId(`req-list-tree-node-${created[0].id}`);
    await firstRow.click();
    await firstRow.focus();
    await expect(firstRow).toBeFocused();
    await expect(firstRow).toHaveAttribute(
      'aria-keyshortcuts',
      'Alt+ArrowUp Alt+ArrowDown',
    );
    await page.keyboard.press('Alt+ArrowDown');

    await expect
      .poll(async () => positionOf(page, created[0]))
      .toBe(1);

    const afterMove = await treeOrder(page);
    expect(afterMove).toEqual([
      `req-list-tree-node-${created[1].id}`,
      `req-list-tree-node-${created[0].id}`,
      `req-list-tree-node-${created[2].id}`,
    ]);

    // The position is persisted server-side (sort_key), not just in the UI.
    await page.reload();
    await page.getByTestId('req-list-search-input').fill(PREFIX);
    await expect
      .poll(async () => treeOrder(page))
      .toEqual([
        `req-list-tree-node-${created[1].id}`,
        `req-list-tree-node-${created[0].id}`,
        `req-list-tree-node-${created[2].id}`,
      ]);
  });
});
