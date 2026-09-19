/**
 * System-proof journey — one coherent artifact crosses MCP, REST and UI.
 *
 * Every step corroborates the previous one, so the whole run is a single
 * end-to-end proof that the three surfaces share one database:
 *
 *   Step 1  UI login + seeded workspace + admin API key (REST)
 *   Step 2  MCP writes a StakeholderNeed and a Requirement
 *   Step 3  REST reads back exactly what MCP wrote          (MCP -> REST)
 *   Step 4  REST creates a 'derives-from' trace link        (REST writes)
 *   Step 5  MCP reads that trace link back                  (REST -> MCP)
 *   Step 6  UI renders the requirement and its trace link    (MCP/REST -> UI)
 *   Step 7  MCP updates the title, UI reflects it            (MCP -> UI)
 *   Step 8  TestCase + 'verifies' link + TestRun via MCP, UI reflects them
 *   cleanup Outdate/delete everything the journey created    (idempotent)
 *
 * Evidence:
 *  - `e2e/proof/01..07*.png`       — screenshots at each UI-visible milestone
 *  - `e2e/proof/mcp-*.req.json`    — raw JSON-RPC request bodies
 *  - `e2e/proof/mcp-*.res.json`    — raw JSON-RPC response bodies
 *  - `e2e/proof/rest-*.req.json`   — raw REST request bodies
 *  - `e2e/proof/rest-*.res.json`   — raw REST response bodies
 *
 * Facts read from the repository before writing this file (not guessed):
 *  - MCP endpoint + X-API-Key + JSON-RPC envelope + `result.content[0].text`
 *    as a JSON string: `backend/mcp_server/protocol_handler.py`.
 *  - Tool argument names/return shapes: `backend/mcp_server/tools/needs.py`,
 *    `backend/mcp_server/tools/requirements.py`, `backend/mcp_server/tools/tests.py`.
 *  - REST routes: `backend/rest_api/urls.py` (`tracelinks`, `needs`,
 *    `test-runs`, `api-keys`, workspace-scoped needs).
 *  - TraceLink create payload `{source_id, target_id, link_type}` and that it
 *    resolves entity ids to artifact ids: `backend/rest_api/views.py`
 *    (`TraceLinkViewSet.create`) + `backend/application/trace_link_service.py`.
 *  - API-key create body `{name, scope}` returning `plaintext` once:
 *    `backend/rest_api/api_key_views.py`.
 *  - UI routes `/requirements/:id`, `/testcases/:id`, `/test-runs`:
 *    `frontend/src/components/NavigationShell/NavigationShell.tsx`.
 *  - Selectors `artifact-field-title`, `artifact-form`, `req-tracelink-panel`,
 *    `req-tree-title`: `frontend/src/components/shared/ArtifactForm/ArtifactForm.tsx`,
 *    `frontend/src/components/RequirementEditors/ReqTraceLinkPanel.tsx`,
 *    `frontend/src/components/RequirementEditors/RequirementTreeNode.tsx`.
 *  - `testrun-item-<id>`: `frontend/src/components/TestRuns/TestRunsList.tsx`.
 */

import { test, expect, request, type Page, type APIRequestContext } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

import {
  loginAsAdmin,
  getAuthToken,
  setWorkspaceId,
  revokeAllApiKeys,
  SEEDED_WORKSPACE_ID,
  TEST_USER,
} from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const PROOF_DIR = path.resolve(__dirname, '..', 'proof');

/** Unique suffix so repeated runs never collide on titles/names. */
const RUN = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;

const needTitle = `E2E Proof Need ${RUN}`;
const requirementTitle = `E2E Proof Requirement ${RUN}`;
const updatedRequirementTitle = `E2E Proof Requirement ${RUN} updated`;
// Step 7b: what the browser puts in, and MCP reads back.
const uiEditedRequirementTitle = `E2E Proof Requirement ${RUN} edited in UI`;
// The seeded workspace runs the `extended` preset, whose adapter requires a
// change reason on every update (ArtifactForm `requiresChangeReason`).
const changeReason = `E2E system-proof UI edit ${RUN}`;
const testCaseTitle = `E2E Proof TestCase ${RUN}`;
const testRunName = `E2E Proof Test Run ${RUN}`;
// Contains the E2E marker so `revokeAllApiKeys` may reclaim the slot on a
// aborted run (see helpers/auth.ts#E2E_API_KEY_MARKERS).
const apiKeyName = `E2E-SystemProof-${RUN}`;

let token = '';
let apiKeyId = '';
let apiKeyPlaintext = '';
let workspaceId = SEEDED_WORKSPACE_ID;
let needId = '';
let requirementId = '';
let requirementArtifactId = '';
let reqNeedLinkId = '';
let testCaseId = '';
let verifiesLinkId = '';
let testRunId = '';

fs.mkdirSync(PROOF_DIR, { recursive: true });

function authHeaders(): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

function writeProof(name: string, data: unknown): void {
  fs.writeFileSync(path.join(PROOF_DIR, name), JSON.stringify(data, null, 2), 'utf8');
}

async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: path.join(PROOF_DIR, name), fullPage: true });
}

function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(`UNCAUGHT: ${err.message}`));
  return errors;
}

/** Known non-application dev noise (same filter the existing suite uses). */
function filterKnownNoise(errors: string[]): string[] {
  return errors.filter(
    (e) =>
      !e.includes('favicon') &&
      !e.includes('hot-update') &&
      !e.includes('[HMR]') &&
      !e.includes('WebSocket')
  );
}

/**
 * Perform one JSON-RPC 2.0 `tools/call` against the MCP endpoint.
 *
 * The MCP transport wraps every successful tool payload as
 * `result.content[0].text` — a JSON *string* that must be parsed again.
 * When `proofBase` is given the raw request and response frames are written to
 * `e2e/proof/<proofBase>.req.json` / `.res.json`.
 */
async function mcpCall(
  ctx: APIRequestContext,
  tool: string,
  args: Record<string, unknown>,
  proofBase?: string
): Promise<any> {
  const reqBody = {
    jsonrpc: '2.0',
    id: 1,
    method: 'tools/call',
    params: { name: tool, arguments: args },
  };
  if (proofBase) writeProof(`${proofBase}.req.json`, reqBody);

  const res = await ctx.post(`${BACKEND_URL}/mcp/`, {
    headers: { 'X-API-Key': apiKeyPlaintext, 'Content-Type': 'application/json' },
    data: reqBody,
  });
  expect(res.status(), `[${tool}] MCP transport must answer HTTP 200`).toBe(200);

  const body = await res.json();
  if (proofBase) writeProof(`${proofBase}.res.json`, body);

  expect(body.jsonrpc, `[${tool}] JSON-RPC 2.0 envelope`).toBe('2.0');
  if (body.error) {
    throw new Error(`[${tool}] JSON-RPC error: ${JSON.stringify(body.error)}`);
  }
  expect(body.result, `[${tool}] result present`).toBeTruthy();
  if (body.result.isError) {
    throw new Error(`[${tool}] tool error: ${body.result?.content?.[0]?.text}`);
  }
  const text = body.result?.content?.[0]?.text;
  expect(typeof text, `[${tool}] result.content[0].text must be a JSON string`).toBe('string');
  return JSON.parse(text as string);
}

test.describe.serial('System proof: MCP <-> REST <-> UI artifact journey', () => {
  // Cleanup runs even when a step fails. It is intentionally defensive: any id
  // that was never assigned is skipped, and every call tolerates a failure.
  test.afterAll(async () => {
    const ctx = await request.newContext({ baseURL: BACKEND_URL });
    try {
      if (reqNeedLinkId) {
        await ctx.delete(`/api/v1/tracelinks/${reqNeedLinkId}/`, { headers: authHeaders() });
      }
      if (verifiesLinkId) {
        await ctx.delete(`/api/v1/tracelinks/${verifiesLinkId}/`, { headers: authHeaders() });
      }
      if (apiKeyPlaintext && testCaseId) {
        await mcpCall(ctx, 'test.outdate', { id: testCaseId, reason: 'E2E system-proof cleanup' }).catch(() => undefined);
      }
      if (apiKeyPlaintext && requirementId) {
        await mcpCall(ctx, 'requirement.outdate', { id: requirementId, reason: 'E2E system-proof cleanup' }).catch(() => undefined);
      }
      if (apiKeyPlaintext && needId) {
        await mcpCall(ctx, 'needs.outdate', { id: needId, reason: 'E2E system-proof cleanup' }).catch(() => undefined);
      }
      if (token && apiKeyId) {
        await ctx.delete(`/api/v1/api-keys/${apiKeyId}/`, { headers: authHeaders() });
      }
    } catch {
      // Cleanup is best-effort: never turn a report into a second failure.
    } finally {
      await ctx.dispose();
    }
  });

  // -------------------------------------------------------------------------
  // Step 1 — UI login, seeded workspace, admin API key (REST)
  // -------------------------------------------------------------------------
  test('Step 1 - UI login, seeded workspace, admin API key (REST)', async ({ page, request }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    // Captured across the whole login transition; only *uncaught* exceptions
    // are asserted here. The app fires a few authenticated requests while the
    // login response is still being wired up, which the browser logs as 401
    // resource errors — that is the auth bootstrap, not the page under test
    // (the clean-console assertion for the real pages lives in steps 6-8).
    const errors = collectConsoleErrors(page);

    await page.goto(`${FRONTEND_URL}/login`);
    await expect(page.locator('#username-input')).toBeVisible();
    await shot(page, '01-login.png');

    await page.fill('#username-input', TEST_USER.username);
    await page.fill('#password-input', TEST_USER.password);
    await page.click('button[type="submit"]');
    await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });

    token = await getAuthToken();
    expect(token.length, 'JWT for REST calls').toBeGreaterThan(0);

    // Resolve/verify the seeded demo workspace this journey writes into.
    const wsResp = await request.get(`${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`, {
      headers: authHeaders(),
    });
    expect(wsResp.status(), 'seeded demo workspace must resolve').toBe(200);
    const ws = await wsResp.json();
    expect(ws.id, 'resolved workspace id').toBe(SEEDED_WORKSPACE_ID);
    workspaceId = ws.id;

    // Free any stale E2E keys before creating a fresh one (per-user cap is 10).
    await revokeAllApiKeys(token);

    const keyResp = await request.post(`${BACKEND_URL}/api/v1/api-keys/`, {
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      data: { name: apiKeyName, scope: 'admin' },
    });
    expect(keyResp.status(), 'admin API key creation must return 201').toBe(201);
    const key = await keyResp.json();
    expect(key.scope, 'write tools need the admin scope').toBe('admin');
    expect(typeof key.plaintext, 'plaintext returned once').toBe('string');
    expect(key.plaintext.startsWith('reqlo_'), 'plaintext looks like an MCP key').toBe(true);
    apiKeyId = key.id;
    apiKeyPlaintext = key.plaintext;

    const uncaught = errors.filter((e) => e.startsWith('UNCAUGHT:'));
    expect(uncaught, `uncaught exceptions during login: ${JSON.stringify(uncaught)}`).toHaveLength(0);
  });

  // -------------------------------------------------------------------------
  // Step 2 — MCP writes
  // -------------------------------------------------------------------------
  test('Step 2 - MCP writes a StakeholderNeed and a Requirement', async ({ request }) => {
    const need = await mcpCall(
      request,
      'needs.create',
      {
        workspace_id: workspaceId,
        title: needTitle,
        description: 'Stakeholder need created through MCP for the system-proof journey',
        moscow_priority: 'Must',
      },
      'mcp-needs-create'
    );
    expect(need.need.title, 'needs.create echoes the title').toBe(needTitle);
    expect(typeof need.need.id, 'needs.create returns an id').toBe('string');
    expect(need.need.workspace_id).toBe(workspaceId);
    needId = need.need.id;

    const req = await mcpCall(
      request,
      'requirement.create',
      {
        workspace_id: workspaceId,
        title: requirementTitle,
        description: 'System requirement created through MCP for the system-proof journey',
      },
      'mcp-requirement-create'
    );
    expect(req.requirement.title, 'requirement.create echoes the title').toBe(requirementTitle);
    expect(typeof req.requirement.id, 'requirement.create returns an id').toBe('string');
    requirementId = req.requirement.id;
  });

  // -------------------------------------------------------------------------
  // Step 3 — REST reads what MCP wrote  (MCP -> REST)
  // -------------------------------------------------------------------------
  test('Step 3 - REST reads the MCP-written need and requirement', async ({ request }) => {
    const reqResp = await request.get(`${BACKEND_URL}/api/v1/requirements/${requirementId}/`, {
      headers: authHeaders(),
    });
    expect(reqResp.status(), 'GET requirement written via MCP').toBe(200);
    const req = await reqResp.json();
    expect(req.title, 'title written through MCP is visible through REST').toBe(requirementTitle);
    expect(req.workspace_id).toBe(workspaceId);
    requirementArtifactId = req.artifact_id;
    expect(requirementArtifactId, 'REST exposes the backing artifact id').toBeTruthy();

    const needResp = await request.get(`${BACKEND_URL}/api/v1/needs/${needId}/`, {
      headers: authHeaders(),
    });
    expect(needResp.status(), 'GET need written via MCP').toBe(200);
    const need = await needResp.json();
    expect(need.title, 'need title written through MCP is visible through REST').toBe(needTitle);
  });

  // -------------------------------------------------------------------------
  // Step 4 — REST creates the trace link  (REST writes)
  // -------------------------------------------------------------------------
  test('Step 4 - REST creates the derives-from trace link', async ({ request }) => {
    const body = {
      source_id: requirementId,
      target_id: needId,
      link_type: 'derives-from',
    };
    const resp = await request.post(`${BACKEND_URL}/api/v1/tracelinks/`, {
      headers: { ...authHeaders(), 'Content-Type': 'application/json' },
      data: body,
    });
    expect(resp.status(), 'REST trace-link creation must return 201').toBe(201);
    const link = await resp.json();
    writeProof('rest-tracelink-create.req.json', body);
    writeProof('rest-tracelink-create.res.json', link);

    expect(link.link_type, 'link type is the requested derives-from').toBe('derives-from');
    expect(link.source_id, 'source resolves to the requirement artifact').toBe(requirementArtifactId);
    expect(typeof link.id, 'created link has an id').toBe('string');
    reqNeedLinkId = link.id;
  });

  // -------------------------------------------------------------------------
  // Step 5 — MCP reads the trace back  (REST -> MCP)
  // -------------------------------------------------------------------------
  test('Step 5 - MCP reads the REST-created trace link back', async ({ request }) => {
    const traces = await mcpCall(request, 'needs.get_traces', { id: needId }, 'mcp-needs-get-traces');
    expect(traces.source_need, 'traces are reported for the need').toBe(needId);

    const incoming: Array<{ source: string; type: string }> = traces.incoming_traces;
    expect(Array.isArray(incoming), 'incoming_traces is a list').toBe(true);
    const match = incoming.find(
      (t) => t.type === 'derives-from' && t.source === requirementArtifactId
    );
    expect(
      match,
      `incoming traces must contain derives-from from ${requirementArtifactId}; got ${JSON.stringify(incoming)}`
    ).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // Step 6 — UI shows it  (MCP/REST -> UI)
  // -------------------------------------------------------------------------
  test('Step 6 - UI shows the MCP-created requirement and the REST-created trace link', async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);

    // Collect only for the page under test (after the login transition).
    const errors = collectConsoleErrors(page);
    await page.goto(`${FRONTEND_URL}/requirements/${requirementId}`);
    const titleInput = page.locator('[data-testid="artifact-field-title"]');
    await expect(titleInput, 'requirement detail editor renders').toBeVisible({ timeout: 15000 });
    await expect(titleInput, 'UI shows the MCP-written title').toHaveValue(requirementTitle);
    await shot(page, '02-mcp-created.png');

    const form = page.locator('[data-testid="artifact-form"]');
    await expect(form).toBeVisible();
    await form.screenshot({ path: path.join(PROOF_DIR, '03-requirement-detail.png') });

    const panel = page.locator('[data-testid="req-tracelink-panel"]');
    await expect(panel, 'trace panel renders in the requirement editor').toBeVisible({ timeout: 15000 });
    await expect(
      panel.locator('[data-testid="req-tree-title"]').filter({ hasText: needTitle }),
      'the linked stakeholder need is shown as the requirement parent'
    ).toBeVisible({ timeout: 15000 });
    await shot(page, '04-trace-panel.png');

    expect(
      filterKnownNoise(errors),
      `console errors on requirement detail: ${JSON.stringify(errors)}`
    ).toHaveLength(0);
  });

  // -------------------------------------------------------------------------
  // Step 7 — MCP mutates, UI reflects  (MCP -> UI)
  // -------------------------------------------------------------------------
  test('Step 7 - MCP updates the title, the UI reflects it', async ({ page, request }) => {
    const updated = await mcpCall(
      request,
      'requirement.update',
      {
        id: requirementId,
        data: { title: updatedRequirementTitle, change_reason: 'E2E system-proof title update' },
      },
      'mcp-requirement-update'
    );
    expect(updated.requirement.title, 'MCP update response carries the new title').toBe(updatedRequirementTitle);

    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);

    // Collect only for the page under test (after the login transition).
    const errors = collectConsoleErrors(page);
    await page.goto(`${FRONTEND_URL}/requirements/${requirementId}`);
    const titleInput = page.locator('[data-testid="artifact-field-title"]');
    await expect(titleInput, 'UI reflects the title changed through MCP').toHaveValue(
      updatedRequirementTitle,
      { timeout: 15000 }
    );
    await shot(page, '05-title-updated-via-mcp.png');

    expect(
      filterKnownNoise(errors),
      `console errors after MCP title update: ${JSON.stringify(errors)}`
    ).toHaveLength(0);
  });

  // -------------------------------------------------------------------------
  // Step 7b — the other direction: a change made in the UI, read back via MCP.
  //
  // Steps 2-8 all write through MCP or REST and then look at the UI, so the
  // "UI -> MCP" direction is the one they leave unpinned. It is the direction
  // that actually matters for the claim "the three surfaces share one state":
  // a user editing a title in the browser must be observable by an AI client
  // talking to the same workspace.
  // -------------------------------------------------------------------------
  test('Step 7b - UI edits the title, MCP reads the change back', async ({ page, request }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);

    const errors = collectConsoleErrors(page);
    await page.goto(`${FRONTEND_URL}/requirements/${requirementId}`);

    // The detail editor submits explicitly (`artifact-form-save`); the title
    // control is `artifact-field-title` (ArtifactForm.tsx fieldTestIds).
    const titleInput = page.locator('[data-testid="artifact-field-title"]');
    await expect(titleInput).toHaveValue(updatedRequirementTitle, { timeout: 15000 });
    await titleInput.fill(uiEditedRequirementTitle);

    // The change-reason field only exists when the workspace's preset adapter
    // asks for one (`requiresChangeReason` — the `extended` tier does, the
    // `minimal` tier the seeded workspace runs does not). Fill it when it is
    // there, so the step works under either preset instead of assuming one.
    const changeReasonInput = page.locator('[data-testid="artifact-form-change-reason"]');
    if (await changeReasonInput.count()) {
      await changeReasonInput.fill(changeReason);
    }

    const save = page.locator('[data-testid="artifact-form-save"]');
    await save.click();
    // Wait for the save round-trip to actually finish before screenshotting.
    // The button label is the signal: it reads "Saving…" while the request is
    // in flight and returns to its resting label once the form is clean, so
    // asserting on the value alone would photograph a half-saved form.
    await expect(save).not.toHaveText(/Saving/i, { timeout: 15000 });
    // A refused save leaves the form untouched, so prove a request actually
    // went out rather than only that the label settled.
    await expect(titleInput).toHaveValue(uiEditedRequirementTitle, { timeout: 15000 });
    await expect(page.locator('[role="alert"]')).toHaveCount(0);
    await shot(page, '08-ui-edit-saved.png');

    // Now read the same requirement back through MCP — proof that the write
    // the browser made is visible to a completely different client.
    const readBack = await mcpCall(
      request,
      'requirement.get',
      { id: requirementId },
      'mcp-requirement-get-after-ui-edit'
    );
    expect(
      readBack.requirement.title,
      'MCP reads the title the UI just saved — UI -> MCP direction'
    ).toBe(uiEditedRequirementTitle);

    expect(
      filterKnownNoise(errors),
      `console errors after UI edit: ${JSON.stringify(errors)}`
    ).toHaveLength(0);
  });

  // -------------------------------------------------------------------------
  // Step 8 — Test management surface
  // -------------------------------------------------------------------------
  test('Step 8 - TestCase, verifies-link and TestRun via MCP, UI reflects them', async ({ page, request }) => {
    const tc = await mcpCall(
      request,
      'test.create',
      { workspace_id: workspaceId, title: testCaseTitle, description: 'Created through MCP' },
      'mcp-test-create'
    );
    expect(tc.test_case.title, 'test.create echoes the title').toBe(testCaseTitle);
    expect(typeof tc.test_case.id, 'test.create returns an id').toBe('string');
    testCaseId = tc.test_case.id;

    const link = await mcpCall(
      request,
      'test.link',
      { test_id: testCaseId, req_id: requirementId },
      'mcp-test-link'
    );
    expect(link.trace_link.link_type, 'test.link always creates a verifies link').toBe('verifies');
    expect(link.trace_link.requirement_id, 'verifies link points at the requirement').toBe(requirementId);
    verifiesLinkId = link.trace_link.id;

    const run = await mcpCall(
      request,
      'test.run_create',
      { workspace_id: workspaceId, name: testRunName, test_case_ids: [testCaseId] },
      'mcp-test-run-create'
    );
    expect(run.test_run.name, 'test.run_create echoes the run name').toBe(testRunName);
    expect(typeof run.test_run.id, 'test.run_create returns an id').toBe('string');
    testRunId = run.test_run.id;

    const report = await mcpCall(
      request,
      'test.run_report_results',
      {
        run_id: testRunId,
        results: [{ test_case_id: testCaseId, status: 'passed', message: 'system-proof journey' }],
      },
      'mcp-test-run-report-results'
    );
    expect(report.recorded, 'exactly one result is recorded').toBe(1);
    expect(report.results[0].test_case_id).toBe(testCaseId);

    const complete = await mcpCall(request, 'test.run_complete', { run_id: testRunId });
    expect(complete.test_run.status, 'all results passed -> run status passed').toBe('passed');

    // UI: the TestCase detail shows the MCP-created case.
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);

    // Collect only for the pages under test (after the login transition).
    const errors = collectConsoleErrors(page);
    await page.goto(`${FRONTEND_URL}/testcases/${testCaseId}`);
    const tcTitle = page.locator('[data-testid="artifact-field-title"]');
    await expect(tcTitle, 'TestCase detail renders the MCP-created title').toHaveValue(testCaseTitle, {
      timeout: 15000,
    });
    await shot(page, '06-testcase.png');

    // UI: the TestRun is listed.
    await page.goto(`${FRONTEND_URL}/test-runs`);
    await expect(
      page.locator(`[data-testid="testrun-item-${testRunId}"]`),
      'MCP-created test run appears in the UI list'
    ).toBeVisible({ timeout: 15000 });
    await shot(page, '07-test-run.png');

    expect(
      filterKnownNoise(errors),
      `console errors on test surfaces: ${JSON.stringify(errors)}`
    ).toHaveLength(0);
  });
});
