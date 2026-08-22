import { test, expect } from '@playwright/test';
import { getAuthToken, createIsolatedWorkspace, setWorkspaceId, loginAsAdmin } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

test.describe('Stakeholder Needs Cross-Boundary E2E (API/MCP/UI)', () => {
  let workspaceId: string;
  let token: string;

  test.beforeAll(async () => {
    // 1. Setup workspace and auth.
    // NOTE: helpers/auth.ts exposes getAuthToken()/createIsolatedWorkspace(),
    // not adminLogin()/setupWorkspace() (those never existed in this
    // helper module — the previous version of this spec referenced
    // undefined imports, which failed the whole file at compile time
    // before any test body ran).
    // A fixed workspace name collides across repeated local runs
    // ("A workspace named '...' already exists in this tenant" — 400),
    // so include a timestamp suffix like the other isolated-workspace specs do.
    token = await getAuthToken();
    workspaceId = await createIsolatedWorkspace(token, `Needs-Cross-Boundary-Test-WS-${Date.now()}`);
  });

  test.beforeEach(async ({ page }) => {
    // Inject workspace + token via sessionStorage so the UI opens directly
    // in the target workspace instead of relying on fragile text-based
    // workspace-switcher navigation.
    await setWorkspaceId(page, workspaceId);
    await loginAsAdmin(page);
  });

  test('Write via API -> Read in UI', async ({ page, request }) => {
    // 1. Create Need via API
    const apiTitle = `API Need ${Date.now()}`;
    const createResp = await request.post(`${BACKEND_URL}/api/v1/workspaces/${workspaceId}/needs/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        title: apiTitle,
        description: 'Created via REST API',
        moscow_priority: 'Must'
      }
    });
    expect(createResp.status()).toBe(201);

    // 2. Verify in UI
    // NOTE: the nav link text is locale-dependent ("Bedarfe" in de,
    // "Stakeholder Needs" in en — see frontend/src/i18n/locales/*.json,
    // key nav.needs). Playwright's default browser locale is en-US
    // (navigator.language), so the app renders the English label and a
    // hardcoded German-text selector times out regardless of app health.
    // The route link itself (NavLink to="/needs") is locale-independent —
    // select on the href instead.
    await page.goto('/');
    await page.click('a[href="/needs"]');

    // Verify list contains the item
    await expect(page.locator(`text=${apiTitle}`)).toBeVisible();

    // Click to verify details
    await page.click(`text=${apiTitle}`);
    await expect(page.locator('input[type="text"]').first()).toHaveValue(apiTitle);
    await expect(page.locator('textarea')).toHaveValue('Created via REST API');
    // NOTE: NeedForm's MoSCoW-priority <select> has no data-testid/label
    // association (frontend/src/components/NeedsEditors/NeedForm.tsx), and
    // the page renders several other <select> elements (status filter, sort,
    // diff version pickers), so a bare `page.locator('select')` is ambiguous
    // (Playwright strict-mode violation). Scope to the select that has the
    // 'Must' MoSCoW option, which is unique to the priority field.
    await expect(page.locator('select:has(option[value="Must"])')).toHaveValue('Must');
  });

  test('Write via MCP -> Read in UI', async ({ page, request }) => {
    // 1. Create Need via MCP
    const mcpTitle = `MCP Need ${Date.now()}`;
    // Simulate MCP request
    const createResp = await request.post(`${BACKEND_URL}/api/v1/workspaces/${workspaceId}/needs/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        title: mcpTitle,
        description: 'Created via simulated MCP Tool Call',
        moscow_priority: 'Could'
      }
    });
    expect(createResp.status()).toBe(201);

    // 2. Verify in UI (locale-independent selector — see note above)
    await page.goto('/');
    await page.click('a[href="/needs"]');

    await expect(page.locator(`text=${mcpTitle}`)).toBeVisible();
  });

  test('Write via UI -> Read via API', async ({ page, request }) => {
    await page.goto('/');
    await page.click('a[href="/needs"]');

    const uiTitle = `UI Need ${Date.now()}`;

    // NOTE: the "New" flow used to be a native window.prompt() (hence the
    // old dialog-handler + text=New selector below) but NeedsEditors/NeedList
    // now render an inline create form (data-testid="create-need-btn" ->
    // text input -> submit button; see frontend/src/components/NeedsEditors/
    // NeedList.tsx). No browser dialog is involved anymore.
    await page.click('[data-testid="create-need-btn"]');
    const titleInput = page.locator('[data-testid="need-new-title-input"]');
    await expect(titleInput).toBeVisible({ timeout: 5000 });
    await titleInput.fill(uiTitle);
    await page.click('form button[type="submit"]');

    // Wait for it to appear in list
    await expect(page.locator(`text=${uiTitle}`)).toBeVisible();

    // 2. Verify via API
    const listResp = await request.get(`${BACKEND_URL}/api/v1/workspaces/${workspaceId}/needs/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(listResp.status()).toBe(200);
    const listJson = await listResp.json();
    const found = listJson.results.find((n: any) => n.title === uiTitle);
    expect(found).toBeDefined();
    expect(found.title).toBe(uiTitle);
  });
});
