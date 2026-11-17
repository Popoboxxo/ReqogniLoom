// @mobile — mobile smoke suite (plan M0, REQ-215).
//
// This suite is deliberately shallow: it does not verify feature behaviour,
// only that the shell renders and the document does not scroll sideways on a
// phone. It is tagged `@mobile` so the four desktop shards skip it; the
// dedicated fifth CI shard runs the two device projects against it.
//
// S0.4 CI fix: the final `openFirstListItem('/requirements')` step used the
// shared demo seed, which has no guaranteed rows in CI. Seed one requirement
// through the REST API into an isolated workspace and point the app at it, so
// the list/detail step has a deterministic target on both device projects.
import { test, expect, type Page, type APIRequestContext } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  createIsolatedWorkspace,
  setWorkspaceId,
  deleteWorkspace,
  purgeWorkspaceBaselines,
  closeWorkspace,
} from '../helpers/auth';
import { expectNoHorizontalDocumentScroll, openFirstListItem } from '../helpers/mobile';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

const ROUTES: Array<[string, string]> = [
  ['dashboard', '/'],
  ['requirements', '/requirements'],
  ['documents', '/documents'],
  ['traceability', '/traceability'],
  ['connections', '/connections'],
];

test.describe('@mobile shell smoke', () => {
  test('all routes fit the viewport and list/detail is usable', async ({ page, request }: { page: Page; request: APIRequestContext }) => {
    const token = await getAuthToken();
    const workspaceName = `e2e-mobile-smoke-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const workspaceId = await createIsolatedWorkspace(token, workspaceName);
    const seed = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: workspaceId,
        title: `E2E mobile smoke requirement ${Date.now()}`,
        category: 'Functional',
      },
    });
    expect(
      seed.ok(),
      `requirement seed failed: ${seed.status()} ${await seed.text()}`
    ).toBeTruthy();
    // addInitScript applies on the next navigation — point the app at the
    // seeded workspace before login navigates.
    await setWorkspaceId(page, workspaceId);

    try {
      await loginAsAdmin(page);

      for (const [name, path] of ROUTES) {
        await test.step(`route ${path}`, async () => {
          await page.goto(path);
          // Wait for the route's async data instead of screenshotting the
          // loading skeleton (React Query fetches after the first paint).
          await page.locator('main').first().waitFor({ state: 'visible' });
          await expectNoHorizontalDocumentScroll(page);

          if (test.info().project.name === 'mobile-safari') {
            // Only one project writes baselines; two device snapshots of the
            // same route would double the review surface without new signal.
            await page.screenshot({
              // e2e/test-results/ is gitignored; the CI report artifact keeps
              // these for the M0 audit without committing a baseline we cannot
              // generate until the stack is available.
              path: `test-results/mobile-baseline/mobile-${name}.png`,
              animations: 'disabled',
            });
          }
        });
      }

      // The core mobile flow from Spec §4.1 / REQ-209: a list item opens the
      // detail as a replacement for the list, not as a second narrow column.
      await page.goto('/requirements');
      await openFirstListItem(page);
      await expectNoHorizontalDocumentScroll(page);
    } finally {
      // Best-effort teardown; cleanup must never fail the test.
      await purgeWorkspaceBaselines(token, workspaceId);
      if (!(await deleteWorkspace(token, workspaceId, workspaceName))) {
        await closeWorkspace(token, workspaceId);
      }
    }
  });
});
