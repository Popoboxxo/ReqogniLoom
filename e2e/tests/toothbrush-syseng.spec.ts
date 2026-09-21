import { test, expect, request, type APIRequestContext } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/** Must match WORKSPACE_NAME in the seed_toothbrush management command. */
const WORKSPACE_NAME = 'Zahnbürste SysEng Demo';

/**
 * Create a throwaway requirement in the big seeded workspace (issue #947).
 *
 * The mass-edit test used to edit a *seeded* MISRA requirement and assert the
 * transition target. That made it depend on the artifact's accumulated state:
 * after one run it sits in `in_review`, whose first offered transition is the
 * preset-gated `approved` (needs acceptance_criteria + description), so a
 * re-run failed deterministically. A dedicated artifact always starts in
 * `draft` (ungated draft -> in_review), so the test is state-independent.
 */
async function createMassEditRequirement(
  api: APIRequestContext,
  token: string,
  workspaceId: string,
  title: string
): Promise<{ id: string }> {
  const response = await api.post(`${BACKEND_URL}/api/v1/requirements/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      workspace_id: workspaceId,
      title,
      description: 'Created by toothbrush-syseng.spec.ts (mass-edit fixture)',
      acceptance_criteria: 'Given an editor, when a transition is applied, then the status updates.',
    },
  });
  expect(response.ok()).toBeTruthy();
  return (await response.json()) as { id: string };
}

/**
 * Soft-delete the fixture (204); keeps re-runs from growing the workspace.
 *
 * `change_reason` is required: the seeded "Zahnbürste SysEng Demo" workspace
 * runs the `extended` preset, and `RequirementService.delete_requirement`
 * enforces the workspace's change_reason policy (#604) — a body-less DELETE is
 * answered with 400 VALIDATION_ERROR. The call used to ignore the response, so
 * every run silently left its fixture behind (found while verifying #947).
 * Non-2xx responses are now surfaced instead of swallowed.
 */
async function deleteRequirement(
  api: APIRequestContext,
  token: string,
  id: string
): Promise<void> {
  const response = await api.delete(`${BACKEND_URL}/api/v1/requirements/${id}/`, {
    headers: { Authorization: `Bearer ${token}` },
    data: { change_reason: 'E2E mass-edit fixture cleanup (toothbrush-syseng.spec.ts)' },
  });
  if (!response.ok() && response.status() !== 404) {
    throw new Error(
      `deleteRequirement(${id}) failed: ${response.status()} ${await response.text()}`
    );
  }
}

let workspaceId: string = '';

test.describe('Zahnbürste SysEng Demo', () => {
  test.beforeAll(async () => {
    // The workspace is seeded by `manage.py seed_toothbrush`, run alongside
    // seed_demo in the E2E workflow. This spec used to shell out to
    // `docker compose exec -T backend python seed_toothbrush.py`, which can
    // only work against a local compose stack — CI runs the backend as a bare
    // `manage.py runserver` process, so that call failed on every run. Look
    // the workspace up over the API instead, which works in both setups.
    const token = await getAuthToken();
    const ctx = await request.newContext({ baseURL: BACKEND_URL });

    // The endpoint is paginated and other specs create workspaces of their
    // own, so walk `next` rather than assuming a single page.
    let url: string | null = '/api/v1/workspaces/';
    let ws: { id?: string; name?: string } | undefined;
    while (url && !ws) {
      const resp = await ctx.get(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!resp.ok()) {
        await ctx.dispose();
        throw new Error(`Listing workspaces failed: ${resp.status()} ${await resp.text()}`);
      }
      const body = await resp.json();
      const items = Array.isArray(body) ? body : body.results ?? [];
      ws = items.find((w: { name?: string }) => w.name === WORKSPACE_NAME);
      url = Array.isArray(body) ? null : (body.next ?? null);
    }
    await ctx.dispose();

    if (!ws) {
      // GH-691: a fresh `docker compose up` stack never ran the undocumented
      // manual seeding step below, so this spec isn't self-sufficient on
      // such an environment. There is no existing setup-API/management-command
      // runner this spec (or any other spec in this suite) can call from
      // Playwright to seed it itself — see the beforeAll comment above for
      // why shelling out to `docker compose exec` was already tried and
      // reverted (breaks in CI, which runs a bare `manage.py runserver`).
      // Skip with a clear, actionable reason instead of a hard, confusing
      // failure — matching the existing `test.skip(true, ...)` convention
      // used elsewhere in this suite (e.g. se-workflow.spec.ts,
      // stakeholder-needs.spec.ts) for "required seed data missing".
      test.skip(
        true,
        `Workspace "${WORKSPACE_NAME}" not found — run \`python manage.py seed_toothbrush\` ` +
        `(compose: \`docker compose exec -T backend python manage.py seed_toothbrush\`) before ` +
        `this spec, e.g. as documented in README.md's E2E prerequisites.`
      );
      return;
    }
    workspaceId = ws.id as string;
    console.log(`Seeded Workspace ID: ${workspaceId}`);
  });

  test.beforeEach(async ({ page }) => {
    // WorkspaceContext reads the active workspace from sessionStorage; a
    // `/workspaces/<id>` navigation alone does not switch it, so every view
    // below kept rendering the default workspace's artifacts.
    await setWorkspaceId(page, workspaceId);
    await loginAsAdmin(page);
  });

  // The seeded workspace is deliberately large (880 requirements, 55 issues,
  // …) to exercise the SysEng views at realistic scale, and the Vite dev
  // server renders those lists well past the 10s these assertions used to
  // allow — the data is there, the first paint just is not.
  //
  // Navigation goes through the route, not a `text=` click: the dashboard
  // renders a "Requirements" count label per workspace card, so the old
  // text clicks resolved there and every assertion ran against the workspace
  // list instead of the module view.
  test('should render the Requirement hierarchy', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    // Narrow the list before asserting: this workspace holds ~880 requirements
    // and painting all of them takes long enough that an unfiltered lookup is
    // a timing race rather than a real check of the seeded hierarchy.
    await page.getByTestId('req-list-search-input').fill('MISRA');
    await expect(page.locator('text=Der C-Code für das OTA-Modul muss MISRA-C kompatibel sein.').first()).toBeVisible({ timeout: 30000 });
    // In Card view, the hierarchy is flattened or shown differently, just check existence of L2 element
    // await expect(page.locator('text=Die MCU muss den PWM-Kanal 1 für die Motorsteuerung verwenden.').first()).toBeVisible();
  });

  test('should render the Architecture tree', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/architecture`);
    await expect(page.locator('text=Smart Toothbrush System').first()).toBeVisible({ timeout: 30000 });
    await expect(page.locator('text=Handstück').first()).toBeVisible();
    await expect(page.locator('text=Bürstenkopf').first()).toBeVisible();
  });

  test('should render ICDs', async ({ page }) => {
    // The link was renamed to "ICDs"
    await page.goto(`${FRONTEND_URL}/icds`);
    // Just verify the table has loaded some of our custom interfaces
    await expect(page.locator('text=SPI Data Link').first()).toBeVisible({ timeout: 30000 });
  });

  test('should render Risks, Issues, ADRs', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/risks`);
    await expect(page.locator('text=Wassereintritt am Schalter').first()).toBeVisible({ timeout: 30000 });

    await page.goto(`${FRONTEND_URL}/issues`);
    await expect(page.locator('text=Spaltmaß am Gehäuse zu groß').first()).toBeVisible({ timeout: 30000 });

    await page.goto(`${FRONTEND_URL}/adrs`);
    await expect(page.locator('text=Verwendung von BLE 5.2 statt 5.0').first()).toBeVisible({ timeout: 30000 });
  });

  test('should render TestCases and TestRuns', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/testcases`);
    await expect(page.locator('text=Test für: Der BLDC-Motor').first()).toBeVisible({ timeout: 30000 });

    await page.goto(`${FRONTEND_URL}/test-runs`);
    await expect(page.locator('text=Nightly Build Test Run').first()).toBeVisible({ timeout: 30000 });
  });

  test('should support mass-edit without crashing', async ({ page, request: api }) => {
    test.setTimeout(90000); // large seeded workspace — see note above
    // Issue #947: drive a dedicated fixture instead of a seeded artifact, so
    // the assertion does not depend on state left by a previous run.
    const token = await getAuthToken();
    const title = `E2E mass-edit ${Date.now()}`;
    const created = await createMassEditRequirement(api, token, workspaceId, title);

    try {
      await page.goto(`${FRONTEND_URL}/requirements`);
      await page.getByTestId('req-list-search-input').fill(title);
      const card = page.locator(`text=${title}`).first();
      await expect(card).toBeVisible({ timeout: 30000 });

      // Open the artifact and drive the transition via the
      // WorkflowStatusEditor's trigger + menu (REQ-161).
      await card.click();

      await page.getByTestId('workflow-transition-trigger').click();
      const firstOption = page
        .getByTestId('workflow-transition-menu')
        .locator('[data-testid^="workflow-transition-option-"]')
        .first();
      await expect(firstOption).toBeVisible({ timeout: 10000 });
      const targetState = (await firstOption.getAttribute('data-testid'))!
        .replace('workflow-transition-option-', '');
      await firstOption.click();

      // requires_change_reason is true on every extended-preset transition, so
      // the editor prompts before it sends the POST.
      const reasonPrompt = page.getByTestId('workflow-reason-prompt');
      if (await reasonPrompt.isVisible({ timeout: 5000 }).catch(() => false)) {
        await page.getByTestId('workflow-reason-input').fill(`E2E: move to ${targetState}`);
        await page.getByTestId('workflow-reason-confirm').click();
      }

      // Check if updated in the status badge
      await expect(page.getByTestId('workflow-current-status')).toContainText(targetState, { timeout: 30000 });
    } finally {
      await deleteRequirement(api, token, created.id);
    }
  });
});
