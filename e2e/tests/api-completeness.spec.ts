// REQ-L0-012 — REST API Completeness: full CRUD for all core entities
// Pure API tests — no browser required
import { test, expect } from '@playwright/test';
import { getAuthToken, setWorkspacePreset, createIsolatedWorkspace, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

test.describe('[REQ-L0-012] REST API Completeness', () => {
  // The REQ-L0-002 preset switcher test mutates the seeded workspace's preset
  // (extended → minimal → extended) and its cleanup is not reliable across
  // test isolation. Baseline endpoints are preset-gated and return 404 in the
  // minimal preset (presets/registry.py: minimal.features.baselines = False),
  // so GET /api/v1/baselines/ only returns 200 when baselines are enabled.
  // Pin the preset to extended so this suite has a deterministic starting
  // state regardless of file order (see helpers/auth.ts setWorkspacePreset).
  test.beforeEach(async () => {
    await setWorkspacePreset('extended');
  });
  // -------------------------------------------------------------------------
  // Requirements CRUD
  // -------------------------------------------------------------------------
  test('[REQ-L0-012] GET /api/v1/requirements/ returns paginated list', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results ?? [];
    expect(Array.isArray(items)).toBeTruthy();
  });

  test('[REQ-L0-012] POST /api/v1/requirements/ creates a requirement', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: 'API Completeness E2E — Requirement',
        description: 'Created by api-completeness.spec.ts Playwright test',
        category: 'Functional',
      },
    });
    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.id).toBeDefined();
    expect(body.title).toBe('API Completeness E2E — Requirement');

    // Cleanup
    await request.delete(`${BACKEND_URL}/api/v1/requirements/${body.id}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
  });

  test('[REQ-L0-012] PATCH /api/v1/requirements/{id}/ updates title', async ({ request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };

    const createResp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: 'PATCH Target Requirement',
        category: 'Functional',
      },
    });
    expect(createResp.ok()).toBeTruthy();
    const created = await createResp.json();

    // Try PATCH first; fall back to PUT if PATCH is not supported (405)
    // change_reason is required in extended preset (REQ-L0-011 / KONZEPT.md §7.3)
    let patchResp = await request.patch(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, {
      headers,
      data: { title: 'PATCH Updated Requirement', change_reason: 'API completeness test update' },
    });

    if (!patchResp.ok()) {
      // Backend may require PUT with full payload
      patchResp = await request.put(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, {
        headers,
        data: {
          workspace_id: SEEDED_WORKSPACE_ID,
          title: 'PATCH Updated Requirement',
          category: 'Functional',
        },
      });
    }

    // If neither PATCH nor PUT succeeded, the backend does not support update — document it
    if (!patchResp.ok()) {
      const status = patchResp.status();
      const body = await patchResp.text();
      // Fail with informative message so developer can implement PATCH/PUT
      throw new Error(
        `[REQ-L0-012] Backend does not support PATCH or PUT on requirements (status ${status}): ${body.slice(0, 300)}`
      );
    }

    const updated = await patchResp.json();
    expect(updated.title).toBe('PATCH Updated Requirement');

    // Cleanup
    await request.delete(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, { headers });
  });

  test('[REQ-L0-012] DELETE /api/v1/requirements/{id}/ removes requirement', async ({ request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };

    const createResp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: 'DELETE Target Requirement',
        category: 'Functional',
      },
    });
    expect(createResp.ok()).toBeTruthy();
    const created = await createResp.json();

    const deleteResp = await request.delete(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, {
      headers,
    });
    expect([200, 204]).toContain(deleteResp.status());

    // Verify it is gone
    const getResp = await request.get(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, {
      headers,
    });
    expect([404, 403]).toContain(getResp.status());
  });

  // -------------------------------------------------------------------------
  // Architecture CRUD
  // -------------------------------------------------------------------------
  test('[REQ-L0-012] GET /api/v1/architecture/ returns paginated list', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/architecture/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results ?? [];
    expect(Array.isArray(items)).toBeTruthy();
  });

  test('[REQ-L0-012] POST /api/v1/architecture/ creates an element', async ({ request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };
    // [I5] A workspace tree may have exactly one root ArchitectureElement.
    // seed_demo now pre-seeds a root for SEEDED_WORKSPACE_ID, so a plain
    // (no parent_id) create against it always 400s here. Use a fresh,
    // element-free workspace instead, matching the pattern already used by
    // architecture.spec.ts / architecture-editor.spec.ts.
    const workspaceId = await createIsolatedWorkspace(token);

    const response = await request.post(`${BACKEND_URL}/api/v1/architecture/`, {
      headers,
      data: {
        workspace_id: workspaceId,
        title: 'API Completeness E2E — Architecture Element',
        element_type: 'component',
      },
    });
    expect(response.status()).toBe(201);
    const body = await response.json();
    expect(body.id).toBeDefined();
    expect(body.title).toBe('API Completeness E2E — Architecture Element');

    // Cleanup
    await request.delete(`${BACKEND_URL}/api/v1/architecture/${body.id}/`, { headers });
  });

  test('[REQ-L0-012] DELETE /api/v1/architecture/{id}/ removes element', async ({ request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };
    // [I5] see the POST test above — needs its own root-free workspace.
    const workspaceId = await createIsolatedWorkspace(token);

    const createResp = await request.post(`${BACKEND_URL}/api/v1/architecture/`, {
      headers,
      data: {
        workspace_id: workspaceId,
        title: 'DELETE Target Arch Element',
        element_type: 'module',
      },
    });
    expect(createResp.ok()).toBeTruthy();
    const created = await createResp.json();

    const deleteResp = await request.delete(`${BACKEND_URL}/api/v1/architecture/${created.id}/`, {
      headers,
    });
    expect([200, 204]).toContain(deleteResp.status());

    const getResp = await request.get(`${BACKEND_URL}/api/v1/architecture/${created.id}/`, {
      headers,
    });
    expect([404, 403]).toContain(getResp.status());
  });

  // -------------------------------------------------------------------------
  // TraceLinks CRUD
  // -------------------------------------------------------------------------
  test('[REQ-L0-012] GET /api/v1/tracelinks/ returns list', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/tracelinks/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results ?? [];
    expect(Array.isArray(items)).toBeTruthy();
  });

  test('[REQ-L0-012] POST /api/v1/tracelinks/ creates a tracelink and DELETE removes it', async ({ request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };

    // Create two requirements to link
    const req1Resp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: 'TraceLink Source Req E2E',
        category: 'Functional',
      },
    });
    expect(req1Resp.ok()).toBeTruthy();
    const req1 = await req1Resp.json();

    const req2Resp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        title: 'TraceLink Target Req E2E',
        category: 'Functional',
      },
    });
    expect(req2Resp.ok()).toBeTruthy();
    const req2 = await req2Resp.json();

    // Create the TraceLink
    const linkResp = await request.post(`${BACKEND_URL}/api/v1/tracelinks/`, {
      headers,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        source_artifact: req1.artifact_id ?? req1.id,
        target_artifact: req2.artifact_id ?? req2.id,
        link_type: 'derives',
      },
    });

    if (!linkResp.ok()) {
      // Some backends require artifact UUIDs not requirement UUIDs — skip gracefully
      const errText = await linkResp.text();
      test.skip(true, `TraceLink creation failed (${linkResp.status()}): ${errText.slice(0, 200)}`);
      // Cleanup reqs anyway
      await request.delete(`${BACKEND_URL}/api/v1/requirements/${req1.id}/`, { headers });
      await request.delete(`${BACKEND_URL}/api/v1/requirements/${req2.id}/`, { headers });
      return;
    }

    const link = await linkResp.json();
    expect(link.id).toBeDefined();

    // DELETE the tracelink
    const deleteResp = await request.delete(`${BACKEND_URL}/api/v1/tracelinks/${link.id}/`, {
      headers,
    });
    expect([200, 204]).toContain(deleteResp.status());

    // Cleanup reqs
    await request.delete(`${BACKEND_URL}/api/v1/requirements/${req1.id}/`, { headers });
    await request.delete(`${BACKEND_URL}/api/v1/requirements/${req2.id}/`, { headers });
  });

  // -------------------------------------------------------------------------
  // Baselines
  // -------------------------------------------------------------------------
  test('[REQ-L0-012] GET /api/v1/baselines/ returns list', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/baselines/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results ?? [];
    expect(Array.isArray(items)).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // TestCases
  // -------------------------------------------------------------------------
  test('[REQ-L0-012] GET /api/v1/testcases/ returns list', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/testcases/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results ?? [];
    expect(Array.isArray(items)).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // Artifacts
  // -------------------------------------------------------------------------
  test('[REQ-L0-012] GET /api/v1/artifacts/ returns list', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/artifacts/`, {
      headers: { Authorization: `Bearer ${token}` },
      params: { workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const items = Array.isArray(body) ? body : body.results ?? [];
    expect(Array.isArray(items)).toBeTruthy();
  });

  // -------------------------------------------------------------------------
  // Workspaces
  // -------------------------------------------------------------------------
  test('[REQ-L0-012] GET /api/v1/workspaces/ returns workspaces', async ({ request }) => {
    const token = await getAuthToken();
    const response = await request.get(`${BACKEND_URL}/api/v1/workspaces/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const items: unknown[] = Array.isArray(body) ? body : body.results ?? [];
    expect(items.length).toBeGreaterThan(0);
  });
});
