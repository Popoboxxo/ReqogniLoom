// REQ-144: Review/Approval UI — draft -> in_review -> approved workflow,
// including the reject path and the signature-gated approve path.
//
// Written against the same conventions as e2e/tests/requirements.spec.ts and
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
//
// ---------------------------------------------------------------------------
// fix F2 — hardened against fixture accumulation and client-side pagination
// ---------------------------------------------------------------------------
// This spec shares SEEDED_WORKSPACE_ID with every other spec in the suite and
// used to create its fixtures under five FIXED titles. Two consequences made
// the assertions position- and history-dependent:
//
//  1. Cleanup only ran in the `finally` of a *successful* run, so an aborted or
//     timed-out run left its `in_review` fixture behind (27 stale fixtures were
//     observed in the shared workspace). The next run then found an item in the
//     queue it did not create — and one more after every aborted run.
//  2. The reviews queue fetches *all* pages but renders only a
//     REVIEWS_PAGE_SIZE slice of them (frontend/src/components/Reviews/
//     ReviewsView.tsx paginates client-side; the slice is applied AFTER the
//     search filter). Once the shared workspace holds more in_review items
//     than fit into that slice, this spec's own row falls off the rendered
//     page and the `review-list-item-<id>` assertion fails against a queue
//     that does contain the item. The backend list order is unordered
//     (requirement_service.list_requirements has no order_by), so position-
//     based assertions were flaky regardless of the page size.
//
// Hardening, no product code touched BY THIS FIX (frontend/ and backend/ are
// unmodified here — the branch may contain other fixes' backend changes):
//  * every fixture title carries a per-run RUN_ID under the stable spec prefix
//    `E2E-RW-`, so runs cannot collide and a leftover is always attributable;
//  * a beforeAll hook sweeps this spec's own legacy fixed titles plus every
//    `E2E-RW-*` leftover, scoped strictly by title — never by status, position
//    or count, so other specs' fixtures (notably toothbrush-syseng's in_review
//    seed) survive untouched;
//  * every visibility assertion goes through the reviews search box. The
//    client-side search filter runs BEFORE the page slice, so narrowing to the
//    unique run title makes the assertion independent of how many items other
//    specs left in the queue — and of REVIEWS_PAGE_SIZE, which is never
//    referenced here;
//  * deletion failures are collected and asserted in afterAll instead of being
//    thrown from a test's `finally`, where they would mask the real failure
//    (same pattern as e2e/tests/toothbrush-syseng.spec.ts).
import {
  test,
  expect,
  request as playwrightRequest,
  APIRequestContext,
  Page,
  Route,
} from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
import { deleteRequirement as deleteRequirementFixture } from '../helpers/cleanup';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

interface CreatedRequirement {
  id: string;
  title: string;
}

/** One row of the paginated requirement list endpoint. */
interface RequirementRow {
  id: string;
  title: string;
}

// ---------------------------------------------------------------------------
// Per-run fixture identity (fix F2, deliverable 1)
// ---------------------------------------------------------------------------

/**
 * Stable prefix identifying every fixture THIS spec ever created, across all
 * runs. Used by the stale-fixture sweep to find leftovers of aborted runs.
 */
const SPEC_FIXTURE_PREFIX = 'E2E-RW-';

/** Date.now() + short random suffix — unique per spec run. */
const RUN_ID = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;

/** Prefix shared by this run's fixtures only. */
const RUN_FIXTURE_PREFIX = `${SPEC_FIXTURE_PREFIX}${RUN_ID}-`;

/** This run's fixture titles. No globally fixed title remains in this spec. */
const RUN_TITLES = {
  queue: `${RUN_FIXTURE_PREFIX}queue`,
  approve: `${RUN_FIXTURE_PREFIX}approve`,
  reject: `${RUN_FIXTURE_PREFIX}reject`,
  signature: `${RUN_FIXTURE_PREFIX}signature`,
  history: `${RUN_FIXTURE_PREFIX}history`,
} as const;

/**
 * The fixed titles this spec used before the per-run rename. They are only
 * kept as *sweep targets*: every one of them identifies a fixture that a
 * previous, aborted run left behind, so each run still deletes them.
 */
const LEGACY_FIXED_TITLES: readonly string[] = [
  'E2E Review Queue Requirement',
  'E2E Approve Requirement',
  'E2E Reject Requirement',
  'E2E Signature Gate Requirement',
  'E2E History Tab Requirement',
];

/**
 * API search terms that surface this spec's own fixtures: the shared prefix
 * (any previous run) plus each legacy fixed title.
 */
const SWEEP_SEARCH_TERMS: readonly string[] = [
  SPEC_FIXTURE_PREFIX,
  ...LEGACY_FIXED_TITLES,
];

/** change_reason recorded on a cleanup delete (mandatory in the `extended` preset). */
const SWEEP_CHANGE_REASON = 'E2E stale-fixture sweep (review-workflow.spec.ts)';

/**
 * True when a title belongs to THIS spec (any run) and may therefore be swept.
 *
 * The check is deliberately title-only and exact: the API `search` parameter
 * matches title, description AND uid, so a term like `E2E-RW-` can also return
 * foreign rows whose description merely mentions it. Only an exact title match
 * is deleted — never "something that looks like ours".
 */
function isOwnFixtureTitle(title: string): boolean {
  return (
    title.startsWith(SPEC_FIXTURE_PREFIX) || LEGACY_FIXED_TITLES.includes(title)
  );
}

/** Every fixture this run created, so afterAll can sweep what a test left behind. */
const runFixtures: CreatedRequirement[] = [];

/**
 * Deletion failures, asserted once in `test.afterAll`.
 *
 * Throwing them from a test's `finally` would replace the real assertion error
 * with the cleanup's error and hide what actually broke (toothbrush-syseng
 * pattern, issue #947 review F-4).
 */
const cleanupErrors: string[] = [];

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

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
      // #412: the approve gate rejects an in_review -> approved transition
      // while a preset-mandatory field is empty ("the 'extended' preset
      // requires the following field(s) to be filled in first:
      // acceptance_criteria"). Without this the approve tests below can never
      // pass — the POST 400s, the signature dialog stays open and the item
      // stays in the queue.
      acceptance_criteria: 'Given the review queue, when approved, then the status is approved.',
      // #272 (spec section 7.2): `verification_method` joined the Extended
      // approval gate's mandatory fields. Same failure mode as
      // acceptance_criteria above — omit it and the approve POST 400s, the
      // signature dialog stays open and the item stays in the queue. The
      // requirement defaults to `type: 'SyReq'`, so the value is accepted and
      // persisted; 'Test' mirrors the backend policy fixture
      // (test_se_validation_remainder_272.py).
      verification_method: 'Test',
    },
  });
  expect(response.ok()).toBeTruthy();
  const body = await response.json();
  const created = { id: body.id as string, title: body.title as string };
  runFixtures.push(created);
  return created;
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
  // Issue #1115: a rejected transition must surface as such. The old
  // `expect(response.ok()).toBeTruthy()` produced only a generic assertion
  // failure and the actual reason — e.g. HTTP 400 "Transition not allowed:
  // 'draft' -> 'in_review' is not defined" from a workspace whose workflow
  // lacks the edge, or a missing mandatory review-gate field — never appeared
  // in the error. Include status and backend error body in the diagnostic.
  if (!response.ok()) {
    const body = await response.text();
    throw new Error(
      `apiTransition: '${targetState}' rejected with HTTP ${response.status()} for ` +
        `requirement ${id}: ${body}`
    );
  }
}

/**
 * Soft-delete a fixture, capturing the failure instead of throwing it.
 *
 * Issue #947: delegates to the shared helper, which sends the `change_reason`
 * the `extended` preset mandates and inspects the response (a body-less DELETE
 * was answered with 400 and silently left every fixture behind).
 */
async function deleteRequirement(
  request: APIRequestContext,
  token: string,
  fixture: CreatedRequirement
): Promise<void> {
  try {
    await deleteRequirementFixture(
      request,
      token,
      fixture.id,
      'E2E cleanup (review-workflow.spec.ts)'
    );
  } catch (error) {
    cleanupErrors.push(
      `deleteRequirement(${fixture.title}, ${fixture.id}): ${
        error instanceof Error ? error.message : String(error)
      }`
    );
  }
}

/**
 * List requirements in the seeded workspace matching `search`, walking every
 * page of the paginated list (default page size is 25, the noise in this
 * workspace is in the hundreds).
 */
async function listRequirementsBySearch(
  request: APIRequestContext,
  token: string,
  search: string
): Promise<RequirementRow[]> {
  const headers = { Authorization: `Bearer ${token}` };
  const rows: RequirementRow[] = [];
  const seen = new Set<string>();
  const visited = new Set<string>();
  let url: string | null = '/api/v1/requirements/';
  let params: Record<string, string> | undefined = {
    workspace_id: SEEDED_WORKSPACE_ID,
    search,
    page_size: '100',
  };
  while (url && !visited.has(url)) {
    visited.add(url);
    const response = params
      ? await request.get(url, { headers, params })
      : await request.get(url, { headers });
    if (!response.ok()) {
      throw new Error(
        `listRequirementsBySearch('${search}') failed: HTTP ${response.status()} ` +
          `${await response.text()}`
      );
    }
    const body = await response.json();
    const items: RequirementRow[] = Array.isArray(body)
      ? body
      : (body.results ?? []);
    for (const item of items) {
      if (item.id && item.title && !seen.has(item.id)) {
        seen.add(item.id);
        rows.push({ id: item.id, title: item.title });
      }
    }
    // `next` carries its own query string; the response envelope may also be a
    // bare array (older deployments), which has no `next` at all.
    url = Array.isArray(body) ? null : (body.next ?? null);
    params = undefined;
  }
  return rows;
}

/**
 * Stale-fixture sweep (fix F2, deliverable 2): delete this spec's own
 * leftovers — the five legacy fixed titles plus every `E2E-RW-*` fixture of any
 * previous run — in the seeded workspace.
 *
 * Scoped by own prefix/known titles ONLY. Other specs' fixtures are never
 * touched: no status filter, no "everything in_review", no count-based rule.
 * toothbrush-syseng's in_review seed and the hundreds of other specs'
 * leftovers therefore survive this sweep untouched.
 *
 * @returns number of leftover fixtures that were deleted.
 */
async function sweepOwnFixtures(
  request: APIRequestContext,
  token: string
): Promise<number> {
  const candidates = new Map<string, string>();
  for (const term of SWEEP_SEARCH_TERMS) {
    for (const row of await listRequirementsBySearch(request, token, term)) {
      if (isOwnFixtureTitle(row.title)) {
        candidates.set(row.id, row.title);
      }
    }
  }
  for (const [id, title] of candidates) {
    try {
      await deleteRequirementFixture(request, token, id, SWEEP_CHANGE_REASON);
    } catch (error) {
      cleanupErrors.push(
        `sweep ${title} (${id}): ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }
  return candidates.size;
}

// ---------------------------------------------------------------------------
// UI helpers — pagination-tolerant review-queue interaction (fix F2)
// ---------------------------------------------------------------------------

/**
 * Open a review-queue row WITHOUT depending on its page position.
 *
 * The queue fetches every page of in_review requirements but renders only a
 * REVIEWS_PAGE_SIZE slice of them, so with enough accumulated fixtures the
 * target row lands outside the rendered page. The client-side search filter is
 * applied BEFORE the slice (ReviewsView.tsx filters `items`, then pages), so
 * narrowing to this run's unique title makes the row the only candidate —
 * independent of how much other specs left behind and of the page size itself.
 */
async function openReviewQueueItem(
  page: Page,
  title: string,
  id: string
): Promise<void> {
  const item = page.locator(`[data-testid="review-list-item-${id}"]`);
  await page.locator('[data-testid="reviews-search-input"]').fill(title);
  await expect(item).toBeVisible({ timeout: 20000 });
  await expect(item).toContainText(title);
  await item.click();
}

/**
 * Assert that a requirement has left the review queue, via the same search
 * filter — never via a page position or an absolute count.
 *
 * The empty state is asserted as well: `review-list-item-<id>` disappearing on
 * its own could be a not-yet-refetched render, whereas the "nothing pending"
 * message only appears once the refetch completed and returned zero rows for
 * this search.
 */
async function expectLeftReviewQueue(page: Page, id: string): Promise<void> {
  const item = page.locator(`[data-testid="review-list-item-${id}"]`);
  await expect(item).not.toBeVisible({ timeout: 20000 });
  await expect(page.locator('[data-testid="reviews-empty"]')).toBeVisible({
    timeout: 20000,
  });
}

test.describe('[COMP-RF-REV] Reviews view (REQ-144)', () => {
  // fix F2: clear this spec's own leftovers from previous (aborted) runs before
  // asserting anything, so the run starts from a queue that contains only its
  // own fixtures. Scoped by title prefix — see sweepOwnFixtures.
  test.beforeAll(async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BACKEND_URL });
    try {
      const token = await getAuthToken();
      const swept = await sweepOwnFixtures(ctx, token);
      if (swept > 0) {
        console.log(
          `review-workflow: swept ${swept} stale fixture(s) left by a previous run`
        );
      }
    } finally {
      await ctx.dispose();
    }
  });

  // Issue #947 review F-4: cleanup failures are asserted here, after the test
  // body has already reported its own result. Running them in the test's
  // `finally` made a cleanup error mask the real assertion error.
  //
  // fix F2: this also re-sweeps the spec's own prefixes/titles, so a run that
  // died hard (worker crash, timeout abort, `--last-failed` re-run) still
  // leaves nothing behind for the next run to trip over.
  test.afterAll(async () => {
    const ctx = await playwrightRequest.newContext({ baseURL: BACKEND_URL });
    try {
      const token = await getAuthToken();
      // 1. Fixtures this run created but no test managed to delete (already
      //    deleted ones answer 404, which the shared helper treats as success).
      for (const fixture of runFixtures) {
        await deleteRequirement(ctx, token, fixture);
      }
      // 2. Leftovers of any aborted run, including this one's.
      const swept = await sweepOwnFixtures(ctx, token);
      if (swept > 0) {
        console.log(`review-workflow: swept ${swept} stale fixture(s) after the run`);
      }
    } finally {
      await ctx.dispose();
    }
    expect(
      cleanupErrors,
      `fixture cleanup failed — the seeded workspace keeps these artifacts:\n${cleanupErrors.join('\n')}`
    ).toEqual([]);
  });

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
    const req = await createRequirement(request, token, RUN_TITLES.queue);
    await apiTransition(request, token, req.id, 'in_review', 'submitting for review');

    try {
      await page.goto(`${FRONTEND_URL}/reviews`);
      await expect(page.locator('[data-testid="reviews-view"]')).toBeVisible({ timeout: 10000 });

      // Pagination-tolerant: search for the run's own title first (see
      // openReviewQueueItem), so the assertion holds no matter how many items
      // other specs left in the shared queue.
      await openReviewQueueItem(page, req.title, req.id);
    } finally {
      await deleteRequirement(request, token, req);
    }
  });

  test('[REQ-144] approve transitions the requirement to approved and removes it from the queue', async ({
    page,
    request,
  }) => {
    const token = await getAuthToken();
    const req = await createRequirement(request, token, RUN_TITLES.approve);
    await apiTransition(request, token, req.id, 'in_review', 'submitting for review');

    try {
      await page.goto(`${FRONTEND_URL}/reviews`);
      await openReviewQueueItem(page, req.title, req.id);

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
      // requirement drops out of the list — asserted through the search
      // filter, not through a page position.
      await expectLeftReviewQueue(page, req.id);

      const check = await request.get(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(check.ok()).toBeTruthy();
      const body = await check.json();
      expect(body.status).toBe('approved');
    } finally {
      await deleteRequirement(request, token, req);
    }
  });

  test('[REQ-144] reject transitions the requirement back to draft', async ({ page, request }) => {
    const token = await getAuthToken();
    const req = await createRequirement(request, token, RUN_TITLES.reject);
    await apiTransition(request, token, req.id, 'in_review', 'submitting for review');

    try {
      await page.goto(`${FRONTEND_URL}/reviews`);
      await openReviewQueueItem(page, req.title, req.id);

      await expect(page.locator('[data-testid="review-detail"]')).toBeVisible({ timeout: 10000 });
      await page
        .locator('[data-testid="review-change-reason-input"]')
        .fill('needs another pass before approval');

      const rejectBtn = page.locator('[data-testid="review-reject-btn"]');
      await expect(rejectBtn).toBeEnabled({ timeout: 10000 });
      await rejectBtn.click();

      // A rejected item leaves the in_review queue again — asserted via search.
      await expectLeftReviewQueue(page, req.id);

      const check = await request.get(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(check.ok()).toBeTruthy();
      const body = await check.json();
      expect(body.status).toBe('draft');
    } finally {
      await deleteRequirement(request, token, req);
    }
  });

  test('[REQ-144] signature-gated approve opens a modal requiring a credential', async ({
    page,
    request,
  }) => {
    const token = await getAuthToken();
    const req = await createRequirement(request, token, RUN_TITLES.signature);
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
      await openReviewQueueItem(page, req.title, req.id);

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
      await expectLeftReviewQueue(page, req.id);

      const check = await request.get(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(check.ok()).toBeTruthy();
      const body = await check.json();
      expect(body.status).toBe('approved');
    } finally {
      await deleteRequirement(request, token, req);
    }
  });

  test('[REQ-144] history tab shows the draft -> in_review transition', async ({
    page,
    request,
  }) => {
    const token = await getAuthToken();
    const req = await createRequirement(request, token, RUN_TITLES.history);
    await apiTransition(request, token, req.id, 'in_review', 'submitting for review');

    try {
      await page.goto(`${FRONTEND_URL}/reviews`);
      await openReviewQueueItem(page, req.title, req.id);

      await expect(page.locator('[data-testid="review-detail"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="review-detail-tab-history"]').click();

      const historyList = page.locator('[data-testid="review-history-list"]');
      await expect(historyList).toBeVisible({ timeout: 10000 });
      await expect(historyList).toContainText('draft');
      await expect(historyList).toContainText('in_review');
    } finally {
      await deleteRequirement(request, token, req);
    }
  });
});
