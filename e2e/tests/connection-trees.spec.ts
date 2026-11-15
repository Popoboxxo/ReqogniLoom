// V.5 — the "Bäume" view is the default of the connection route.
//
// The spec pins the four behaviours the mode owns end to end:
//
// 1. both trees render, and an allocation draws exactly one edge (the target
//    text on the row is independent of the overlay);
// 2. clicking a row emphasises its edge **and** the row at the other end;
// 3. dragging a requirement onto an element allocates it;
// 4. the keyboard path allocates without a pointer (checkbox -> "Allokieren
//    auf …" -> picker -> Enter), spec §5.8.11.
//
// The route is opened **without** a `view` parameter on purpose: V.5 made
// `trees` the default, and that default is part of the contract.
//
// The specs are list-validated without a live stack
// (`npx playwright test connection-view connection-trees --list`).

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
      description: `E2E connection-trees fixture: ${title}`,
      category: 'Functional',
    },
  });
  expect(response.status()).toBe(201);
  return (await response.json()).id as string;
}

/** One atomic allocation through the committed bulk path. */
async function allocate(
  request: APIRequestContext,
  requirementId: string,
  targetElementId: string
): Promise<void> {
  const response = await request.post(
    `${BACKEND_URL}/api/v1/trace-links/bulk/`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { items: [{ requirement_id: requirementId, element_id: targetElementId }] },
    }
  );
  expect(response.status()).toBe(201);
}

test.describe('Connection view — trees (default mode)', () => {
  test.beforeEach(async ({ request, page }) => {
    token = await getAuthToken();
    workspaceName = `e2e-connection-trees-${Date.now()}-${Math.random()
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

  test.afterEach(async ({ request }) => {
    // The edge switch is a *user* preference, so it outlives the workspace this
    // spec creates (and now really lands, see §5.8.13). Restore the documented
    // default first, or a retry / the next run of this file starts with the
    // overlay hidden and the "exactly one edge per allocation" assertions fail
    // for the wrong reason. Same pattern as the readable-id restore in
    // `requirement-editor.spec.ts`.
    await request.patch(`${BACKEND_URL}/api/v1/users/me/preference-values/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: { values: { 'ui.connection_view.show_edges': true } },
    });
    await deleteWorkspace(token, workspaceId, workspaceName);
  });

  test('opens the two trees by default and draws exactly one edge per allocation', async ({
    page,
    request,
  }) => {
    await allocate(request, requirementIds[0], elementId);

    // No `view` parameter: the default is the contract here.
    await page.goto(`${FRONTEND_URL}/connections`);

    await expect(page.getByTestId('view-switch-trees')).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect(page.getByTestId('allocation-trees-renderer')).toBeVisible();

    // Both hierarchies are rendered …
    await expect(page.getByTestId(`alloc-req-${requirementIds[0]}`)).toBeVisible();
    await expect(page.getByTestId(`alloc-req-${requirementIds[1]}`)).toBeVisible();
    await expect(page.getByTestId(`alloc-el-${elementId}`)).toBeVisible();

    // … the target is also text, so the assignment does not depend on a line,
    await expect(page.getByTestId(`alloc-target-${requirementIds[0]}`)).toHaveText(
      'Bremse'
    );
    // … and the edge is measured, not just mounted (`d` starts a path command).
    const edge = page.getByTestId(`allocation-edge-${requirementIds[0]}`);
    await expect(edge).toHaveCount(1);
    await expect(edge).toHaveAttribute('d', /^M/);
    // The unallocated row has no edge at all.
    await expect(
      page.getByTestId(`allocation-edge-${requirementIds[1]}`)
    ).toHaveCount(0);
  });

  test('clicking a requirement emphasises its edge and the target element', async ({
    page,
    request,
  }) => {
    await allocate(request, requirementIds[0], elementId);
    await page.goto(`${FRONTEND_URL}/connections`);
    await expect(page.getByTestId('allocation-trees-renderer')).toBeVisible();

    await page.getByTestId(`alloc-target-${requirementIds[0]}`).click();

    await expect(page.getByTestId(`alloc-req-${requirementIds[0]}`)).toHaveAttribute(
      'data-emphasized',
      'true'
    );
    await expect(page.getByTestId(`alloc-el-${elementId}`)).toHaveAttribute(
      'data-emphasized',
      'true'
    );
    await expect(
      page.getByTestId(`allocation-edge-${requirementIds[0]}`)
    ).toHaveAttribute('data-emphasized', 'true');

    // The element row emphasises every requirement allocated to it.
    await page.getByTestId(`alloc-el-${elementId}`).click();
    await expect(page.getByTestId(`alloc-req-${requirementIds[0]}`)).toHaveAttribute(
      'data-emphasized',
      'true'
    );
  });

  test('dragging a requirement onto an element allocates it', async ({
    page,
  }) => {
    await page.goto(`${FRONTEND_URL}/connections`);
    await expect(page.getByTestId('allocation-trees-renderer')).toBeVisible();
    // The "not allocated" marker is language-independent, unlike the row text.
    await expect(
      page.getByTestId(`unallocated-marker-${requirementIds[0]}`)
    ).toBeVisible();

    await page
      .getByTestId(`alloc-req-${requirementIds[0]}`)
      .dragTo(page.getByTestId(`alloc-el-${elementId}`));

    await expect(page.getByTestId(`alloc-target-${requirementIds[0]}`)).toHaveText(
      'Bremse'
    );
    await expect(
      page.getByTestId(`unallocated-marker-${requirementIds[0]}`)
    ).toHaveCount(0);
    await expect(
      page.getByTestId(`allocation-edge-${requirementIds[0]}`)
    ).toHaveCount(1);
  });

  test('the keyboard path allocates without a pointer', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/connections`);
    await expect(page.getByTestId('allocation-trees-renderer')).toBeVisible();

    // Select with the keyboard (Space on the row checkbox), then open the
    // picker with Enter on the action bar.
    await page.getByTestId(`alloc-select-${requirementIds[0]}`).focus();
    await page.keyboard.press('Space');
    await expect(page.getByTestId('assistant-selection-count')).toContainText(
      '1'
    );

    await page.getByTestId('assistant-allocate').focus();
    await page.keyboard.press('Enter');
    await expect(page.getByTestId('assistant-element-picker')).toBeVisible();

    await page
      .getByTestId(`assistant-element-picker-option-${elementId}`)
      .focus();
    await page.keyboard.press('Enter');

    // The atomic write landed: the row now names its target.
    await expect(page.getByTestId(`alloc-target-${requirementIds[0]}`)).toHaveText(
      'Bremse'
    );
  });

  test('the edge switch hides only the overlay, never the target text', async ({
    page,
    request,
  }) => {
    await allocate(request, requirementIds[0], elementId);
    await page.goto(`${FRONTEND_URL}/connections`);
    await expect(
      page.getByTestId(`allocation-edge-${requirementIds[0]}`)
    ).toHaveCount(1);

    // The preference survives a reload (spec §5.8.13) — but only if the write
    // reached the store before the reload reads it back. Waiting for the PATCH
    // response (the canvas-diagram/artifact-diff pattern) makes this assertion
    // about the product instead of about network timing. This is not a
    // workaround for a dropped request: the product keeps the write alive
    // across the unload (`keepalive`, `api/preference-values.ts`), so the wait
    // would resolve even for a click that was immediately navigated away from.
    const writeResponse = page.waitForResponse(
      (response) =>
        response.url().includes('/users/me/preference-values/') &&
        response.request().method() === 'PATCH',
      { timeout: 10000 }
    );
    await page.getByTestId('connection-view-show-edges').click();
    expect((await writeResponse).status()).toBe(200);

    await expect(page.getByTestId('allocation-edges')).toHaveCount(0);
    await expect(page.getByTestId(`alloc-target-${requirementIds[0]}`)).toHaveText(
      'Bremse'
    );

    await page.reload();
    await expect(page.getByTestId('allocation-trees-renderer')).toBeVisible();
    await expect(page.getByTestId('connection-view-show-edges')).not.toBeChecked();
    await expect(page.getByTestId('allocation-edges')).toHaveCount(0);
  });
});
