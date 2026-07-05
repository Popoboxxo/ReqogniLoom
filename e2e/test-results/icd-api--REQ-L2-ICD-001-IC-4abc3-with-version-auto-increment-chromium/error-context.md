# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: icd-api.spec.ts >> [REQ-L2-ICD-001] ICD CRUD API >> [REQ-L2-ICD-001] Full CRUD round-trip for ICD with version auto-increment
- Location: tests\icd-api.spec.ts:8:7

# Error details

```
Error: expect(received).toBeGreaterThanOrEqual(expected)

Expected: >= 2
Received:    0
```

# Test source

```ts
  1  | // REQ-L2-ICD-001: ICD Management CRUD API
  2  | import { test, expect } from '@playwright/test';
  3  | import { getAuthToken, SEEDED_WORKSPACE_ID } from '../helpers/auth';
  4  | 
  5  | const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
  6  | 
  7  | test.describe('[REQ-L2-ICD-001] ICD CRUD API', () => {
  8  |   test('[REQ-L2-ICD-001] Full CRUD round-trip for ICD with version auto-increment', async ({ request }) => {
  9  |     const token = await getAuthToken();
  10 |     const headers = { Authorization: `Bearer ${token}` };
  11 | 
  12 |     // Fetch existing artifacts for source/target element IDs
  13 |     const artifactsResp = await request.get(
  14 |       `${BACKEND_URL}/api/v1/artifacts/?workspace_id=${SEEDED_WORKSPACE_ID}`,
  15 |       { headers },
  16 |     );
  17 |     let sourceId: string;
  18 |     let targetId: string;
  19 | 
  20 |     expect(artifactsResp.status()).toBe(200);
  21 |     const artifacts = await artifactsResp.json();
  22 |     const artifactList: Record<string, unknown>[] = Array.isArray(artifacts) ? artifacts : (artifacts.results ?? []);
> 23 |     expect(artifactList.length).toBeGreaterThanOrEqual(2);
     |                                 ^ Error: expect(received).toBeGreaterThanOrEqual(expected)
  24 |     sourceId = artifactList[0].id as string;
  25 |     targetId = artifactList[1].id as string;
  26 | 
  27 |     // Step 1: Create an ICD
  28 |     const createResp = await request.post(`${BACKEND_URL}/api/v1/icds/`, {
  29 |       headers,
  30 |       data: {
  31 |         name: 'E2E Test ICD',
  32 |         workspace_id: SEEDED_WORKSPACE_ID,
  33 |         source_element_id: sourceId,
  34 |         target_element_id: targetId,
  35 |         direction: 'unidirectional',
  36 |         interface_type: 'REST API',
  37 |         semantic_description: 'E2E test interface contract',
  38 |         preconditions: ['Consumer authenticated'],
  39 |         postconditions: ['Data returned'],
  40 |         invariants: ['Idempotent'],
  41 |       },
  42 |     });
  43 |     expect(createResp.status()).toBe(201);
  44 |     const created = await createResp.json();
  45 |     expect(created.id).toBeDefined();
  46 |     expect(created.name).toBe('E2E Test ICD');
  47 |     expect(created.version).toBe(1);
  48 |     const icdId = created.id;
  49 | 
  50 |     // Step 2: List ICDs
  51 |     const listResp = await request.get(
  52 |       `${BACKEND_URL}/api/v1/icds/?workspace_id=${SEEDED_WORKSPACE_ID}`,
  53 |       { headers },
  54 |     );
  55 |     expect(listResp.status()).toBe(200);
  56 | 
  57 |     // Step 3: Get single ICD
  58 |     const getResp = await request.get(`${BACKEND_URL}/api/v1/icds/${icdId}/`, { headers });
  59 |     expect(getResp.status()).toBe(200);
  60 |     const retrieved = await getResp.json();
  61 |     expect(retrieved.id).toBe(icdId);
  62 |     expect(retrieved.name).toBe('E2E Test ICD');
  63 |     expect(retrieved.version).toBe(1);
  64 | 
  65 |     // Step 4: Patch (update) ICD — version should auto-increment
  66 |     const patchResp = await request.patch(`${BACKEND_URL}/api/v1/icds/${icdId}/`, {
  67 |       headers,
  68 |       data: {
  69 |         semantic_description: 'Updated E2E test interface contract',
  70 |         preconditions: ['Consumer authenticated', 'Rate limit checked'],
  71 |       },
  72 |     });
  73 |     expect(patchResp.status()).toBe(200);
  74 |     const patched = await patchResp.json();
  75 |     expect(patched.version).toBe(2);  // Auto-incremented
  76 | 
  77 |     // Step 5: Verify version increment via retrieve
  78 |     const getAfterPatch = await request.get(`${BACKEND_URL}/api/v1/icds/${icdId}/`, { headers });
  79 |     expect(getAfterPatch.status()).toBe(200);
  80 |     const afterPatch = await getAfterPatch.json();
  81 |     expect(afterPatch.version).toBe(2);
  82 | 
  83 |     // Step 6: Delete ICD
  84 |     const deleteResp = await request.delete(`${BACKEND_URL}/api/v1/icds/${icdId}/`, { headers });
  85 |     expect(deleteResp.status()).toBe(204);
  86 | 
  87 |     // Step 7: Verify deletion
  88 |     const getDeletedResp = await request.get(`${BACKEND_URL}/api/v1/icds/${icdId}/`, { headers });
  89 |     expect(getDeletedResp.status()).toBe(404);
  90 |   });
  91 | });
  92 | 
```