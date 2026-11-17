// @mobile — list → detail → back across the artifact routes (plan M5, REQ-209).
// The regression: on a phone, opening a detail rendered the two-column
// desktop branch instead of replacing the list. Each route is its own test so
// one failing route can never hide the others.
//
// S0.4 CI fix: the old version asserted `rows.count() > 0` against demo seed
// data, which does not exist for most routes in CI (and the shared seed
// workspace is mutated by other parallel shards). Every test now creates its
// OWN artifact via the REST API in an isolated workspace, points the app at
// that workspace, and removes the workspace in `finally`. No environment
// dependency, no `test.skip(true)`, no false-green emptiness branch.
import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  createIsolatedWorkspace,
  deleteWorkspace,
  purgeWorkspaceBaselines,
  closeWorkspace,
  setWorkspaceId,
} from '../helpers/auth';
import { LIST_ROW_SELECTOR, openFirstListItem } from '../helpers/mobile';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

const ROUTES = [
  '/requirements',
  '/needs',
  '/risks',
  '/issues',
  '/adrs',
  '/testcases',
  '/glossary',
  '/baselines',
];

interface SeededWorkspace {
  workspaceId: string;
  workspaceName: string;
}

/**
 * Create exactly one artifact of the type backing `route` in a fresh isolated
 * workspace and point the page at that workspace on its next navigation.
 *
 * The create payloads mirror the frontend API modules (frontend/src/api/*) and
 * existing passing specs — they are the real REST contracts, not mocks:
 *  - requirements / testcases / risks / issues / adrs / glossary take
 *    `workspace_id` in the body;
 *  - needs are workspace-nested (`POST /workspaces/{id}/needs/`) so the id is
 *    in the path, not the body;
 *  - baselines take `workspace_id`, `name`, `scope` (see baselines-tags.spec.ts).
 */
async function seedRoute(
  request: APIRequestContext,
  page: Page,
  route: string,
  token: string
): Promise<SeededWorkspace> {
  const slug = route.replace(/^\//, '') || 'root';
  const workspaceName = `e2e-mobile-${slug}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const workspaceId = await createIsolatedWorkspace(token, workspaceName);
  const headers = { Authorization: `Bearer ${token}` };
  const stamp = Date.now();

  let url: string;
  let data: Record<string, unknown>;
  switch (route) {
    case '/requirements':
      url = `${BACKEND_URL}/api/v1/requirements/`;
      data = { workspace_id: workspaceId, title: `E2E mobile requirement ${stamp}`, category: 'Functional' };
      break;
    case '/needs':
      url = `${BACKEND_URL}/api/v1/workspaces/${workspaceId}/needs/`;
      data = { title: `E2E mobile need ${stamp}`, description: 'Mobile list/detail seed', moscow_priority: 'Must' };
      break;
    case '/risks':
      url = `${BACKEND_URL}/api/v1/risks/`;
      data = { workspace_id: workspaceId, title: `E2E mobile risk ${stamp}` };
      break;
    case '/issues':
      url = `${BACKEND_URL}/api/v1/issues/`;
      data = { workspace_id: workspaceId, title: `E2E mobile issue ${stamp}` };
      break;
    case '/adrs':
      url = `${BACKEND_URL}/api/v1/adrs/`;
      data = { workspace_id: workspaceId, title: `E2E mobile ADR ${stamp}` };
      break;
    case '/testcases':
      url = `${BACKEND_URL}/api/v1/testcases/`;
      data = { workspace_id: workspaceId, title: `E2E mobile test case ${stamp}`, test_type: 'unit' };
      break;
    case '/glossary':
      url = `${BACKEND_URL}/api/v1/glossary/`;
      data = { workspace_id: workspaceId, term: `E2E mobile term ${stamp}`, definition: 'Mobile list/detail seed' };
      break;
    case '/baselines':
      url = `${BACKEND_URL}/api/v1/baselines/`;
      data = { workspace_id: workspaceId, name: `e2e-mobile-baseline-${stamp}`, scope: 'project' };
      break;
    default:
      throw new Error(`No seed recipe defined for mobile route ${route}`);
  }

  const seed = await request.post(url, { headers, data });
  expect(
    seed.ok(),
    `${route} seed failed: POST ${url} -> ${seed.status()} ${await seed.text()}`
  ).toBeTruthy();

  // addInitScript applies on the next navigation — point the app at the seeded
  // workspace before login navigates (same pattern as the other workspace-
  // scoped specs). setWorkspaceId registers an init script, so it survives the
  // login redirect and every subsequent page.goto in this test.
  await setWorkspaceId(page, workspaceId);
  return { workspaceId, workspaceName };
}

/** Best-effort teardown. Never turns a green test red (helper contract). */
async function cleanupWorkspace(token: string, ws: SeededWorkspace): Promise<void> {
  // A workspace holding a baseline cannot be hard-deleted until it is purged
  // (GH-1084). Purge is a no-op for the other routes. Fall back to a soft close
  // if the hard delete is still refused for any reason.
  await purgeWorkspaceBaselines(token, ws.workspaceId);
  const deleted = await deleteWorkspace(token, ws.workspaceId, ws.workspaceName);
  if (!deleted) {
    await closeWorkspace(token, ws.workspaceId);
  }
}

test.describe('@mobile list/detail flow', () => {
  for (const route of ROUTES) {
    test(`${route}: detail replaces the list and the back step returns`, { tag: '@mobile' }, async ({ page, request }: { page: Page; request: APIRequestContext }) => {
      const token = await getAuthToken();
      const ws = await seedRoute(request, page, route, token);

      try {
        await loginAsAdmin(page);
        await page.goto(route);
        await expect(page.getByTestId('splitview-list')).toBeVisible();

        const rows = page.locator(LIST_ROW_SELECTOR);
        // Explicit state wait on the seeded row (not a fixed timeout); the
        // count assertion then proves the precondition deterministically.
        await expect(rows.first(), `${route}: seeded list row never became visible`).toBeVisible({ timeout: 10000 });
        expect(await rows.count(), `${route}: expected at least one seeded list row`).toBeGreaterThan(0);

        await openFirstListItem(page);
        await expect(page.getByTestId('splitview-list')).toBeHidden();
        await expect(page.getByTestId('splitview-detail')).toBeVisible();

        await page.getByTestId('splitview-back').click();
        await expect(page.getByTestId('splitview-list')).toBeVisible();
        await expect(page.getByTestId('splitview-detail')).toBeHidden();
      } finally {
        await cleanupWorkspace(token, ws);
      }
    });
  }
});
