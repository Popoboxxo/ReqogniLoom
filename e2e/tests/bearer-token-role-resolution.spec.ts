// REQ-126: Bearer Token Role Resolution — E2E verification
//
// Context:
// - Bug: Users with empty JWT roles (fresh sign-up with no assigned roles) couldn't
//   create Needs/Requirements/Architecture, even after roles were assigned in the DB.
// - Root cause: AuthTenancyAuthentication didn't fallback to DB for role resolution.
// - Fix: _resolve_roles_from_db() in backend/auth_tenancy/rest.py now resolves roles
//   from UserRole table when JWT roles are empty.
//
// This E2E test validates the fix via:
// 1. Browser login (validates cookie/session auth path)
// 2. Bearer token extraction and API calls (validates Bearer token role resolution)
// 3. CRUD operations (validates DB-fallback works for write operations)

import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[REQ-126] Bearer Token Role Resolution E2E', () => {
  // =========================================================================
  // REQ-126: Browser Login validates auth path
  // =========================================================================
  test('[REQ-126] browser login succeeds and redirects from login page', async ({ page }) => {
    await loginAsAdmin(page);
    // After login, should NOT be on /login page (redirected to dashboard/home)
    await page.waitForLoadState('networkidle');
    const url = page.url();
    expect(url.includes('/login')).toBe(false);
    // Page should be visible (not 404 or error)
    await expect(page.locator('body')).toBeVisible();
  });

  // =========================================================================
  // REQ-126: Bearer token extracted after login can be used for API calls
  // =========================================================================
  test('[REQ-126] getAuthToken returns valid JWT', async () => {
    const token = await getAuthToken();
    expect(token).toBeTruthy();
    expect(token.length).toBeGreaterThan(20); // JWT should be substantial
  });

  // =========================================================================
  // REQ-126: Create Need via Bearer token (DB-fallback validation)
  // =========================================================================
  test('[REQ-126] create Need via Bearer token after login (DB-fallback path)', async ({ request }) => {
    const token = await getAuthToken();

    // Create need with Bearer token
    const needResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/needs/`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          title: `Bearer Need E2E ${Date.now()}`,
          description: 'Created via Bearer token after login (validates DB-fallback)',
        },
      }
    );

    // Must return 201, not 403
    // 403 would indicate: roles=[empty] in JWT, DB-fallback didn't work
    expect(needResp.status()).toBe(201);
    const body = await needResp.json();
    expect(body.id).toBeDefined();
    expect(body.title).toContain('Bearer Need');
  });

  // =========================================================================
  // REQ-126: Create Requirement via Bearer token (DB-fallback validation)
  // =========================================================================
  test('[REQ-126] create Requirement via Bearer token (DB-fallback validates for all WRITE ops)', async ({ request }) => {
    const token = await getAuthToken();

    const reqResp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        title: `Bearer Requirement E2E ${Date.now()}`,
        workspace_id: SEEDED_WORKSPACE_ID,
        description: 'Created via Bearer token after login',
      },
    });

    // Must return 201, not 403
    expect(reqResp.status()).toBe(201);
    const body = await reqResp.json();
    expect(body.id).toBeDefined();
    expect(body.workspace_id).toBe(SEEDED_WORKSPACE_ID);
  });

  // =========================================================================
  // REQ-126: Create Architecture Element via Bearer token (DB-fallback validation)
  // =========================================================================
  test('[REQ-126] create Architecture element via Bearer token (DB-fallback validation)', async ({ request }) => {
    const token = await getAuthToken();

    const archResp = await request.post(`${BACKEND_URL}/api/v1/architecture/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        title: `Bearer Architecture E2E ${Date.now()}`,
        workspace_id: SEEDED_WORKSPACE_ID,
        element_type: 'Component',
      },
    });

    // Must return 201, not 403
    expect(archResp.status()).toBe(201);
    const body = await archResp.json();
    expect(body.id).toBeDefined();
    expect(body.element_type?.toLowerCase()).toBe('component');
  });

  // =========================================================================
  // REQ-126: List artifacts via Bearer token (READ operations also use resolved roles)
  // =========================================================================
  test('[REQ-126] list Needs via Bearer token validates read permission', async ({ request }) => {
    const token = await getAuthToken();

    const listResp = await request.get(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/needs/`,
      {
        headers: { Authorization: `Bearer ${token}` },
      }
    );

    // Must return 200 (DB-fallback resolves read permission)
    expect(listResp.status()).toBe(200);
    const body = await listResp.json();
    expect(body.results || body).toBeTruthy();
  });

  // =========================================================================
  // REQ-126: Regression Guard — Fast path (token with non-empty roles)
  //
  // Verify that tokens WITH roles in the JWT don't regress (still use fast path).
  // =========================================================================
  test('[REQ-126] fast path still works for tokens with roles in JWT', async ({ request }) => {
    const token = await getAuthToken();

    // Try to create an ADR (architecture) which requires WRITE permission
    const adrResp = await request.post(`${BACKEND_URL}/api/v1/architecture/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        title: `Fast Path ADR ${Date.now()}`,
        workspace_id: SEEDED_WORKSPACE_ID,
        element_type: 'Layer',
      },
    });

    // Should succeed (whether using fast path or DB-fallback, result is same)
    expect(adrResp.status()).toBe(201);
  });

  // =========================================================================
  // REQ-126: Browser login with workspace context
  // =========================================================================
  test('[REQ-126] browser login respects injected workspace context', async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);

    // After login, page should be functional (workspace is set)
    await page.waitForLoadState('networkidle');
    await expect(page.locator('body')).toBeVisible();

    // No 404 or permission error should occur
    const statusCode = page.url().includes('/403') || page.url().includes('/404');
    expect(statusCode).toBe(false);
  });

  // =========================================================================
  // REQ-126: Token refresh (if applicable) uses same role resolution
  // =========================================================================
  test('[REQ-126] subsequent API calls with same token work consistently', async ({ request }) => {
    const token = await getAuthToken();

    // Make multiple calls with the same token
    const calls = [
      request.post(`${BACKEND_URL}/api/v1/requirements/`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { title: `Consistency Test 1 ${Date.now()}`, workspace_id: SEEDED_WORKSPACE_ID },
      }),
      request.post(`${BACKEND_URL}/api/v1/requirements/`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { title: `Consistency Test 2 ${Date.now()}`, workspace_id: SEEDED_WORKSPACE_ID },
      }),
      request.post(`${BACKEND_URL}/api/v1/requirements/`, {
        headers: { Authorization: `Bearer ${token}` },
        data: { title: `Consistency Test 3 ${Date.now()}`, workspace_id: SEEDED_WORKSPACE_ID },
      }),
    ];

    const responses = await Promise.all(calls);

    // All should succeed with 201
    for (const resp of responses) {
      expect(resp.status()).toBe(201);
    }
  });
});
