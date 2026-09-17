// REQ-L2-DS-001: DiagramService CRUD API
import { test, expect } from '@playwright/test';
import { getAuthToken, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

test.describe('[REQ-L2-DS-001] Diagram CRUD API', () => {
  test('[REQ-L2-DS-001] Full CRUD round-trip for diagrams', async ({ request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };

    // Step 1: Create a diagram
    // workspace_id is required: without it, Diagram.workspace_id stays None
    // and DELETE (workflow.services.outdate -> UUID(str(None))) 500s instead
    // of soft-deleting (backend/diagram/services.py delete_diagram).
    const createResp = await request.post(`${BACKEND_URL}/api/v1/diagrams/`, {
      headers,
      data: {
        workspace_id: SEEDED_WORKSPACE_ID,
        name: 'E2E Test Diagram',
        diagram_type: 'block',
        payload_format: 'json',
        content: JSON.stringify({ nodes: [{ id: 'n1' }], edges: [{ id: 'e1', from: 'n1', to: 'n2' }] }),
        description: 'Created by E2E test',
      },
    });
    expect(createResp.status()).toBe(201);
    const created = await createResp.json();
    expect(created.id).toBeDefined();
    expect(created.name).toBe('E2E Test Diagram');
    const diagramId = created.id;

    // Step 2: List diagrams
    const listResp = await request.get(
      `${BACKEND_URL}/api/v1/diagrams/?workspace_id=${SEEDED_WORKSPACE_ID}`,
      { headers },
    );
    expect(listResp.status()).toBe(200);

    // Step 3: Get single diagram
    const getResp = await request.get(`${BACKEND_URL}/api/v1/diagrams/${diagramId}/`, { headers });
    expect(getResp.status()).toBe(200);
    const retrieved = await getResp.json();
    expect(retrieved.id).toBe(diagramId);
    expect(retrieved.name).toBe('E2E Test Diagram');
    // Verify nodes/edges structure exists in content
    if (retrieved.content) {
      const parsed = typeof retrieved.content === 'string' ? JSON.parse(retrieved.content) : retrieved.content;
      expect(parsed.nodes ?? parsed.nodes).toBeDefined();
    }

    // Step 4: Patch (update) diagram
    const patchResp = await request.patch(`${BACKEND_URL}/api/v1/diagrams/${diagramId}/`, {
      headers,
      data: {
        payload_format: 'json',
        content: JSON.stringify({ nodes: [{ id: 'n1' }, { id: 'n3' }], edges: [] }),
      },
    });
    expect(patchResp.status()).toBe(200);
    const patched = await patchResp.json();
    expect(patched.version_number).toBeGreaterThanOrEqual(2);

    // Step 5: Delete diagram
    const deleteResp = await request.delete(`${BACKEND_URL}/api/v1/diagrams/${diagramId}/`, {
      headers,
    });
    expect(deleteResp.status()).toBe(204);

    // Step 6: Verify deletion
    const getDeletedResp = await request.get(`${BACKEND_URL}/api/v1/diagrams/${diagramId}/`, {
      headers,
    });
    expect(getDeletedResp.status()).toBe(404);
  });
});
