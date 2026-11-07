// P3.5 / P4.4 — connection view allocation assistant.
//
// Exercises the multi-select bulk path end to end: "Nicht allokiert" filter ->
// count -> select rows -> atomic allocation through the element picker ->
// count drops -> the matrix shows the allocation dot. A second test drives the
// suggestion flow and proves nothing is written before the explicit confirm.
//
// The specs are list-validated without a live stack
// (`node node_modules/@playwright/test/cli.js test --list tests/connection-view.spec.ts`).

import { test, expect, type APIRequestContext } from '@playwright/test';
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
let requirementIds: string[];

async function createRequirement(
  request: APIRequestContext,
  title: string
): Promise<string> {
  const response = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      workspace_id: workspaceId,
      title,
      description: `E2E connection-view fixture: ${title}`,
      category: 'Functional',
    },
  });
  expect(response.status()).toBe(201);
  return (await response.json()).id as string;
}

test.describe('Connection view — allocation assistant', () => {
  test.beforeEach(async ({ request, page }) => {
    token = await getAuthToken();
    workspaceName = `e2e-connection-view-${Date.now()}-${Math.random()
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

    requirementIds = [
      await createRequirement(request, 'Bremsdruck regeln'),
      await createRequirement(request, 'Bremsweg messen'),
    ];

    await setWorkspaceId(page, workspaceId);
    await loginAsAdmin(page);
  });

  test.afterEach(async () => {
    await deleteWorkspace(token, workspaceId, workspaceName);
  });

  test('filters "Nicht allokiert", bulk-allocates the selection, count drops and the matrix shows the dot', async ({
    page,
  }) => {
    await page.goto(`${FRONTEND_URL}/connections`);
    await expect(page.getByTestId('connection-view')).toBeVisible();

    await page.getByTestId('quick-unallocated').click();
    await expect(page.getByTestId('unallocated-count')).toHaveText('2');

    await page.getByTestId(`assistant-check-${requirementIds[0]}`).check();
    await page.getByTestId(`assistant-check-${requirementIds[1]}`).check();
    await expect(page.getByTestId('assistant-selection-count')).toContainText(
      '2'
    );

    await page.getByTestId('assistant-allocate').click();
    await page
      .getByTestId(`assistant-element-picker-option-${elementId}`)
      .click();

    // The whole selection is one atomic request; both rows leave the
    // "Nicht allokiert" result.
    await expect(page.getByTestId('unallocated-count')).toHaveText('0');

    // Clear the quick filter, then verify the allocation in the matrix.
    await page.getByTestId('quick-unallocated').click();
    await page.getByTestId('view-switch-matrix').click();
    await expect(page.getByTestId('matrix-renderer')).toBeVisible();
    await expect(
      page.getByTestId(`matrix-dot-${requirementIds[0]}-${elementId}`)
    ).toBeVisible();
    await expect(
      page.getByTestId(`matrix-dot-${requirementIds[1]}-${elementId}`)
    ).toBeVisible();
  });

  test('suggestion flow shows target + reason and writes only after confirmation', async ({
    page,
    request,
  }) => {
    await page.route(
      '**/api/v1/requirements/*/suggest-architecture/',
      (route) =>
        route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify({
            suggested_arch_element_ids: [elementId],
            is_mock_fallback: true,
            ephemeral: true,
          }),
        })
    );

    await page.goto(`${FRONTEND_URL}/connections`);
    await expect(page.getByTestId('connection-view')).toBeVisible();
    await page.getByTestId('quick-unallocated').click();

    await page.getByTestId(`assistant-check-${requirementIds[0]}`).check();
    await page.getByTestId('assistant-suggest').click();

    const suggestion = page.getByTestId(
      `assistant-candidate-${requirementIds[0]}-${elementId}`
    );
    await expect(suggestion).toContainText('Bremse');
    await expect(
      page.getByTestId(`assistant-reason-${requirementIds[0]}-${elementId}`)
    ).not.toBeEmpty();

    // Nothing may be written before the confirmation dialog's confirm.
    const before = await request.get(
      `${BACKEND_URL}/api/v1/workspaces/${workspaceId}/allocation-view/`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(before.ok()).toBeTruthy();
    const beforeRows = (await before.json()).results as Array<{
      id: string;
      allocated_to: string | null;
    }>;
    expect(
      beforeRows.find((row) => row.id === requirementIds[0])?.allocated_to
    ).toBeNull();

    await page.getByTestId('assistant-accept-all').click();
    await expect(
      page.getByTestId('assistant-suggestion-confirm')
    ).toBeVisible();
    await page.getByTestId('assistant-confirm-write').click();
    await expect(page.getByTestId('assistant-notice')).toBeVisible();

    // The confirmed suggestion is now persisted.
    await expect
      .poll(async () => {
        const after = await request.get(
          `${BACKEND_URL}/api/v1/workspaces/${workspaceId}/allocation-view/`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (!after.ok()) return null;
        const rows = (await after.json()).results as Array<{
          id: string;
          allocated_to: string | null;
        }>;
        return rows.find((row) => row.id === requirementIds[0])?.allocated_to;
      })
      .not.toBeNull();
  });
});
