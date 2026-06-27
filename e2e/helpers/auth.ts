import { Page, request } from '@playwright/test';

const BASE_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

export const TEST_USER = {
  username: 'admin',
  password: 'admin12345',
};

/**
 * Login via UI on the /login page.
 * Uses real selectors: #username-input, #password-input, button[type="submit"]
 */
export async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto(`${FRONTEND_URL}/login`);
  await page.fill('#username-input', TEST_USER.username);
  await page.fill('#password-input', TEST_USER.password);
  await page.click('button[type="submit"]');
  // Wait for redirect away from /login
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10000 });
}

/**
 * Get a JWT token directly via API (no browser needed).
 */
export async function getAuthToken(): Promise<string> {
  const ctx = await request.newContext({ baseURL: BASE_URL });
  const response = await ctx.post('/api/v1/auth/login/', {
    data: { username: TEST_USER.username, password: TEST_USER.password },
  });
  if (!response.ok()) {
    throw new Error(`Login failed: ${response.status()} ${await response.text()}`);
  }
  const body = await response.json();
  await ctx.dispose();
  // Token field may be 'token' or 'access' depending on backend implementation
  return body.token || body.access || body.access_token;
}

/**
 * Get the first available workspace ID for the logged-in user.
 * Falls back to the tenant's default workspace from the login response.
 */
export async function getWorkspaceId(token: string): Promise<string> {
  const ctx = await request.newContext({ baseURL: BASE_URL });
  // Try /api/v1/workspaces/ first (may not be implemented)
  try {
    const wsResp = await ctx.get('/api/v1/workspaces/', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (wsResp.ok()) {
      const body = await wsResp.json();
      const items = Array.isArray(body) ? body : body.results ?? [];
      if (items.length > 0 && items[0].id) {
        await ctx.dispose();
        return items[0].id as string;
      }
    }
  } catch {
    // endpoint not implemented — fall through
  }
  await ctx.dispose();
  // Fall back to the workspace ID seeded by seed_demo (discovered at test setup time)
  // This is the real workspace created for the demo tenant.
  return SEEDED_WORKSPACE_ID;
}

/**
 * Inject JWT token and workspace ID into sessionStorage so tests skip the
 * login UI and the WorkspaceContext picks up the real workspace.
 */
export async function setAuthToken(page: Page, token: string): Promise<void> {
  await page.addInitScript((t) => {
    sessionStorage.setItem('reqflow_token', t);
  }, token);
}

/**
 * Inject workspace ID into sessionStorage before page load so WorkspaceContext
 * uses the real workspace instead of the default zero-UUID mock.
 */
export async function setWorkspaceId(page: Page, workspaceId: string): Promise<void> {
  await page.addInitScript((wsId) => {
    sessionStorage.setItem('reqflow_workspace_id', wsId);
  }, workspaceId);
}

/**
 * Workspace preset tier name as accepted by PATCH /api/v1/workspaces/{id}/preset/.
 */
export type WorkspacePresetName = 'minimal' | 'standard' | 'extended';

/**
 * Reset the seeded workspace's active preset via API.
 *
 * The REQ-L0-002 preset switcher test mutates the seeded workspace's preset
 * (extended → minimal → extended) and its UI-driven cleanup is not always
 * reliable as a state reset for downstream tests. Tests that depend on a
 * specific preset (e.g. REQ-L0-012 smoke test, which requires the extended
 * preset so /api/v1/baselines/ returns 200) call this helper in their
 * beforeEach to guarantee a known starting preset regardless of file order
 * or test isolation state.
 */
export async function setWorkspacePreset(preset: WorkspacePresetName): Promise<void> {
  const token = await getAuthToken();
  const ctx = await request.newContext({ baseURL: BASE_URL });
  const response = await ctx.patch(
    `/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/preset/`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { preset },
    }
  );
  await ctx.dispose();
  if (!response.ok()) {
    throw new Error(
      `Failed to set workspace preset to '${preset}': ${response.status()} ${await response.text()}`
    );
  }
}

// ---------------------------------------------------------------------------
// Seeded workspace ID — matches what seed_demo creates for the demo tenant.
// Resolved once at module load via a synchronous env var or hardcoded fallback.
// The real value is discovered by running:
//   docker-compose exec backend python manage.py shell -c "..."
// and captured here as a constant so API tests can use it without async setup.
// ---------------------------------------------------------------------------
export const SEEDED_WORKSPACE_ID = '6d20f0b9-d2cf-46a0-b916-79f8b417210f';
