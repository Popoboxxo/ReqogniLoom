// REQ-144: Review/Approval UI — draft -> in_review -> approved workflow,
// including the reject path and the signature-gated approve path.
//
// NOT YET RUN — no Docker/Postgres backend available in this sandbox. Written
// against the same conventions as e2e/tests/requirements.spec.ts and
// e2e/tests/baselines-view.spec.ts (API setup via request fixture, UI
// assertions via data-testid).
//
// The seeded workspace's "extended" preset (backend/workflow/definition_store.py,
// _extended_transitions()) has requires_change_reason: True on every
// transition and signature_gate: False on all of them today — so the "happy
// path" approve/reject tests below always fill the change-reason field and
// never expect the signature dialog. The dedicated signature-gate test
// exercises SignatureDialog end-to-end by intercepting the GET .../transitions/
// response and forcing signature_gate: true on the "approved" transition,
// so this spec does not depend on a workspace preset actually enabling it.
import { test, expect, APIRequestContext, Route } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

interface CreatedRequirement {
  id: string;
  title: string;
}

async function createRequirement(
  request: APIRequestContext,
  token: string,
  title: string
): Promise<CreatedRequirement> {
  const response = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      workspace_id: SEEDED_WORKSPACE_ID,
      title,
      description: 'Created by review-workflow.spec.ts (REQ-144)',
      category: 'Functional',
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  return { id: body.id as string, title: body.title as string };
}

async function apiTransition(
  request: APIRequestContext,
  token: string,
  id: string,
  targetState: string,
  changeReason: string
): Promise<void> {
  const response = await request.post(`${BACKEND_URL}/api/v1/requirements/${id}/transitions/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { target_state: targetState, change_reason: changeReason },
  });
  expect(response.ok()).toBeTruthy();
}

async function deleteRequirement(
  request: APIRequestContext,
  token: string,
  id: string
): Promise<void> {
  await request.delete(`${BACKEND_URL}/api/v1/requirements/${id}/`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

test.describe('[COMP-RF-REV] Reviews view (REQ-144)', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-144] reviews view renders without error', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/reviews`);
    await expect(page.locator('[data-testid="reviews-view"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-144] a requirement moved to in_review appears in the review queue', async ({
    page,
    request,
  }) => {
    const token = await getAuthToken();
    const req = await createRequirement(request, token, 'E2E Review Queue Requirement');
    await apiTransition(request, token, req.id, 'in_review', 'submitting for review');

    try {
      await page.goto(`${FRONTEND_URL}/reviews`);
      await expect(page.locator('[data-testid="reviews-view"]')).toBeVisible({ timeout: 10000 });

      const item = page.locator(`[data-testid="review-list-item-${req.id}"]`);
      await expect(item).toBeVisible({ timeout: 10000 });
      await expect(item).toContainText(req.title);
    } finally {
      await deleteRequirement(request, token, req.id);
    }
  });

  test('[REQ-144] approve transitions the requirement to approved and removes it from the queue', async ({
    page,
    request,
  }) => {
    const token = await getAuthToken();
    const req = await createRequirement(request, token, 'E2E Approve Requirement');
    await apiTransition(request, token, req.id, 'in_review', 'submitting for review');

    try {
      await page.goto(`${FRONTEND_URL}/reviews`);
      const item = page.locator(`[data-testid="review-list-item-${req.id}"]`);
      await expect(item).toBeVisible({ timeout: 10000 });
      await item.click();

      const detail = page.locator('[data-testid="review-detail"]');
      await expect(detail).toBeVisible({ timeout: 10000 });

      // The extended preset requires a change_reason on in_review -> approved.
      await page.locator('[data-testid="review-change-reason-input"]').fill('looks good to me');

      const approveBtn = page.locator('[data-testid="review-approve-btn"]');
      await expect(approveBtn).toBeEnabled({ timeout: 10000 });
      await approveBtn.click();

      // Today this transition is not signature-gated in the seeded preset
      // (see file header), so no dialog is expected — but handle it
      // defensively in case that config ever changes, so this test does not
      // flake if signature_gate flips to true for "approved" later.
      const dialog = page.locator('[data-testid="signature-dialog"]');
      if (await dialog.isVisible({ timeout: 2000 }).catch(() => false)) {
        await dialog.locator('[data-testid="signature-dialog-credential-input"]').fill('admin12345');
        await dialog.locator('[data-testid="signature-dialog-submit"]').click();
        await expect(dialog).not.toBeVisible({ timeout: 10000 });
      }

      // The review queue is scoped to status=in_review, so an approved
      // requirement drops out of the list.
      await expect(item).not.toBeVisible({ timeout: 10000 });

      const check = await request.get(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(check.ok()).toBeTruthy();
      const body = await check.json();
      expect(body.status).toBe('approved');
    } finally {
      await deleteRequirement(request, token, req.id);
    }
  });

  test('[REQ-144] reject transitions the requirement back to draft', async ({ page, request }) => {
    const token = await getAuthToken();
    const req = await createRequirement(request, token, 'E2E Reject Requirement');
    await apiTransition(request, token, req.id, 'in_review', 'submitting for review');

    try {
      await page.goto(`${FRONTEND_URL}/reviews`);
      const item = page.locator(`[data-testid="review-list-item-${req.id}"]`);
      await expect(item).toBeVisible({ timeout: 10000 });
      await item.click();

      await expect(page.locator('[data-testid="review-detail"]')).toBeVisible({ timeout: 10000 });
      await page
        .locator('[data-testid="review-change-reason-input"]')
        .fill('needs another pass before approval');

      const rejectBtn = page.locator('[data-testid="review-reject-btn"]');
      await expect(rejectBtn).toBeEnabled({ timeout: 10000 });
      await rejectBtn.click();

      await expect(item).not.toBeVisible({ timeout: 10000 });

      const check = await request.get(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(check.ok()).toBeTruthy();
      const body = await check.json();
      expect(body.status).toBe('draft');
    } finally {
      await deleteRequirement(request, token, req.id);
    }
  });

  test('[REQ-144] signature-gated approve opens a modal requiring a credential', async ({
    page,
    request,
  }) => {
    const token = await getAuthToken();
    const req = await createRequirement(request, token, 'E2E Signature Gate Requirement');
    await apiTransition(request, token, req.id, 'in_review', 'submitting for review');

    try {
      // Force signature_gate: true on the "approved" transition so the
      // SignatureDialog path is exercised regardless of the seeded preset's
      // actual configuration (currently signature_gate: False everywhere,
      // see backend/workflow/definition_store.py::_extended_transitions).
      await page.route('**/api/v1/requirements/*/transitions/', async (route: Route) => {
        if (route.request().method() !== 'GET') {
          await route.continue();
          return;
        }
        const response = await route.fetch();
        const json = await response.json();
        json.allowed_transitions = (json.allowed_transitions ?? []).map(
          (t: Record<string, unknown>) =>
            t.target_state === 'approved' ? { ...t, signature_gate: true } : t
        );
        await route.fulfill({ response, json });
      });

      await page.goto(`${FRONTEND_URL}/reviews`);
      const item = page.locator(`[data-testid="review-list-item-${req.id}"]`);
      await expect(item).toBeVisible({ timeout: 10000 });
      await item.click();

      await expect(page.locator('[data-testid="review-detail"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="review-change-reason-input"]').fill('final sign-off');

      const approveBtn = page.locator('[data-testid="review-approve-btn"]');
      await expect(approveBtn).toBeEnabled({ timeout: 10000 });
      await approveBtn.click();

      const dialog = page.locator('[data-testid="signature-dialog"]');
      await expect(dialog).toBeVisible({ timeout: 10000 });

      // Empty credential is blocked client-side.
      await dialog.locator('[data-testid="signature-dialog-submit"]').click();
      await expect(dialog.locator('[data-testid="signature-dialog-error"]')).toBeVisible();

      await dialog.locator('[data-testid="signature-dialog-credential-input"]').fill('admin12345');
      await dialog.locator('[data-testid="signature-dialog-submit"]').click();

      await expect(dialog).not.toBeVisible({ timeout: 10000 });
      await expect(item).not.toBeVisible({ timeout: 10000 });

      const check = await request.get(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(check.ok()).toBeTruthy();
      const body = await check.json();
      expect(body.status).toBe('approved');
    } finally {
      await deleteRequirement(request, token, req.id);
    }
  });

  test('[REQ-144] history tab shows the draft -> in_review transition', async ({
    page,
    request,
  }) => {
    const token = await getAuthToken();
    const req = await createRequirement(request, token, 'E2E History Tab Requirement');
    await apiTransition(request, token, req.id, 'in_review', 'submitting for review');

    try {
      await page.goto(`${FRONTEND_URL}/reviews`);
      const item = page.locator(`[data-testid="review-list-item-${req.id}"]`);
      await expect(item).toBeVisible({ timeout: 10000 });
      await item.click();

      await expect(page.locator('[data-testid="review-detail"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="review-detail-tab-history"]').click();

      const historyList = page.locator('[data-testid="review-history-list"]');
      await expect(historyList).toBeVisible({ timeout: 10000 });
      await expect(historyList).toContainText('draft');
      await expect(historyList).toContainText('in_review');
    } finally {
      await deleteRequirement(request, token, req.id);
    }
  });
});
