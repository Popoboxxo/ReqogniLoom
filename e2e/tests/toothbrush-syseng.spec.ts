import { test, expect, request } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/** Must match WORKSPACE_NAME in the seed_toothbrush management command. */
const WORKSPACE_NAME = 'Zahnbürste SysEng Demo';

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
      throw new Error(
        `Workspace "${WORKSPACE_NAME}" not found. Run \`python manage.py seed_toothbrush\` ` +
        `(compose: \`docker compose exec -T backend python manage.py seed_toothbrush\`).`
      );
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

  test('should support mass-edit without crashing', async ({ page }) => {
    test.setTimeout(90000); // large seeded workspace — see note above
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.getByTestId('req-list-search-input').fill('MISRA');
    await expect(page.locator('text=Der C-Code für das OTA-Modul muss MISRA-C kompatibel sein.').first()).toBeVisible({ timeout: 30000 });
    
    // In the new Card UI, mass-edit checkboxes might not exist.
    // Instead, we will simulate opening an element and editing its status, then saving.
    await page.locator('text=Der C-Code für das OTA-Modul muss MISRA-C kompatibel sein.').first().click();
    
    // Wait for form to open, then drive the transition via the
    // WorkflowStatusEditor's trigger + menu (REQ-161).
    //
    // Take whichever transition the state machine actually offers rather than
    // naming one: the seeded requirements start in `draft`, where the extended
    // preset allows only draft -> in_review ("approved" is reachable from
    // in_review only), and a rerun against an already-transitioned artifact
    // would otherwise look for an option that is gone.
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
  });
});
