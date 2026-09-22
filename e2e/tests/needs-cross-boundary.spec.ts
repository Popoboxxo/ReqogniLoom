import { test, expect } from '@playwright/test';
import { getAuthToken, createIsolatedWorkspace, setWorkspaceId, loginAsAdmin } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

/**
 * Row testid of one need in the needs tree (issue #947).
 *
 * `NeedList.tsx` renders `<WorkspaceTree data-testid="need-list-tree">`, and the
 * tree puts `data-testid={`${testIdPrefix}-node-${node.id}`}` on each
 * `<li role="treeitem">` — so the row for a known id is addressable without
 * matching its rendered title (which changes per run) or using a `text=` CSS
 * pseudo-selector.
 */
const needRow = (id: string): string => `need-list-tree-node-${id}`;

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
    const created = (await createResp.json()) as { id: string };

    // 2. Verify in UI
    // NOTE: the nav link text is locale-dependent ("Bedarfe" in de,
    // "Stakeholder Needs" in en — see frontend/src/i18n/locales/*.json,
    // key nav.needs). Playwright's default browser locale is en-US
    // (navigator.language), so the app renders the English label and a
    // hardcoded German-text selector times out regardless of app health.
    // The route link itself (NavLink to="/needs") is locale-independent —
    // select on the href instead. (Route-based, not text-based: the nav items
    // are data-driven in SidebarNavigation.tsx, so a per-module `data-testid`
    // would mean touching the shared navigation shell — documented as
    // deliberately unchanged in the #947 report.)
    await page.goto('/');
    await page.click('a[href="/needs"]');

    // Verify the list contains *this* need, addressed by its id (issue #947).
    const row = page.getByTestId(needRow(created.id));
    await expect(row).toBeVisible();

    // Click to verify details
    await row.click();
    await expect(page.locator('[data-testid="artifact-field-title"]')).toHaveValue(apiTitle);
    // Attribut v3 WS6 (#939) added further extended textareas to the Need form
    // (e.g. rationale), so a bare `page.locator('textarea')` is now ambiguous
    // (Playwright strict-mode violation). Scope to the description field's own
    // testid, which the shared TextArea renders.
    await expect(page.locator('[data-testid="artifact-field-description"]')).toHaveValue(
      'Created via REST API'
    );
    // Issue #947: the MoSCoW priority <select> is rendered by the shared
    // `ArtifactForm`/`EnumSelect` (NeedArtifactForm renders through it and does
    // not override the testid), so it is addressable as
    // `artifact-field-moscow_priority`. The previous
    // `select:has(option[value="Must"])` was a structural CSS guess: "whichever
    // <select> happens to own a Must option" — the page also renders
    // status/sort/diff selects, and a second Must-valued enum anywhere on the
    // page would make the selector ambiguous.
    await expect(page.getByTestId('artifact-field-moscow_priority')).toHaveValue('Must');
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
    const created = (await createResp.json()) as { id: string };

    // 2. Verify in UI (locale-independent selector — see note above)
    await page.goto('/');
    await page.click('a[href="/needs"]');

    await expect(page.getByTestId(needRow(created.id))).toBeVisible();
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
    // Issue #947: the submit button has its own testid
    // (need-create-submit-btn) — `form button[type="submit"]` was a structural
    // guess that breaks as soon as the form gains a second submit control.
    await page.click('[data-testid="need-create-submit-btn"]');

    // 2. Verify via API. The id is only known after the create, so resolve it
    // through the API and then assert the UI row by id — deterministic, no
    // title-substring matching.
    //
    // Issue #947: `expect.poll` (not a single GET) because `createResp.status()`
    // is not capturable here without adding a request interceptor, and the
    // create is a POST from the UI whose completion is only observable through
    // its effect. A one-shot read raced it before; polling the *condition* also
    // gives a far better failure message than "expected [ ] to contain".
    await expect
      .poll(
        async () => {
          const listResp = await request.get(
            `${BACKEND_URL}/api/v1/workspaces/${workspaceId}/needs/`,
            { headers: { Authorization: `Bearer ${token}` } }
          );
          if (listResp.status() !== 200) return [];
          const listJson = await listResp.json();
          return listJson.results as Array<{ id: string; title: string }>;
        },
        { timeout: 10000, message: `need "${uiTitle}" did not reach the API` }
      )
      .toContainEqual(expect.objectContaining({ title: uiTitle }));

    const listResp = await request.get(`${BACKEND_URL}/api/v1/workspaces/${workspaceId}/needs/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const listJson = await listResp.json();
    const found = (listJson.results as Array<{ id: string; title: string }>).find(
      (n) => n.title === uiTitle
    )!;

    // Wait for it to appear in list, addressed by id.
    await expect(page.getByTestId(needRow(found.id))).toBeVisible();
  });
});
