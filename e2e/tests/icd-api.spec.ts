// REQ-L2-ICD-001: ICD Management CRUD API
import { test, expect } from '@playwright/test';
import { getAuthToken, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

test.describe('[REQ-L2-ICD-001] ICD CRUD API', () => {
  test('[REQ-L2-ICD-001] Full CRUD round-trip for ICD with version auto-increment', async ({ request }) => {
    const token = await getAuthToken();
    const headers = { Authorization: `Bearer ${token}` };

    // Provision the two ArchitectureElement artifacts this test needs.
    // NOTE: /api/v1/icds/ requires source_element_id/target_element_id to
    // reference ArchitectureElement artifacts (backend/icd/icd_manager.py).
    // The generic /api/v1/artifacts/ endpoint returns the workspace's whole
    // artifact tree (all types, e.g. StakeholderNeed) and does not support
    // filtering by artifact_type, so it cannot be used here — use the
    // dedicated /api/v1/architecture/ endpoint instead.
    //
    // The elements MUST be created here rather than read from whatever the
    // seeded workspace happens to contain: `seed_demo` provisions only the
    // tenant/user/workspace and no artifacts at all, and the suite runs
    // sharded (`--shard=N/4`) with a *separate database per shard job*. The
    // specs that do create architecture elements (architecture.spec.ts,
    // architecture-editor.spec.ts) land in shard 1 while this file lands in
    // shard 2, so relying on their leftovers made this test fail on every
    // sharded CI run while passing on an unsharded local run.
    //
    // Invariant I5 (backend/application/validators.py) allows a workspace
    // exactly one *root* element, so the second element has to be attached
    // under the first via `parent_id` — creating two roots returns 400.
    // Existing elements are reused when the workspace already has some (a
    // long-lived dev database, or a shard that did run the architecture
    // specs first), and only the ones created here are cleaned up again.
    const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const createdElementIds: string[] = [];

    const createElement = async (title: string, parentId?: string): Promise<string> => {
      const resp = await request.post(`${BACKEND_URL}/api/v1/architecture/`, {
        headers,
        data: {
          workspace_id: SEEDED_WORKSPACE_ID,
          title,
          element_type: 'component',
          ...(parentId ? { parent_id: parentId } : {}),
        },
      });
      expect(resp.status(), await resp.text()).toBe(201);
      const element = await resp.json();
      expect(element.id).toBeDefined();
      createdElementIds.push(element.id as string);
      return element.id as string;
    };

    const elementsResp = await request.get(
      `${BACKEND_URL}/api/v1/architecture/?workspace_id=${SEEDED_WORKSPACE_ID}`,
      { headers },
    );
    expect(elementsResp.status()).toBe(200);
    const elementsBody = await elementsResp.json();
    const existing: Record<string, unknown>[] = Array.isArray(elementsBody)
      ? elementsBody
      : (elementsBody.results ?? []);

    const rootId =
      (existing.find((el) => el.parent_id == null)?.id as string | undefined) ??
      (await createElement(`E2E ICD Root Element ${suffix}`));
    const sourceId = rootId;
    const targetId =
      (existing.find((el) => (el.id as string) !== rootId)?.id as string | undefined) ??
      (await createElement(`E2E ICD Target Element ${suffix}`, rootId));
    expect(sourceId).not.toBe(targetId);

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

    // Cleanup: remove only the architecture elements provisioned above (leaves
    // first, so a child is never orphaned) so repeated runs against a
    // long-lived dev database don't accumulate them.
    for (const elementId of [...createdElementIds].reverse()) {
      await request.delete(`${BACKEND_URL}/api/v1/architecture/${elementId}/`, { headers });
    }
  });
});
