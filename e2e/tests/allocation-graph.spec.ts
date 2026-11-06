// P4.4 / P5 — allocation card graph.
//
// - View mode exposes no write handle; edit mode does (requires write role).
// - A frozen requirement card has no allocation handle and its lock marker
//   carries the freeze state as tooltip; frozen elements stay valid targets.
// - A rejected write renders the REST code + message verbatim (409 parity).
//
// The frozen-row fixture is injected through the read object (no seeded
// workspace marks Requirement/ArchitectureElement states as freeze states);
// every write assertion still goes through the real backend route.
//
// List validation without a live stack:
// `node node_modules/@playwright/test/cli.js test --list tests/allocation-graph.spec.ts`

import { test, expect } from '@playwright/test';
import {
  createIsolatedWorkspace,
  deleteWorkspace,
  getAuthToken,
  loginAsAdmin,
  setWorkspaceId,
} from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

let token: string;
let workspaceId: string;
let workspaceName: string;
let elementId: string;
let requirementId: string;

test.describe('Allocation graph — modes, locks and error parity', () => {
  test.beforeEach(async ({ request, page }) => {
    token = await getAuthToken();
    workspaceName = `e2e-allocation-graph-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2, 8)}`;
    workspaceId = await createIsolatedWorkspace(token, workspaceName);

    const elementResponse = await request.post(
      `${BACKEND_URL}/api/v1/architecture/`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          workspace_id: workspaceId,
          title: 'Bremse',
          element_type: 'component',
        },
      }
    );
    expect(elementResponse.status()).toBe(201);
    elementId = (await elementResponse.json()).id as string;

    const requirementResponse = await request.post(
      `${BACKEND_URL}/api/v1/requirements/`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          workspace_id: workspaceId,
          title: 'Bremsdruck regeln',
          description: 'E2E allocation-graph fixture',
          category: 'Functional',
        },
      }
    );
    expect(requirementResponse.status()).toBe(201);
    requirementId = (await requirementResponse.json()).id as string;

    await setWorkspaceId(page, workspaceId);
    await loginAsAdmin(page);
  });

  test.afterEach(async () => {
    await deleteWorkspace(token, workspaceId, workspaceName);
  });

  test('view mode hides the write handle, edit mode exposes it', async ({
    page,
  }) => {
    await page.goto(`${FRONTEND_URL}/connections?view=graph`);
    await expect(page.getByTestId('allocation-graph')).toBeVisible();

    await expect(page.getByTestId('graph-mode-view')).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect(
      page.getByTestId(`req-allocate-handle-${requirementId}`)
    ).toHaveCount(0);

    await page.getByTestId('graph-mode-edit').click();
    await expect(page.getByTestId('graph-mode-edit')).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect(
      page.getByTestId(`req-allocate-handle-${requirementId}`)
    ).toBeVisible();
    // A frozen element would still be a valid target; the handle exists on
    // the element side in edit mode regardless of its own lock state.
    await expect(
      page.getByTestId(`el-allocate-handle-${elementId}`)
    ).toBeVisible();
  });

  test('a frozen requirement card has no handle and a state tooltip; the element stays a valid target', async ({
    page,
  }) => {
    await page.route(
      /\/api\/v1\/workspaces\/[^/]+\/allocation-view\//,
      async (route) => {
        const response = await route.fetch();
        const body = (await response.json()) as {
          results: Array<Record<string, unknown>>;
        };
        body.results = body.results.map((row) =>
          row.kind === 'requirement'
            ? { ...row, locked: 'Freigegeben' }
            : row
        );
        await route.fulfill({ response, json: body });
      }
    );

    await page.goto(`${FRONTEND_URL}/connections?view=graph`);
    await expect(page.getByTestId(`req-card-${requirementId}`)).toHaveAttribute(
      'data-frozen',
      'true'
    );

    await page.getByTestId('graph-mode-edit').click();
    await expect(
      page.getByTestId(`req-allocate-handle-${requirementId}`)
    ).toHaveCount(0);
    await expect(page.getByTestId(`card-lock-${requirementId}`)).toHaveAttribute(
      'title',
      'Freigegeben'
    );
    // Frozen elements remain valid allocation targets.
    await expect(
      page.getByTestId(`el-allocate-handle-${elementId}`)
    ).toBeVisible();
  });

  test('a rejected write shows the 409 code and the server message verbatim', async ({
    page,
  }) => {
    await page.route('**/api/v1/trace-links/bulk/', (route) =>
      route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({
          error: {
            code: 'WORKFLOW_FROZEN',
            message: 'Requirement ist durch den Workflow gesperrt',
          },
        }),
      })
    );

    await page.goto(`${FRONTEND_URL}/connections?view=graph`);
    await expect(page.getByTestId('allocation-graph')).toBeVisible();

    await page.getByTestId('graph-mode-edit').click();
    await page.getByTestId(`card-allocate-${requirementId}`).click();
    await page
      .getByTestId(`graph-element-picker-option-${elementId}`)
      .click();

    await expect(page.getByTestId('allocation-graph-error')).toBeVisible();
    await expect(
      page.getByTestId('allocation-graph-error-code')
    ).toHaveText('WORKFLOW_FROZEN');
    await expect(
      page.getByTestId('allocation-graph-error-message')
    ).toContainText('Requirement ist durch den Workflow gesperrt');
  });
});
