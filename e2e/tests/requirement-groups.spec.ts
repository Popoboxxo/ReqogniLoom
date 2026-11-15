// G3 (spec 2026-11-08 §4.5.4/6): drag a *non-member* requirement row onto a
// group folder and the membership is created — visible in the tree without a
// route reload, and still there after one.
//
// The drag half is driven with Playwright's `dragTo`, i.e. real HTML5
// drag-and-drop events, because the membership add *is* the pointer gesture
// (unlike tree-reorder.spec.ts, which deliberately drives the keyboard path).
// The discriminating case from the spec's risk R7 — a drop of an existing
// member must keep reordering inside its group and never add a second
// membership — is covered by the second test.
//
// The specs are list-validated without a live stack
// (`node node_modules/@playwright/test/cli.js test --list tests/requirement-groups.spec.ts`).

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

/** Tree test id prefix of the requirement list (`RequirementList`). */
const TREE = 'req-list-tree';

let token: string;
let workspaceId: string;
let workspaceName: string;
let groupId: string;
let memberId: string;
let nonMemberId: string;

async function createRequirement(
  request: APIRequestContext,
  title: string
): Promise<string> {
  const response = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      workspace_id: workspaceId,
      title,
      description: `E2E requirement-groups fixture: ${title}`,
      category: 'Functional',
    },
  });
  expect(response.status()).toBe(201);
  return (await response.json()).id as string;
}

/** The workspace's groups have no delete route yet, so the whole workspace is
 *  the cleanup unit: it is created per test and hard-deleted afterwards. */
async function createGroup(
  request: APIRequestContext,
  title: string
): Promise<string> {
  const response = await request.post(`${BACKEND_URL}/api/v1/groups/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { workspace_id: workspaceId, title, description: '' },
  });
  expect(response.status()).toBe(201);
  return (await response.json()).id as string;
}

async function addMember(
  request: APIRequestContext,
  requirementId: string
): Promise<void> {
  const response = await request.post(
    `${BACKEND_URL}/api/v1/groups/${groupId}/members/`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { requirement_id: requirementId },
    }
  );
  expect(response.ok()).toBeTruthy();
}

test.describe('Requirement groups — drag a non-member onto a folder (G3)', () => {
  test.beforeEach(async ({ request, page }) => {
    token = await getAuthToken();
    workspaceName = `e2e-requirement-groups-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2, 8)}`;
    workspaceId = await createIsolatedWorkspace(token, workspaceName);

    memberId = await createRequirement(request, 'Bremsdruck regeln');
    nonMemberId = await createRequirement(request, 'Bremsweg messen');

    groupId = await createGroup(request, 'Bremse');
    await addMember(request, memberId);

    await setWorkspaceId(page, workspaceId);
    await loginAsAdmin(page);
  });

  test.afterEach(async () => {
    await deleteWorkspace(token, workspaceId, workspaceName);
  });

  test('drag of a non-member row onto the group folder creates the membership', async ({
    page,
  }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);

    // The group view is opt-in and off by default; turning it on renders the
    // group as a folder with its single member inside.
    const groupToggle = page.getByTestId(`${TREE}-groups-toggle`);
    await expect(groupToggle).toBeVisible();
    await groupToggle.check();

    const folder = page.getByTestId(`${TREE}-node-__group__:${groupId}`);
    await expect(folder).toBeVisible();
    await expect(folder).toHaveAttribute('data-group-folder', 'true');
    await expect(
      page.getByTestId(`${TREE}-node-__group__:${groupId}::${memberId}`)
    ).toBeVisible();
    await expect(
      page.getByTestId(`${TREE}-group-count-__group__:${groupId}`)
    ).toContainText('1');

    // Before the drag the second requirement sits below the folders as a plain
    // row — it is in no group.
    const nonMemberRow = page.getByTestId(`${TREE}-node-${nonMemberId}`);
    await expect(nonMemberRow).toBeVisible();

    // Drop it onto the folder: the middle of the row is the "into this folder"
    // zone, and the row's `draggable` attribute is what makes Playwright's
    // dragTo emit real dragstart/dragover/drop events.
    await expect(nonMemberRow).toHaveAttribute('draggable', 'true');
    await nonMemberRow.dragTo(folder);

    // The membership exists and the tree shows it without a route reload: the
    // member clone appears under the folder, the plain row is gone and the
    // folder counter is up to two.
    await expect(
      page.getByTestId(`${TREE}-node-__group__:${groupId}::${nonMemberId}`)
    ).toBeVisible();
    await expect(page.getByTestId(`${TREE}-node-${nonMemberId}`)).toHaveCount(0);
    await expect(
      page.getByTestId(`${TREE}-group-count-__group__:${groupId}`)
    ).toContainText('2');

    // Server-side truth: a reload renders the same membership.
    await page.reload();
    await page.getByTestId(`${TREE}-groups-toggle`).check();
    await expect(
      page.getByTestId(`${TREE}-node-__group__:${groupId}::${nonMemberId}`)
    ).toBeVisible();
  });

  test('drag of an existing member keeps reordering inside the group', async ({
    page,
  }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.getByTestId(`${TREE}-groups-toggle`).check();

    const folder = page.getByTestId(`${TREE}-node-__group__:${groupId}`);
    const memberRow = page.getByTestId(
      `${TREE}-node-__group__:${groupId}::${memberId}`
    );
    await expect(memberRow).toBeVisible();

    // Dropping the member on its own folder is the inside-the-group reorder
    // (spec risk R7), not a membership add: the count stays at one and no
    // second copy of the row appears.
    await memberRow.dragTo(folder);

    await expect(
      page.getByTestId(`${TREE}-group-count-__group__:${groupId}`)
    ).toContainText('1');
    await expect(
      page.getByTestId(`${TREE}-node-__group__:${groupId}::${memberId}`)
    ).toHaveCount(1);
    // The member never leaves the group for the plain hierarchy.
    await expect(page.getByTestId(`${TREE}-node-${memberId}`)).toHaveCount(0);
  });
});
