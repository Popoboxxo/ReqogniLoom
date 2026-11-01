// F4.5 — Baseline rollback in the UI (REQ-L1-018, ADR-025, Plan F).
//
// The full governed flow, end to end: change an artifact, open the rollback
// panel, compute the plan, open the CCB change request, approve that request
// as a SECOND user (self-approval is denied by `ChangeRequestService`, and the
// CCB transitions need the `approver` role), then apply and verify the
// artifact is back at the baselined title and the result region reports the
// counts.
//
// Setup/approval run through the REST API (the same convention
// `baselines-tags.spec.ts` and `user-management.spec.ts` use — there is no CR
// view in this SPA to drive the CCB decision from). The UI half only touches
// what this change adds: the rollback panel.
import { test, expect, type APIRequestContext } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  createIsolatedWorkspace,
  deleteWorkspace,
  purgeWorkspaceBaselines,
  closeWorkspace,
  unreadNotificationIds,
  clearNotificationsSince,
  setWorkspaceId,
} from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

/** Throwaway password for this run's fixture approver — not a credential. */
const APPROVER_PASSWORD = 'e2e-ccb-approver-123';

interface CreatedUserDto {
  id: string;
}

/** Create a second user and give it the roles the CCB transitions need. */
async function createApprover(
  request: APIRequestContext,
  adminHeaders: Record<string, string>,
  workspaceId: string,
  username: string
): Promise<string> {
  const createResp = await request.post(`${BACKEND_URL}/api/v1/users/`, {
    headers: adminHeaders,
    data: {
      username,
      email: `${username}@e2e.test`,
      password: APPROVER_PASSWORD,
    },
  });
  expect(
    createResp.ok(),
    `user create failed: ${createResp.status()} ${await createResp.text()}`
  ).toBeTruthy();
  const created = (await createResp.json()) as CreatedUserDto;

  // `submitted` is an editor transition, `under_review`/`approved` are
  // approver transitions — the CCB asks two different people, so the fixture
  // user carries both roles (still not the requestor, so self-approval stays
  // impossible).
  for (const role of ['editor', 'approver'] as const) {
    const assignResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${workspaceId}/members/`,
      { headers: adminHeaders, data: { user_id: created.id, role } }
    );
    expect(
      assignResp.ok(),
      `role '${role}' assignment failed: ${assignResp.status()} ${await assignResp.text()}`
    ).toBeTruthy();
  }
  return created.id;
}

/** Log in as the fixture approver and return its JWT. */
async function approverToken(
  request: APIRequestContext,
  username: string
): Promise<string> {
  const response = await request.post(`${BACKEND_URL}/api/v1/auth/login/`, {
    data: { username, password: APPROVER_PASSWORD },
  });
  expect(
    response.ok(),
    `approver login failed: ${response.status()} ${await response.text()}`
  ).toBeTruthy();
  const body = (await response.json()) as {
    token?: string;
    access?: string;
    access_token?: string;
  };
  const token = body.token ?? body.access ?? body.access_token;
  expect(token, 'approver login returned no token').toBeTruthy();
  return token as string;
}

/** Drive one CCB transition, failing with the backend's own reason. */
async function transitionChangeRequest(
  request: APIRequestContext,
  headers: Record<string, string>,
  changeRequestId: string,
  targetState: string,
  changeReason: string
): Promise<void> {
  const response = await request.post(
    `${BACKEND_URL}/api/v1/change-requests/${changeRequestId}/transitions/`,
    { headers, data: { target_state: targetState, change_reason: changeReason } }
  );
  if (!response.ok()) {
    throw new Error(
      `CR transition to '${targetState}' rejected with HTTP ${response.status()}: ` +
        `${await response.text()}`
    );
  }
}

test.describe('[REQ-L1-018] Baseline rollback (F4.5)', () => {
  test('preview → change request → CCB approval → apply restores the baseline', async ({
    page,
    request,
  }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };
    const suffix = Date.now().toString(36);
    const workspaceName = `e2e-rollback-${suffix}`;
    // Notifications this run creates for the shared `admin` user. The CCB
    // approval below is performed by the fixture approver, so the transition's
    // role broadcast notifies this workspace's editor/admin members — `admin`
    // among them. That unread notification makes the shell's interview-widget
    // badge (a `role="status"` live region, `hidden` only at unread === 0)
    // visible, which breaks the page-wide invariant `baselines-tags.spec.ts`
    // and `baselines-view.spec.ts` assert: "the loading indicator is the only
    // visible `[role="status"]`". Since this spec runs before both of them
    // (alphabetical file order, `workers: 1`, `fullyParallel: false`), the
    // delta is marked read again in the teardown.
    const unreadBefore = await unreadNotificationIds(token);
    // F4.5 review B-01: the Approver role is only assignable at the extended
    // preset (`AuthorizationService._APPROVER_ENABLED_PRESETS == {"extended"}`).
    // The CCB transitions below (`submitted`/`under_review`/`approved`) are
    // gated on `approver`, so a `standard` workspace answers 400 on the role
    // assignment and the flow never starts. Creating the workspace at
    // `extended` keeps the real two-person CCB path intact.
    const workspaceId = await createIsolatedWorkspace(token, workspaceName, 'extended');
    const originalTitle = `e2e-rollback-original-${suffix}`;
    const changedTitle = `e2e-rollback-changed-${suffix}`;

    try {
      // --- Fixture: one artifact, captured by a project-scope baseline. ---
      const requirementResp = await request.post(
        `${BACKEND_URL}/api/v1/requirements/`,
        {
          headers,
          data: {
            workspace_id: workspaceId,
            title: originalTitle,
            description: 'Created by baselines-rollback.spec.ts (F4.5)',
            category: 'Functional',
            acceptance_criteria: 'Given a baseline, when rolled back, then the title is restored.',
            verification_method: 'Inspection',
          },
        }
      );
      expect(
        requirementResp.ok(),
        `requirement create failed: ${requirementResp.status()} ${await requirementResp.text()}`
      ).toBeTruthy();
      const requirement = (await requirementResp.json()) as { id: string };

      // GH-513: the SE-Auditor blocks baseline creation while the workspace has
      // BLOCKER findings, and an untraced root requirement is a guaranteed
      // TRACE-P1 BLOCKER at the standard tier. The override is the documented,
      // permission-checked path and keeps this spec focused on the rollback.
      const baselineResp = await request.post(`${BACKEND_URL}/api/v1/baselines/`, {
        headers,
        data: {
          workspace_id: workspaceId,
          name: `e2e-rollback-baseline-${suffix}`,
          scope: 'project',
          override_reason: 'E2E fixture: the captured requirement is intentionally untraced.',
        },
      });
      expect(
        baselineResp.ok(),
        `baseline create failed: ${baselineResp.status()} ${await baselineResp.text()}`
      ).toBeTruthy();
      const baseline = (await baselineResp.json()) as { id: string; name: string };

      // Drift the artifact away from the baselined state.
      const patchResp = await request.patch(
        `${BACKEND_URL}/api/v1/requirements/${requirement.id}/`,
        {
          headers,
          data: { title: changedTitle, change_reason: 'E2E: drift the artifact' },
        }
      );
      expect(
        patchResp.ok(),
        `requirement update failed: ${patchResp.status()} ${await patchResp.text()}`
      ).toBeTruthy();

      // --- UI: open the baseline, compute the plan. ---
      await setWorkspaceId(page, workspaceId);
      await loginAsAdmin(page);
      await page.goto(`${FRONTEND_URL}/baselines`);
      await expect(page.locator('[data-testid="baselines-view"]')).toBeVisible({
        timeout: 10000,
      });
      // The view's own loading region must be gone before we click a baseline.
      // Asserted page-wide on purpose: `baselines-tags.spec.ts` and
      // `baselines-view.spec.ts` assert exactly this, so failing here is the
      // early, actionable signal instead of a red spec three files later. It
      // holds for the whole shard only because every spec that drives a
      // workflow transition cleans up the notifications it leaves behind (see
      // `unreadBefore` above).
      await expect(page.locator('[role="status"]:visible')).toHaveCount(0, {
        timeout: 10000,
      });

      await page
        .locator('[data-testid="baseline-item"]', { hasText: baseline.name })
        .click();
      await expect(page.locator('[data-testid="baseline-rollback-panel"]')).toBeVisible();

      await page.locator('[data-testid="baseline-rollback-preview-btn"]').click();
      const driftedRow = page.locator('[data-testid="baseline-rollback-item-row"]', {
        hasText: originalTitle,
      });
      await expect(driftedRow).toHaveCount(1, { timeout: 10000 });
      await expect(driftedRow).toContainText(changedTitle);
      await expect(page.locator('[data-testid="baseline-rollback-error"]')).toHaveCount(0);

      // --- UI: open the CCB change request. ---
      await page
        .locator('[data-testid="baseline-rollback-reason-input"]')
        .fill('E2E: restore the baselined release state');
      await page.locator('[data-testid="baseline-rollback-request-btn"]').click();

      const crStatus = page.locator('[data-testid="baseline-rollback-cr-status"]');
      await expect(crStatus).toBeVisible({ timeout: 10000 });
      await expect(crStatus).toHaveText(/draft/i);
      // No approval, no apply: the destructive action is not offered yet.
      await expect(page.locator('[data-testid="baseline-rollback-apply-btn"]')).toHaveCount(0);

      const changeRequestId = (
        await page.locator('[data-testid="baseline-rollback-cr-link"]').innerText()
      ).trim();
      expect(changeRequestId, 'the panel did not expose the change request id').toBeTruthy();

      // --- CCB: a second user approves the change request. ---
      const approverName = `e2e-ccb-${suffix}`;
      await createApprover(request, headers, workspaceId, approverName);
      const ccbHeaders = {
        Authorization: `Bearer ${await approverToken(request, approverName)}`,
      };
      await transitionChangeRequest(request, ccbHeaders, changeRequestId, 'submitted', 'Submit for CCB review');
      await transitionChangeRequest(request, ccbHeaders, changeRequestId, 'under_review', 'CCB review opened');
      await transitionChangeRequest(request, ccbHeaders, changeRequestId, 'approved', 'CCB approved the rollback');

      // The approver's transitions broadcast "awaits your action" to this
      // workspace's editor/admin role holders — `admin` among them, and not
      // the actor. Mark that delta read right away: the page-wide
      // `[role="status"]` invariant every baselines spec asserts must not
      // depend on this file reaching its teardown (the teardown repeats the
      // call, idempotently).
      await clearNotificationsSince(token, unreadBefore);

      // --- UI: re-read the status, then apply behind the confirmation. ---
      await page.locator('[data-testid="baseline-rollback-cr-refresh"]').click();
      const applyBtn = page.locator('[data-testid="baseline-rollback-apply-btn"]');
      await expect(applyBtn).toBeVisible({ timeout: 10000 });
      await expect(crStatus).toHaveText(/approved/i);

      await applyBtn.click();
      const confirmDialog = page.locator('[data-testid="baseline-rollback-confirm"]');
      await expect(confirmDialog).toBeVisible();
      await expect(
        page.locator('[data-testid="baseline-rollback-confirm-body"]')
      ).toContainText(/\d+/);

      await page.locator('[data-testid="baseline-rollback-confirm-confirm"]').click();
      const resultRegion = page.locator('[data-testid="baseline-rollback-result"]');
      await expect(resultRegion).toBeVisible({ timeout: 20000 });
      // Locale-agnostic: the message carries the restored/reactivated/link counts.
      await expect(resultRegion).toContainText(/\d+/);

      // --- The artifact is back at the baselined title. ---
      await expect
        .poll(
          async () => {
            const response = await request.get(
              `${BACKEND_URL}/api/v1/requirements/${requirement.id}/`,
              { headers }
            );
            const body = (await response.json()) as { title?: string };
            return body.title;
          },
          { timeout: 15000 }
        )
        .toBe(originalTitle);
    } finally {
      // 1. Restore the shared user's unread state (see `unreadBefore`): the
      //    notification this spec caused is what makes the shell's
      //    `role="status"` badge visible for the rest of the shard.
      //    Best-effort and idempotent — the helper swallows its own failures.
      await clearNotificationsSince(token, unreadBefore);

      // 2. Baselines are append-only, so the workspace hard-delete is refused
      //    with `409 baselines_immutable` while one exists (GH-1084). Purge
      //    them through the audited admin route first, otherwise this spec
      //    leaves an undeletable orphan workspace behind on every run.
      await purgeWorkspaceBaselines(token, workspaceId);

      // 3. Hard delete; if it is still refused, soft-close so no *live*
      //    orphan remains. A closed workspace is out of every list and flow
      //    and stays recoverable (`POST .../reactivate/`).
      const deleted = await deleteWorkspace(token, workspaceId, workspaceName);
      if (!deleted) {
        await closeWorkspace(token, workspaceId);
      }
    }
  });
});
