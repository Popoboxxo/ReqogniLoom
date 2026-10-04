// W1 / SEC-02, SEC-03: workspace fence on REST (ADR-011, ADR-013).
//
// W1 merged the authz workspace-fence fix. The backend suite pins it in
// `rest_api/tests/test_sec02_sec03_workspace_fence.py`; this is the
// end-to-end guard against the *live* stack, where the fence plus RBAC plus
// tenant scoping actually run together.
//
// The scenario is deliberately the API-key fence (SEC-03): a key explicitly
// scoped to the seeded workspace must be denied (403 PERMISSION_DENIED) on an
// object that lives in a *different* workspace of the same tenant. The foreign
// object's existence is proven first with the seeded admin JWT (200), so the
// 403 cannot be a masked 404.
import { test, expect } from '@playwright/test';
import { getAuthToken, createIsolatedWorkspace, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

test.describe('[SEC-02/03] Workspace fence', () => {
  test('[SEC-03] fence-scoped API key is denied (403) on a foreign workspace object', async ({ request }) => {
    const token = await getAuthToken();
    const authHeaders = { Authorization: `Bearer ${token}` };

    // Own-workspace object (inside the fence).
    const ownCreate = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: authHeaders,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: 'E2E W1 fence own',
        category: 'Functional',
      },
    });
    expect(ownCreate.status()).toBe(201);
    const ownReq = await ownCreate.json();

    // Foreign-workspace object: same tenant, a workspace the key is not
    // fenced to.
    const foreignWorkspaceId = await createIsolatedWorkspace(token, 'e2e-w1-fence-foreign');
    const foreignCreate = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: authHeaders,
      data: {
        workspace_id: foreignWorkspaceId,
        title: 'E2E W1 fence foreign',
        category: 'Functional',
      },
    });
    expect(foreignCreate.status()).toBe(201);
    const foreignReq = await foreignCreate.json();

    // Existence proof: the admin JWT reads the foreign object with 200. A 403
    // for the fenced key below is therefore a real fence denial, not the
    // "object missing -> 404" path (ADR-013 object-route rule).
    const adminRead = await request.get(
      `${BACKEND_URL}/api/v1/requirements/${foreignReq.id}/`,
      { headers: authHeaders }
    );
    expect(adminRead.status()).toBe(200);

    // Agent key fenced to the seeded workspace only (SEC-03).
    const keyResp = await request.post(`${BACKEND_URL}/api/v1/api-keys/`, {
      headers: authHeaders,
      data: {
        name: 'E2E W1 fence key',
        principal_type: 'agent',
        scope: 'write',
        workspace_ids: [SEEDED_WORKSPACE_ID],
        expires_at: new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString(),
      },
    });
    expect(keyResp.status()).toBe(201);
    const key = await keyResp.json();
    const fencedHeaders = { 'X-API-Key': key.plaintext as string };

    try {
      const denied = await request.get(
        `${BACKEND_URL}/api/v1/requirements/${foreignReq.id}/`,
        { headers: fencedHeaders }
      );
      expect(denied.status()).toBe(403);
      const deniedBody = await denied.json();
      expect(deniedBody.error.code).toBe('PERMISSION_DENIED');

      // No over-blocking: inside its own fence the key still reads.
      const allowed = await request.get(
        `${BACKEND_URL}/api/v1/requirements/${ownReq.id}/`,
        { headers: fencedHeaders }
      );
      expect(allowed.status()).toBe(200);
    } finally {
      await request.delete(`${BACKEND_URL}/api/v1/api-keys/${key.id}/`, {
        headers: authHeaders,
      });
      await request.delete(`${BACKEND_URL}/api/v1/requirements/${ownReq.id}/`, {
        headers: authHeaders,
        data: { change_reason: 'e2e cleanup' },
      });
      await request.delete(`${BACKEND_URL}/api/v1/requirements/${foreignReq.id}/`, {
        headers: authHeaders,
        data: { change_reason: 'e2e cleanup' },
      });
    }
  });
});
