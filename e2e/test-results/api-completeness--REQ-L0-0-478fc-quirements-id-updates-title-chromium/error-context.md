# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: api-completeness.spec.ts >> [REQ-L0-012] REST API Completeness >> [REQ-L0-012] PATCH /api/v1/requirements/{id}/ updates title
- Location: tests\api-completeness.spec.ts:46:7

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Test source

```ts
  1   | // REQ-L0-012 — REST API Completeness: full CRUD for all core entities
  2   | // Pure API tests — no browser required
  3   | import { test, expect } from '@playwright/test';
  4   | import { getAuthToken, SEEDED_WORKSPACE_ID } from '../helpers/auth';
  5   | 
  6   | const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
  7   | 
  8   | test.describe('[REQ-L0-012] REST API Completeness', () => {
  9   |   // -------------------------------------------------------------------------
  10  |   // Requirements CRUD
  11  |   // -------------------------------------------------------------------------
  12  |   test('[REQ-L0-012] GET /api/v1/requirements/ returns paginated list', async ({ request }) => {
  13  |     const token = await getAuthToken();
  14  |     const response = await request.get(`${BACKEND_URL}/api/v1/requirements/`, {
  15  |       headers: { Authorization: `Bearer ${token}` },
  16  |       params: { workspace_id: SEEDED_WORKSPACE_ID },
  17  |     });
  18  |     expect(response.status()).toBe(200);
  19  |     const body = await response.json();
  20  |     const items = Array.isArray(body) ? body : body.results ?? [];
  21  |     expect(Array.isArray(items)).toBeTruthy();
  22  |   });
  23  | 
  24  |   test('[REQ-L0-012] POST /api/v1/requirements/ creates a requirement', async ({ request }) => {
  25  |     const token = await getAuthToken();
  26  |     const response = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
  27  |       headers: { Authorization: `Bearer ${token}` },
  28  |       data: {
  29  |         workspace_id: SEEDED_WORKSPACE_ID,
  30  |         title: 'API Completeness E2E — Requirement',
  31  |         description: 'Created by api-completeness.spec.ts Playwright test',
  32  |         category: 'Functional',
  33  |       },
  34  |     });
  35  |     expect(response.status()).toBe(201);
  36  |     const body = await response.json();
  37  |     expect(body.id).toBeDefined();
  38  |     expect(body.title).toBe('API Completeness E2E — Requirement');
  39  | 
  40  |     // Cleanup
  41  |     await request.delete(`${BACKEND_URL}/api/v1/requirements/${body.id}/`, {
  42  |       headers: { Authorization: `Bearer ${token}` },
  43  |     });
  44  |   });
  45  | 
  46  |   test('[REQ-L0-012] PATCH /api/v1/requirements/{id}/ updates title', async ({ request }) => {
  47  |     const token = await getAuthToken();
  48  |     const headers = { Authorization: `Bearer ${token}` };
  49  | 
  50  |     const createResp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
  51  |       headers,
  52  |       data: {
  53  |         workspace_id: SEEDED_WORKSPACE_ID,
  54  |         title: 'PATCH Target Requirement',
  55  |         category: 'Functional',
  56  |       },
  57  |     });
> 58  |     expect(createResp.ok()).toBeTruthy();
      |                             ^ Error: expect(received).toBeTruthy()
  59  |     const created = await createResp.json();
  60  | 
  61  |     // Try PATCH first; fall back to PUT if PATCH is not supported (405)
  62  |     // change_reason is required in extended preset (REQ-L0-011 / KONZEPT.md §7.3)
  63  |     let patchResp = await request.patch(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, {
  64  |       headers,
  65  |       data: { title: 'PATCH Updated Requirement', change_reason: 'API completeness test update' },
  66  |     });
  67  | 
  68  |     if (!patchResp.ok()) {
  69  |       // Backend may require PUT with full payload
  70  |       patchResp = await request.put(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, {
  71  |         headers,
  72  |         data: {
  73  |           workspace_id: SEEDED_WORKSPACE_ID,
  74  |           title: 'PATCH Updated Requirement',
  75  |           category: 'Functional',
  76  |         },
  77  |       });
  78  |     }
  79  | 
  80  |     // If neither PATCH nor PUT succeeded, the backend does not support update — document it
  81  |     if (!patchResp.ok()) {
  82  |       const status = patchResp.status();
  83  |       const body = await patchResp.text();
  84  |       // Fail with informative message so developer can implement PATCH/PUT
  85  |       throw new Error(
  86  |         `[REQ-L0-012] Backend does not support PATCH or PUT on requirements (status ${status}): ${body.slice(0, 300)}`
  87  |       );
  88  |     }
  89  | 
  90  |     const updated = await patchResp.json();
  91  |     expect(updated.title).toBe('PATCH Updated Requirement');
  92  | 
  93  |     // Cleanup
  94  |     await request.delete(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, { headers });
  95  |   });
  96  | 
  97  |   test('[REQ-L0-012] DELETE /api/v1/requirements/{id}/ removes requirement', async ({ request }) => {
  98  |     const token = await getAuthToken();
  99  |     const headers = { Authorization: `Bearer ${token}` };
  100 | 
  101 |     const createResp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
  102 |       headers,
  103 |       data: {
  104 |         workspace_id: SEEDED_WORKSPACE_ID,
  105 |         title: 'DELETE Target Requirement',
  106 |         category: 'Functional',
  107 |       },
  108 |     });
  109 |     expect(createResp.ok()).toBeTruthy();
  110 |     const created = await createResp.json();
  111 | 
  112 |     const deleteResp = await request.delete(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, {
  113 |       headers,
  114 |     });
  115 |     expect([200, 204]).toContain(deleteResp.status());
  116 | 
  117 |     // Verify it is gone
  118 |     const getResp = await request.get(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, {
  119 |       headers,
  120 |     });
  121 |     expect([404, 403]).toContain(getResp.status());
  122 |   });
  123 | 
  124 |   // -------------------------------------------------------------------------
  125 |   // Architecture CRUD
  126 |   // -------------------------------------------------------------------------
  127 |   test('[REQ-L0-012] GET /api/v1/architecture/ returns paginated list', async ({ request }) => {
  128 |     const token = await getAuthToken();
  129 |     const response = await request.get(`${BACKEND_URL}/api/v1/architecture/`, {
  130 |       headers: { Authorization: `Bearer ${token}` },
  131 |       params: { workspace_id: SEEDED_WORKSPACE_ID },
  132 |     });
  133 |     expect(response.status()).toBe(200);
  134 |     const body = await response.json();
  135 |     const items = Array.isArray(body) ? body : body.results ?? [];
  136 |     expect(Array.isArray(items)).toBeTruthy();
  137 |   });
  138 | 
  139 |   test('[REQ-L0-012] POST /api/v1/architecture/ creates an element', async ({ request }) => {
  140 |     const token = await getAuthToken();
  141 |     const headers = { Authorization: `Bearer ${token}` };
  142 | 
  143 |     const response = await request.post(`${BACKEND_URL}/api/v1/architecture/`, {
  144 |       headers,
  145 |       data: {
  146 |         workspace_id: SEEDED_WORKSPACE_ID,
  147 |         title: 'API Completeness E2E — Architecture Element',
  148 |         element_type: 'component',
  149 |       },
  150 |     });
  151 |     expect(response.status()).toBe(201);
  152 |     const body = await response.json();
  153 |     expect(body.id).toBeDefined();
  154 |     expect(body.title).toBe('API Completeness E2E — Architecture Element');
  155 | 
  156 |     // Cleanup
  157 |     await request.delete(`${BACKEND_URL}/api/v1/architecture/${body.id}/`, { headers });
  158 |   });
```