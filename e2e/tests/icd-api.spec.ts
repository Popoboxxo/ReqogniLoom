// REQ-L2-ICD-001: ICD Management CRUD API
import { test, expect } from '@playwright/test';
import { getAuthToken, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

test.describe('[REQ-L2-ICD-001] ICD CRUD API', () => {
  test('[REQ-L2-ICD-001] Full CRUD round-trip for ICD with version auto-increment', async ({ request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };

    // Fetch existing artifacts for source/target element IDs
    const artifactsResp = await request.get(
      `${BACKEND_URL}/api/v1/artifacts/?workspace_id=${SEEDED_WORKSPACE_ID}`,
      { headers },
    );
    let sourceId: string;
    let targetId: string;

    expect(artifactsResp.status()).toBe(200);
    const artifacts = await artifactsResp.json();
    const artifactList: Record<string, unknown>[] = Array.isArray(artifacts) ? artifacts : (artifacts.results ?? []);
    expect(artifactList.length).toBeGreaterThanOrEqual(2);
    sourceId = artifactList[0].id as string;
    targetId = artifactList[1].id as string;

    // Step 1: Create an ICD
    const createResp = await request.post(`${BACKEND_URL}/api/v1/icds/`, {
      headers,
      data: {
        name: 'E2E Test ICD',
        workspace_id: SEEDED_WORKSPACE_ID,
        source_element_id: sourceId,
        target_element_id: targetId,
        direction: 'unidirectional',
        interface_type: 'REST API',
        semantic_description: 'E2E test interface contract',
        preconditions: ['Consumer authenticated'],
        postconditions: ['Data returned'],
        invariants: ['Idempotent'],
      },
    });
    expect(createResp.status()).toBe(201);
    const created = await createResp.json();
    expect(created.id).toBeDefined();
    expect(created.name).toBe('E2E Test ICD');
    expect(created.version).toBe(1);
    const icdId = created.id;

    // Step 2: List ICDs
    const listResp = await request.get(
      `${BACKEND_URL}/api/v1/icds/?workspace_id=${SEEDED_WORKSPACE_ID}`,
      { headers },
    );
    expect(listResp.status()).toBe(200);

    // Step 3: Get single ICD
    const getResp = await request.get(`${BACKEND_URL}/api/v1/icds/${icdId}/`, { headers });
    expect(getResp.status()).toBe(200);
    const retrieved = await getResp.json();
    expect(retrieved.id).toBe(icdId);
    expect(retrieved.name).toBe('E2E Test ICD');
    expect(retrieved.version).toBe(1);

    // Step 4: Patch (update) ICD — version should auto-increment
    const patchResp = await request.patch(`${BACKEND_URL}/api/v1/icds/${icdId}/`, {
      headers,
      data: {
        semantic_description: 'Updated E2E test interface contract',
        preconditions: ['Consumer authenticated', 'Rate limit checked'],
      },
    });
    expect(patchResp.status()).toBe(200);
    const patched = await patchResp.json();
    expect(patched.version).toBe(2);  // Auto-incremented

    // Step 5: Verify version increment via retrieve
    const getAfterPatch = await request.get(`${BACKEND_URL}/api/v1/icds/${icdId}/`, { headers });
    expect(getAfterPatch.status()).toBe(200);
    const afterPatch = await getAfterPatch.json();
    expect(afterPatch.version).toBe(2);

    // Step 6: Delete ICD
    const deleteResp = await request.delete(`${BACKEND_URL}/api/v1/icds/${icdId}/`, { headers });
    expect(deleteResp.status()).toBe(204);

    // Step 7: Verify deletion
    const getDeletedResp = await request.get(`${BACKEND_URL}/api/v1/icds/${icdId}/`, { headers });
    expect(getDeletedResp.status()).toBe(404);
  });
});
