# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: api-completeness.spec.ts >> [REQ-L0-012] REST API Completeness >> [REQ-L0-012] POST /api/v1/architecture/ creates an element
- Location: tests\api-completeness.spec.ts:139:7

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 201
Received: 404
```

# Test source

```ts
  51  |       headers,
  52  |       data: {
  53  |         workspace_id: SEEDED_WORKSPACE_ID,
  54  |         title: 'PATCH Target Requirement',
  55  |         category: 'Functional',
  56  |       },
  57  |     });
  58  |     expect(createResp.ok()).toBeTruthy();
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
> 151 |     expect(response.status()).toBe(201);
      |                               ^ Error: expect(received).toBe(expected) // Object.is equality
  152 |     const body = await response.json();
  153 |     expect(body.id).toBeDefined();
  154 |     expect(body.title).toBe('API Completeness E2E — Architecture Element');
  155 | 
  156 |     // Cleanup
  157 |     await request.delete(`${BACKEND_URL}/api/v1/architecture/${body.id}/`, { headers });
  158 |   });
  159 | 
  160 |   test('[REQ-L0-012] DELETE /api/v1/architecture/{id}/ removes element', async ({ request }) => {
  161 |     const token = await getAuthToken();
  162 |     const headers = { Authorization: `Bearer ${token}` };
  163 | 
  164 |     const createResp = await request.post(`${BACKEND_URL}/api/v1/architecture/`, {
  165 |       headers,
  166 |       data: {
  167 |         workspace_id: SEEDED_WORKSPACE_ID,
  168 |         title: 'DELETE Target Arch Element',
  169 |         element_type: 'module',
  170 |       },
  171 |     });
  172 |     expect(createResp.ok()).toBeTruthy();
  173 |     const created = await createResp.json();
  174 | 
  175 |     const deleteResp = await request.delete(`${BACKEND_URL}/api/v1/architecture/${created.id}/`, {
  176 |       headers,
  177 |     });
  178 |     expect([200, 204]).toContain(deleteResp.status());
  179 | 
  180 |     const getResp = await request.get(`${BACKEND_URL}/api/v1/architecture/${created.id}/`, {
  181 |       headers,
  182 |     });
  183 |     expect([404, 403]).toContain(getResp.status());
  184 |   });
  185 | 
  186 |   // -------------------------------------------------------------------------
  187 |   // TraceLinks CRUD
  188 |   // -------------------------------------------------------------------------
  189 |   test('[REQ-L0-012] GET /api/v1/tracelinks/ returns list', async ({ request }) => {
  190 |     const token = await getAuthToken();
  191 |     const response = await request.get(`${BACKEND_URL}/api/v1/tracelinks/`, {
  192 |       headers: { Authorization: `Bearer ${token}` },
  193 |       params: { workspace_id: SEEDED_WORKSPACE_ID },
  194 |     });
  195 |     expect(response.status()).toBe(200);
  196 |     const body = await response.json();
  197 |     const items = Array.isArray(body) ? body : body.results ?? [];
  198 |     expect(Array.isArray(items)).toBeTruthy();
  199 |   });
  200 | 
  201 |   test('[REQ-L0-012] POST /api/v1/tracelinks/ creates a tracelink and DELETE removes it', async ({ request }) => {
  202 |     const token = await getAuthToken();
  203 |     const headers = { Authorization: `Bearer ${token}` };
  204 | 
  205 |     // Create two requirements to link
  206 |     const req1Resp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
  207 |       headers,
  208 |       data: {
  209 |         workspace_id: SEEDED_WORKSPACE_ID,
  210 |         title: 'TraceLink Source Req E2E',
  211 |         category: 'Functional',
  212 |       },
  213 |     });
  214 |     expect(req1Resp.ok()).toBeTruthy();
  215 |     const req1 = await req1Resp.json();
  216 | 
  217 |     const req2Resp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
  218 |       headers,
  219 |       data: {
  220 |         workspace_id: SEEDED_WORKSPACE_ID,
  221 |         title: 'TraceLink Target Req E2E',
  222 |         category: 'Functional',
  223 |       },
  224 |     });
  225 |     expect(req2Resp.ok()).toBeTruthy();
  226 |     const req2 = await req2Resp.json();
  227 | 
  228 |     // Create the TraceLink
  229 |     const linkResp = await request.post(`${BACKEND_URL}/api/v1/tracelinks/`, {
  230 |       headers,
  231 |       data: {
  232 |         workspace_id: SEEDED_WORKSPACE_ID,
  233 |         source_artifact: req1.artifact_id ?? req1.id,
  234 |         target_artifact: req2.artifact_id ?? req2.id,
  235 |         link_type: 'derives',
  236 |       },
  237 |     });
  238 | 
  239 |     if (!linkResp.ok()) {
  240 |       // Some backends require artifact UUIDs not requirement UUIDs — skip gracefully
  241 |       const errText = await linkResp.text();
  242 |       test.skip(true, `TraceLink creation failed (${linkResp.status()}): ${errText.slice(0, 200)}`);
  243 |       // Cleanup reqs anyway
  244 |       await request.delete(`${BACKEND_URL}/api/v1/requirements/${req1.id}/`, { headers });
  245 |       await request.delete(`${BACKEND_URL}/api/v1/requirements/${req2.id}/`, { headers });
  246 |       return;
  247 |     }
  248 | 
  249 |     const link = await linkResp.json();
  250 |     expect(link.id).toBeDefined();
  251 | 
```