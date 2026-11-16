// Slice 5 (task 5.1) — the artifact table view guardrail
// (plan 2026-11-04-tabellenansicht-neu.md).
//
// The unit suites prove the pieces in isolation; this spec proves the *user
// flow* on the Requirements page: open the table, sort, filter (state survives
// a reload), hide a column (state survives a reload), bulk-edit/bulk-transition
// as exactly one request, inline edit through the single-item path and the 412
// conflict marker, and a saved view round trip.
//
// Isolation follows connection-view.spec.ts: every test creates its own
// workspace plus two requirement fixtures and hard-deletes the workspace. No
// test touches the seeded demo workspace, and the browser context of a test
// starts with an empty localStorage, so the "table" view mode is always
// reached by clicking the toggle (`req-view-toggle-table`) rather than by a
// leaked preference.
//
// IMPORTANT — slice dependency: the read side of the table
// (`GET /api/v1/artifacts/table/`, slice 1) is *not* part of the S2–S4 stack
// this branch builds on (checked on main and on feat/tableview-s3). The spec
// therefore probes that route once and skips the whole describe with an
// explicit reason instead of failing 10 tests or — worse — asserting an empty
// table ("0 rows rendered") and passing. The moment slice 1 lands the guard
// starts running the real flows; see #1874 (table-view rollout).
//
// List-only validation (no live stack needed):
//   cd e2e && npx playwright test artifact-table --list

import {
  test,
  expect,
  type APIRequestContext,
  type Page,
  type Request,
  type Response,
} from '@playwright/test';
import {
  createIsolatedWorkspace,
  deleteWorkspace,
  getAuthToken,
  loginAsAdmin,
  setWorkspaceId,
} from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

const TABLE_URL = `${BACKEND_URL}/api/v1/artifacts/table/`;
const TABLE_PATH = '/api/v1/artifacts/table/';
const BULK_UPDATE_URL = '/api/v1/artifacts/bulk-update/';
const BULK_TRANSITION_URL = '/api/v1/artifacts/bulk-transition/';
const TABLE_STATE_URL = '/api/v1/users/me/table-view-state/';
const SAVED_VIEWS_URL = '/api/v1/saved-views/';
const SAVED_VIEWS_PATH = '/api/v1/saved-views/';
const REQUIREMENT_TRANSITIONS_PATH = (id: string): string =>
  `/api/v1/requirements/${id}/transitions/`;

const TITLE_ALPHA = 'Alpha table fixture';
const TITLE_BETA = 'Beta table fixture';

interface RequirementFixture {
  id: string;
  version: number;
}

let token: string;
let workspaceId: string;
let workspaceName: string;
let alpha: RequirementFixture;
let beta: RequirementFixture;

/** Collect matching requests for the whole page lifetime of one test. */
function track(
  page: Page,
  match: (request: Request) => boolean
): Request[] {
  const hits: Request[] = [];
  page.on('request', (request) => {
    if (match(request)) hits.push(request);
  });
  return hits;
}

/**
 * Match the table read **by path**, not by origin.
 *
 * The page requests its own origin (`FRONTEND_URL`) and the Vite/nginx proxy
 * forwards `/api` to the backend, so `request.url()` never starts with
 * `BACKEND_URL` — the pre-fix `startsWith(TABLE_URL)` matcher caught nothing
 * and every `expect.poll` on the tracked requests read `null`. `TABLE_URL`
 * stays for the `APIRequestContext` probe in `beforeAll`, which *does* talk to
 * the backend directly.
 */
function isTableQuery(request: Request): boolean {
  return (
    request.method() === 'GET' &&
    new URL(request.url()).pathname === TABLE_PATH
  );
}

async function createRequirement(
  request: APIRequestContext,
  title: string
): Promise<RequirementFixture> {
  const response = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      workspace_id: workspaceId,
      title,
      description: `E2E artifact-table fixture: ${title}`,
      category: 'Functional',
      // The `standard` preset gates ``approved`` on an acceptance criterion —
      // omitting it makes the bulk-transition flow answer 200 with every row
      // in ``failed[]``, which is exactly the false green this spec must catch.
      acceptance_criteria: `Given ${title}, when approved, then it is approved.`,
    },
  });
  expect(response.status()).toBe(201);
  const body = (await response.json()) as { id: string; version: number };
  return { id: body.id, version: body.version };
}

async function readRequirement(
  request: APIRequestContext,
  id: string
): Promise<{ title: string; version: number }> {
  const response = await request.get(`${BACKEND_URL}/api/v1/requirements/${id}/`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as { title: string; version: number };
}

interface TransitionsBody {
  current_state: string | null;
  allowed_transitions: Array<{ target_state: string }>;
}

/**
 * Read the row's own workflow graph — the single source of truth for "which
 * moves are legal from here".
 *
 * The table's status dropdown derives its options from exactly this endpoint,
 * so a test that hardcodes a target state asserts a state the workspace may not
 * declare (`standard` has `draft -> approved`, `extended` has
 * `draft -> in_review -> approved`). Reading it here keeps the spec honest and
 * makes the chosen target explain itself in the failure message.
 */
async function readTransitions(
  request: APIRequestContext,
  id: string
): Promise<TransitionsBody> {
  const response = await request.get(
    `${BACKEND_URL}${REQUIREMENT_TRANSITIONS_PATH(id)}`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  expect(
    response.ok(),
    `GET ${REQUIREMENT_TRANSITIONS_PATH(id)} answered ${response.status()}`
  ).toBeTruthy();
  return (await response.json()) as TransitionsBody;
}

/** The table only renders when `canRead` and the rows query resolved. */
async function openTableView(page: Page): Promise<void> {
  await page.goto(`${FRONTEND_URL}/requirements`);
  await page.getByTestId('req-view-toggle-table').click();
  await expect(page.getByTestId('artifact-table-view')).toBeVisible();
  // The grid header proves the definition resolved; the row proves the query
  // answered. An error banner instead means the read slice is not deployed.
  await expect(page.getByTestId('artifact-table')).toBeVisible();
  await expect(page.getByTestId(`table-row-${alpha.id}`)).toBeVisible();
  await expect(page.getByTestId(`table-row-${beta.id}`)).toBeVisible();
}

/** Apply `title contains <value>` through the header filter popover. */
async function filterByTitle(page: Page, value: string): Promise<void> {
  await page.getByTestId('filter-trigger-title').click();
  await expect(page.getByTestId('filter-popover-title')).toBeVisible();
  await page.getByTestId('filter-title-contains').fill(value);
  await page.getByTestId('filter-close-title').click();
  await expect(page.getByTestId('filter-popover-title')).toHaveCount(0);
}

/** Wait for the debounced per-user table-state write. */
function nextTableStateWrite(page: Page): Promise<Response> {
  return page.waitForResponse(
    (response) =>
      response.url().includes(TABLE_STATE_URL) &&
      response.request().method() === 'PUT'
  );
}

test.describe('Artifact table view', () => {
  let readEndpointAvailable = false;

  test.beforeAll(async ({ request }) => {
    // Authenticated probe: an undeployed route answers 404, a deployed one
    // rejects the missing query parameters (400). A 404 on the *route* is the
    // only thing this guard treats as "slice 1 not here".
    const probeToken = await getAuthToken();
    const response = await request.get(TABLE_URL, {
      headers: { Authorization: `Bearer ${probeToken}` },
    });
    readEndpointAvailable = response.status() !== 404;
  });

  test.beforeEach(async ({ page, request }) => {
    test.skip(
      !readEndpointAvailable,
      `GET /api/v1/artifacts/table/ is not deployed on this stack (slice 1, #1874) — ` +
        'run this spec against a stack built from slices 1–4.'
    );

    token = await getAuthToken();
    workspaceName = `e2e-artifact-table-${Date.now()}-${Math.random()
      .toString(36)
      .slice(2, 8)}`;
    workspaceId = await createIsolatedWorkspace(token, workspaceName);

    alpha = await createRequirement(request, TITLE_ALPHA);
    beta = await createRequirement(request, TITLE_BETA);

    await setWorkspaceId(page, workspaceId);
    await loginAsAdmin(page);
  });

  test.afterEach(async () => {
    await deleteWorkspace(token, workspaceId, workspaceName);
  });

  test('opens the table from the requirements toggle and shows rows and columns', async ({
    page,
  }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await expect(page.getByTestId('req-view-toggle-list')).toHaveAttribute(
      'aria-pressed',
      'true'
    );

    await page.getByTestId('req-view-toggle-table').click();
    await expect(page.getByTestId('req-view-toggle-table')).toHaveAttribute(
      'aria-pressed',
      'true'
    );
    await expect(page.getByTestId('artifact-table-view')).toBeVisible();
    await expect(page.getByTestId('artifact-table')).toBeVisible();

    // Columns come from the resolved attribute definition, not a hardcoded UI
    // list: title and status are core Requirement attributes.
    await expect(page.getByTestId('sort-title')).toBeVisible();
    await expect(page.getByTestId('sort-status')).toBeVisible();

    await expect(page.getByTestId(`table-row-${alpha.id}`)).toBeVisible();
    await expect(page.getByTestId(`table-row-${beta.id}`)).toBeVisible();
    await expect(page.getByTestId(`cell-${alpha.id}-title`)).toHaveText(
      TITLE_ALPHA
    );
  });

  test('sorts by a column header and sends the sort term to the table query', async ({
    page,
  }) => {
    await openTableView(page);

    const tableRequests = track(page, isTableQuery);

    const header = page.getByTestId('sort-title');
    await header.click();

    // The query always carries `sort` (an empty array before the first click),
    // so wait for the parsed *term*, not merely for a request.
    const lastSort = (): unknown => {
      const last = tableRequests[tableRequests.length - 1];
      if (!last) return null;
      const raw = new URL(last.url()).searchParams.get('sort');
      return raw ? JSON.parse(raw) : null;
    };
    await expect.poll(lastSort, { timeout: 15000 }).toEqual([
      { field: 'title', dir: 'asc' },
    ]);

    // The header reflects the direction, which is what a screen reader sees.
    await expect(page.locator('th[aria-sort="ascending"]')).toHaveCount(1);

    await header.click();
    await expect.poll(lastSort, { timeout: 15000 }).toEqual([
      { field: 'title', dir: 'desc' },
    ]);
    await expect(page.locator('th[aria-sort="descending"]')).toHaveCount(1);
  });

  test('adds a filter chip, carries the filter in the request URL and keeps it across reload', async ({
    page,
  }) => {
    await openTableView(page);

    const tableRequests = track(page, isTableQuery);

    const stateWrite = nextTableStateWrite(page);
    await filterByTitle(page, 'Alpha');
    await stateWrite;

    await expect(page.getByTestId('filter-chip-remove-title-0')).toBeVisible();
    // The constraint goes to the server as the frozen DSL, not as a client-only
    // search box: the request URL carries the JSON filter.
    await expect
      .poll(
        () => {
          const last = tableRequests[tableRequests.length - 1];
          if (!last) return null;
          const raw = new URL(last.url()).searchParams.get('filters');
          return raw ? JSON.parse(raw) : null;
        },
        { timeout: 15000 }
      )
      .toEqual({ title: { op: 'contains', value: 'Alpha' } });

    await expect(page.getByTestId(`table-row-${alpha.id}`)).toBeVisible();
    await expect(page.getByTestId(`table-row-${beta.id}`)).toHaveCount(0);

    // Reload: the per-user state is read back from the server.
    await page.reload();
    await expect(page.getByTestId('artifact-table-view')).toBeVisible();
    await expect(page.getByTestId(`table-row-${alpha.id}`)).toBeVisible();
    await expect(page.getByTestId('filter-chip-remove-title-0')).toBeVisible();
    await expect(page.getByTestId(`table-row-${beta.id}`)).toHaveCount(0);
  });

  test('removes a filter chip and the removal survives reload', async ({ page }) => {
    await openTableView(page);

    const stateWrite = nextTableStateWrite(page);
    await filterByTitle(page, 'Alpha');
    await stateWrite;
    await expect(page.getByTestId(`table-row-${alpha.id}`)).toBeVisible();
    await expect(page.getByTestId(`table-row-${beta.id}`)).toHaveCount(0);

    const removalWrite = nextTableStateWrite(page);
    await page.getByTestId('filter-chip-remove-title-0').click();
    await removalWrite;

    await expect(page.getByTestId('active-filter-chips')).toHaveCount(0);
    await expect(page.getByTestId(`table-row-${beta.id}`)).toBeVisible();

    await page.reload();
    await expect(page.getByTestId('artifact-table-view')).toBeVisible();
    await expect(page.getByTestId('active-filter-chips')).toHaveCount(0);
    await expect(page.getByTestId(`table-row-${beta.id}`)).toBeVisible();
  });

  test('hides a column and the column choice survives reload (per-user)', async ({
    page,
  }) => {
    await openTableView(page);
    await expect(page.getByTestId('sort-title')).toBeVisible();

    await page.getByTestId('column-picker-toggle').click();
    await expect(page.getByTestId('column-picker')).toBeVisible();
    await expect(page.getByTestId('column-toggle-title')).toBeChecked();

    const stateWrite = nextTableStateWrite(page);
    await page.getByTestId('column-toggle-title').uncheck();
    await stateWrite;

    await expect(page.getByTestId('sort-title')).toHaveCount(0);
    await expect(page.getByTestId('sort-status')).toBeVisible();

    await page.reload();
    await expect(page.getByTestId('artifact-table-view')).toBeVisible();
    await expect(page.getByTestId('sort-title')).toHaveCount(0);
    await expect(page.getByTestId('sort-status')).toBeVisible();
    await page.getByTestId('column-picker-toggle').click();
    await expect(page.getByTestId('column-toggle-title')).not.toBeChecked();
  });

  test('bulk edit of two rows sends exactly one bulk-update request', async ({
    page,
  }) => {
    await openTableView(page);

    const bulkRequests = track(
      page,
      (request) =>
        request.method() === 'PATCH' && request.url().includes(BULK_UPDATE_URL)
    );

    await page.getByTestId(`row-select-${alpha.id}`).check();
    await page.getByTestId(`row-select-${beta.id}`).check();
    await expect(page.getByTestId('bulk-selection-count')).toContainText('2');

    await page.getByTestId('bulk-edit-fields').click();
    await expect(page.getByTestId('bulk-edit-dialog')).toBeVisible();
    await page.getByTestId('bulk-field-title').fill('Bulk renamed');
    await page.getByTestId('bulk-change-reason').fill('E2E bulk guardrail');

    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes(BULK_UPDATE_URL) &&
        response.request().method() === 'PATCH'
    );
    await page.getByTestId('bulk-submit').click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);

    await expect(page.getByTestId('bulk-action-bar')).toHaveCount(0);
    expect(bulkRequests).toHaveLength(1);

    // One request, both entries, each with its own version precondition.
    // Body is the merged backend contract: `{workspace_id, entries}`.
    const payload = bulkRequests[0].postDataJSON() as {
      workspace_id: string;
      entries: Array<{
        artifact_id: string;
        expected_version: number;
        fields: Record<string, unknown>;
      }>;
    };
    expect(payload.workspace_id).toBeTruthy();
    expect(payload).not.toHaveProperty('mode');
    expect(payload).not.toHaveProperty('items');
    expect(payload.entries).toHaveLength(2);
    for (const entry of payload.entries) {
      expect(entry.fields).toMatchObject({ title: 'Bulk renamed' });
      expect(entry.fields.change_reason).toBe('E2E bulk guardrail');
      expect(typeof entry.expected_version).toBe('number');
    }

    await expect(page.getByTestId(`cell-${alpha.id}-title`)).toHaveText(
      'Bulk renamed'
    );
    await expect(page.getByTestId(`cell-${beta.id}-title`)).toHaveText(
      'Bulk renamed'
    );
  });

  test('bulk transition of two rows sends exactly one POST and moves both rows', async ({
    page,
    request,
  }) => {
    await openTableView(page);

    // Derive the target from the workspace's own graph instead of hardcoding a
    // state. Both rows must share the current state and the edge, or a single
    // bulk target cannot exist in the first place.
    const [alphaTransitions, betaTransitions] = await Promise.all([
      readTransitions(request, alpha.id),
      readTransitions(request, beta.id),
    ]);
    expect(
      alphaTransitions.current_state,
      'both fixtures must start in the same state for one bulk target'
    ).toBe(betaTransitions.current_state);
    const betaTargets = new Set(
      betaTransitions.allowed_transitions.map((entry) => entry.target_state)
    );
    const commonTargets = alphaTransitions.allowed_transitions
      .map((entry) => entry.target_state)
      .filter((state) => betaTargets.has(state));
    const targets = commonTargets.filter(
      (state) => state !== alphaTransitions.current_state
    );
    expect(
      targets.length,
      `no common transition out of '${alphaTransitions.current_state}' for both rows`
    ).toBeGreaterThan(0);
    const targetState = targets[0];

    const transitionRequests = track(
      page,
      (req) =>
        req.method() === 'POST' && req.url().includes(BULK_TRANSITION_URL)
    );

    await page.getByTestId(`row-select-${alpha.id}`).check();
    await page.getByTestId(`row-select-${beta.id}`).check();
    await page.getByTestId('bulk-change-status').click();

    const target = page.getByTestId('bulk-target-state');
    await expect(target).toBeEnabled();
    const offered = await target
      .locator('option')
      .evaluateAll((options) =>
        options
          .map((option) => (option as HTMLOptionElement).value)
          .filter((value) => value !== '')
      );
    // The dialog must offer exactly the graph's common moves — no more (an
    // option the engine refuses is what produced "200 with failed[]") and no
    // less. Order is the first row's transition order.
    expect(offered).toEqual(commonTargets);

    await target.selectOption(targetState);
    await page
      .getByTestId('bulk-status-change-reason')
      .fill('E2E bulk transition guardrail');

    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes(BULK_TRANSITION_URL) &&
        response.request().method() === 'POST'
    );
    await page.getByTestId('bulk-transition-submit').click();
    const response = await responsePromise;
    expect(response.status()).toBe(200);
    expect(transitionRequests).toHaveLength(1);
    const payload = transitionRequests[0].postDataJSON() as {
      item_type: string;
      ids: string[];
      to_state: string;
    };
    expect(payload.ids).toHaveLength(2);
    expect(payload.to_state).toBe(targetState);

    const result = (await response.json()) as {
      transitioned: Array<{ artifact_id: string; state: string }>;
      failed: Array<{
        index: number;
        artifact_id: string;
        code: string;
        message: string;
      }>;
    };
    // A 200 alone proves nothing: the endpoint is partial-success by contract
    // and answers 200 with every row in `failed`. Without this assertion the
    // test stayed green while both rows kept their old state (exactly the
    // regression this guard exists for).
    expect(
      result.failed,
      `bulk transition refused rows: ${JSON.stringify(result.failed)}`
    ).toEqual([]);
    expect(result.transitioned.map((entry) => entry.artifact_id).sort()).toEqual(
      [...payload.ids].sort()
    );
    for (const entry of result.transitioned) {
      expect(entry.state).toBe(targetState);
    }

    await expect(page.getByTestId('bulk-action-bar')).toHaveCount(0);

    // Both rows really moved — asserted through the workflow state endpoint
    // (the single source of truth) and through the entity's mirrored status.
    for (const id of [alpha.id, beta.id]) {
      const after = await readTransitions(request, id);
      expect(after.current_state).toBe(targetState);
      const reread = await request.get(`${BACKEND_URL}/api/v1/requirements/${id}/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      expect(reread.ok()).toBeTruthy();
      expect((await reread.json()).status).toBe(targetState);
    }
  });

  test('inline edit saves through the single-item path, not through bulk-update', async ({
    page,
    request,
  }) => {
    await openTableView(page);

    const singleUpdates = track(
      page,
      (req) =>
        req.method() === 'PATCH' &&
        new RegExp(`/api/v1/requirements/${alpha.id}/$`).test(req.url())
    );
    const bulkUpdates = track(
      page,
      (req) => req.url().includes(BULK_UPDATE_URL)
    );

    await page.getByTestId(`cell-${alpha.id}-title`).click();
    const editor = page.getByTestId('inline-editor-title');
    await expect(editor).toBeVisible();
    await expect(page.getByTestId('inline-input-title')).toHaveValue(TITLE_ALPHA);

    await page.getByTestId('inline-input-title').fill('Inline saved');
    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === 'PATCH' &&
        new RegExp(`/api/v1/requirements/${alpha.id}/$`).test(response.url())
    );
    await page.getByTestId('inline-input-title').press('Enter');
    const response = await responsePromise;
    expect(response.status()).toBe(200);

    await expect(editor).toHaveCount(0);
    expect(singleUpdates).toHaveLength(1);
    expect(bulkUpdates).toHaveLength(0);
    // The row version travels as the If-Match precondition (GH-868/GH-923).
    expect(singleUpdates[0].headers()['if-match']).toBeTruthy();

    await expect(page.getByTestId(`cell-${alpha.id}-title`)).toHaveText(
      'Inline saved'
    );
    expect((await readRequirement(request, alpha.id)).title).toBe('Inline saved');
  });

  test('a 412 conflict marks only the edited field and offers the reload control', async ({
    page,
    request,
  }) => {
    await openTableView(page);

    // Advance the server-side version behind the page's back: the table row
    // still carries the version it read, so the next inline save is stale.
    const current = await readRequirement(request, alpha.id);
    const concurrent = await request.patch(
      `${BACKEND_URL}/api/v1/requirements/${alpha.id}/`,
      {
        headers: {
          Authorization: `Bearer ${token}`,
          'If-Match': `"${current.version}"`,
        },
        data: { title: 'Written by another session' },
      }
    );
    expect(concurrent.status()).toBe(200);

    await page.getByTestId(`cell-${alpha.id}-title`).click();
    const editor = page.getByTestId('inline-editor-title');
    await expect(editor).toBeVisible();
    await page.getByTestId('inline-input-title').fill('Stale write');

    const responsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === 'PATCH' &&
        new RegExp(`/api/v1/requirements/${alpha.id}/$`).test(response.url())
    );
    await page.getByTestId('inline-input-title').press('Enter');
    const response = await responsePromise;
    expect(response.status()).toBe(412);

    // Exactly the edited cell is in edit state and carries the conflict + the
    // reload control; no other field opens an editor.
    await expect(page.locator('[data-testid^="inline-editor-"]')).toHaveCount(1);
    await expect(editor.getByTestId('inline-error')).toBeVisible();
    await expect(editor.getByTestId('inline-reload')).toBeVisible();

    await editor.getByTestId('inline-reload').click();
    await expect(page.locator('[data-testid^="inline-editor-"]')).toHaveCount(0);
  });

  test('saves the current state as a view and re-applies it later', async ({
    page,
  }) => {
    await openTableView(page);

    const stateWrite = nextTableStateWrite(page);
    await filterByTitle(page, 'Alpha');
    await stateWrite;
    await expect(page.getByTestId('filter-chip-remove-title-0')).toBeVisible();

    const viewName = `E2E alpha view ${Date.now()}`;
    await page.getByTestId('saved-view-save').click();
    await expect(page.getByTestId('saved-view-dialog')).toBeVisible();
    await page.getByTestId('saved-view-name').fill(viewName);

    // Pin the create contract instead of only waiting for the dialog to close:
    // a 400 (unknown item_type/field, bad visibility, duplicate name) left the
    // dialog open and the test failed with a generic timeout that hid the
    // server's message.
    const createRequest = page.waitForRequest(
      (req) =>
        req.method() === 'POST' &&
        new URL(req.url()).pathname === SAVED_VIEWS_PATH
    );
    const createResponse = page.waitForResponse(
      (resp) =>
        resp.request().method() === 'POST' &&
        new URL(resp.url()).pathname === SAVED_VIEWS_PATH
    );
    await page.getByTestId('saved-view-submit').click();
    const createBody = (await createRequest).postDataJSON() as {
      workspace_id: string;
      item_type: string;
      name: string;
      visibility: string;
      columns: unknown[];
      filters: Record<string, unknown>;
      sort: unknown[];
    };
    const create = await createResponse;
    if (create.status() !== 201) {
      throw new Error(
        `POST ${SAVED_VIEWS_PATH} answered ${create.status()}: ${await create.text()}`
      );
    }
    const created = (await create.json()) as {
      id: string;
      name: string;
      item_type: string;
      filters: Record<string, unknown>;
    };
    // The body the UI is required to send (SavedViewWriteSerializer).
    expect(createBody).toMatchObject({
      workspace_id: workspaceId,
      item_type: 'Requirement',
      name: viewName,
      visibility: 'private',
    });
    expect(createBody.filters).toEqual({
      title: { op: 'contains', value: 'Alpha' },
    });
    expect(Array.isArray(createBody.columns)).toBe(true);
    expect(Array.isArray(createBody.sort)).toBe(true);
    expect(created).toMatchObject({
      name: viewName,
      item_type: 'Requirement',
      filters: { title: { op: 'contains', value: 'Alpha' } },
    });
    await expect(page.getByTestId('saved-view-dialog')).toHaveCount(0);

    // Drop the filter (and the selection) so applying the view has to restore
    // the saved state instead of reading whatever is already on screen.
    const removalWrite = nextTableStateWrite(page);
    await page.getByTestId('filter-chip-remove-title-0').click();
    await removalWrite;
    await expect(page.getByTestId('active-filter-chips')).toHaveCount(0);
    await page.getByTestId('saved-view-select').selectOption('');

    const applyResponse = page.waitForResponse(
      (response) =>
        response.request().method() === 'GET' &&
        response.url().includes(SAVED_VIEWS_URL) &&
        response.url().includes('/apply/')
    );
    await page.getByTestId('saved-view-select').selectOption({ label: viewName });
    const applied = await applyResponse;
    expect(applied.status()).toBe(200);
    const appliedBody = (await applied.json()) as {
      count: number;
      results: Array<{ id: string; values?: { title?: string } }>;
      warnings?: string[];
    };
    // `apply` is 200 even for a stale view: only the body proves the stored
    // filter still compiles and actually narrows the rows here.
    expect(appliedBody.warnings ?? []).toEqual([]);
    expect(appliedBody.results.map((row) => row.id)).toEqual([alpha.id]);

    await expect(page.getByTestId('filter-chip-remove-title-0')).toBeVisible();
    await expect(page.getByTestId(`table-row-${alpha.id}`)).toBeVisible();
    await expect(page.getByTestId(`table-row-${beta.id}`)).toHaveCount(0);
    await expect(page.getByTestId('saved-view-error')).toHaveCount(0);
  });
});
