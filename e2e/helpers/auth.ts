import { Page, request } from '@playwright/test';

const BASE_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

// Review finding F-05 (docs/SYSTEMAUDIT_2026-08-18.md follow-up, BUG-17):
// `admin12345` is only the demo default in `seed_demo`
// (`_DEFAULT_ADMIN_PASSWORD`/`SYSTEM_ADMIN_PASSWORD` fallback, see
// backend/auth_tenancy/management/commands/seed_demo.py). A local
// `.env` with its own `SYSTEM_ADMIN_PASSWORD` set (as the security-hardening
// guidance in README recommends) makes every E2E login fail with a plain
// 401 that reads like an unrelated app bug (e.g. "ICD version doesn't
// increment" when the request never even got past login) — see
// docs/SYSTEMAUDIT_2026-08-18.md BUG-17 for a concrete case. Overridable via
// `E2E_ADMIN_PASSWORD` so a local run can point at the real seeded password
// without editing this file.
export const TEST_USER = {
  username: 'admin',
  password: process.env.E2E_ADMIN_PASSWORD || 'admin12345',
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
 * Create a brand-new, empty workspace via the API and return its ID.
 *
 * Used by specs that need a workspace with no pre-existing architecture root
 * (or other singleton state), so they don't collide with other specs sharing
 * SEEDED_WORKSPACE_ID.
 */
export async function createIsolatedWorkspace(token: string, name?: string): Promise<string> {
  const ctx = await request.newContext({ baseURL: BASE_URL });
  const wsName = name || `e2e-isolated-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const response = await ctx.post('/api/v1/workspaces/', {
    headers: { Authorization: `Bearer ${token}` },
    data: { name: wsName },
  });
  if (!response.ok()) {
    throw new Error(`Workspace creation failed: ${response.status()} ${await response.text()}`);
  }
  const body = await response.json();
  await ctx.dispose();
  return body.id as string;
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

/**
 * Name markers that identify API keys created by the E2E test suite.
 * Only keys whose name contains one of these substrings are eligible for
 * automatic cleanup — real/manually-created keys are never touched.
 */
const E2E_API_KEY_MARKERS = [
  'E2E',
  'REQ129',
  'REQ-129',
  'REQ134',
  'REQ-134',
  'REQ-127',
  'MCP-REQ',
  'MCP test key',
  'UI-REQ',
  'Hermes-',
];

/**
 * Revoke stale *E2E-test-created* API keys for the authenticated user.
 *
 * The backend enforces a hard cap of 10 *active* API keys per user
 * (VALIDATION_ERROR "User already has the maximum of 10 active API keys.").
 * The API-key E2E tests create fresh keys in their `beforeAll` hooks but never
 * clean them up, so across repeated runs the active-key count climbs until the
 * cap is hit. Once capped, `POST /api/v1/api-keys/` returns 400 and the created
 * key id / plaintext becomes undefined — which cascades into non-deterministic
 * failures in any test that depends on that key (REQ-129 MCP tools/list,
 * REQ-134 list/retrieve).
 *
 * Calling this in a `beforeAll` before creating new keys keeps the active-key
 * count under the cap. Cleanup is scoped by name marker: only keys created by
 * the E2E suite (see {@link E2E_API_KEY_MARKERS}) are revoked — user-owned or
 * manually-created keys are left untouched. Revoking (DELETE) marks a key
 * inactive, which frees a slot against the cap.
 */
export async function revokeAllApiKeys(token: string): Promise<void> {
  const ctx = await request.newContext({ baseURL: BASE_URL });
  try {
    const listResp = await ctx.get('/api/v1/api-keys/', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (listResp.ok()) {
      const body = await listResp.json();
      const keys: Array<{ id: string; name?: string; revoked?: boolean }> = Array.isArray(body)
        ? body
        : body.results ?? [];
      for (const key of keys) {
        if (key.revoked) {
          continue; // already inactive — does not count against the cap
        }
        const name = key.name ?? '';
        const isE2eKey = E2E_API_KEY_MARKERS.some((marker) => name.includes(marker));
        if (!isE2eKey) {
          continue; // not created by the E2E suite — never touch it
        }
        await ctx.delete(`/api/v1/api-keys/${key.id}/`, {
          headers: { Authorization: `Bearer ${token}` },
        });
      }
    }
  } finally {
    await ctx.dispose();
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
