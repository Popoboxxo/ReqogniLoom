# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: api-completeness.spec.ts >> [REQ-L0-012] REST API Completeness >> [REQ-L0-012] GET /api/v1/baselines/ returns list
- Location: tests\api-completeness.spec.ts:266:7

# Error details

```
Error: expect(received).toBe(expected) // Object.is equality

Expected: 200
Received: 404
```

# Test source

```ts
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
  252 |     // DELETE the tracelink
  253 |     const deleteResp = await request.delete(`${BACKEND_URL}/api/v1/tracelinks/${link.id}/`, {
  254 |       headers,
  255 |     });
  256 |     expect([200, 204]).toContain(deleteResp.status());
  257 | 
  258 |     // Cleanup reqs
  259 |     await request.delete(`${BACKEND_URL}/api/v1/requirements/${req1.id}/`, { headers });
  260 |     await request.delete(`${BACKEND_URL}/api/v1/requirements/${req2.id}/`, { headers });
  261 |   });
  262 | 
  263 |   // -------------------------------------------------------------------------
  264 |   // Baselines
  265 |   // -------------------------------------------------------------------------
  266 |   test('[REQ-L0-012] GET /api/v1/baselines/ returns list', async ({ request }) => {
  267 |     const token = await getAuthToken();
  268 |     const response = await request.get(`${BACKEND_URL}/api/v1/baselines/`, {
  269 |       headers: { Authorization: `Bearer ${token}` },
  270 |       params: { workspace_id: SEEDED_WORKSPACE_ID },
  271 |     });
> 272 |     expect(response.status()).toBe(200);
      |                               ^ Error: expect(received).toBe(expected) // Object.is equality
  273 |     const body = await response.json();
  274 |     const items = Array.isArray(body) ? body : body.results ?? [];
  275 |     expect(Array.isArray(items)).toBeTruthy();
  276 |   });
  277 | 
  278 |   // -------------------------------------------------------------------------
  279 |   // TestCases
  280 |   // -------------------------------------------------------------------------
  281 |   test('[REQ-L0-012] GET /api/v1/testcases/ returns list', async ({ request }) => {
  282 |     const token = await getAuthToken();
  283 |     const response = await request.get(`${BACKEND_URL}/api/v1/testcases/`, {
  284 |       headers: { Authorization: `Bearer ${token}` },
  285 |       params: { workspace_id: SEEDED_WORKSPACE_ID },
  286 |     });
  287 |     expect(response.status()).toBe(200);
  288 |     const body = await response.json();
  289 |     const items = Array.isArray(body) ? body : body.results ?? [];
  290 |     expect(Array.isArray(items)).toBeTruthy();
  291 |   });
  292 | 
  293 |   // -------------------------------------------------------------------------
  294 |   // Artifacts
  295 |   // -------------------------------------------------------------------------
  296 |   test('[REQ-L0-012] GET /api/v1/artifacts/ returns list', async ({ request }) => {
  297 |     const token = await getAuthToken();
  298 |     const response = await request.get(`${BACKEND_URL}/api/v1/artifacts/`, {
  299 |       headers: { Authorization: `Bearer ${token}` },
  300 |       params: { workspace_id: SEEDED_WORKSPACE_ID },
  301 |     });
  302 |     expect(response.status()).toBe(200);
  303 |     const body = await response.json();
  304 |     const items = Array.isArray(body) ? body : body.results ?? [];
  305 |     expect(Array.isArray(items)).toBeTruthy();
  306 |   });
  307 | 
  308 |   // -------------------------------------------------------------------------
  309 |   // Workspaces
  310 |   // -------------------------------------------------------------------------
  311 |   test('[REQ-L0-012] GET /api/v1/workspaces/ returns workspaces', async ({ request }) => {
  312 |     const token = await getAuthToken();
  313 |     const response = await request.get(`${BACKEND_URL}/api/v1/workspaces/`, {
  314 |       headers: { Authorization: `Bearer ${token}` },
  315 |     });
  316 |     expect(response.status()).toBe(200);
  317 |     const body = await response.json();
  318 |     const items: unknown[] = Array.isArray(body) ? body : body.results ?? [];
  319 |     expect(items.length).toBeGreaterThan(0);
  320 |   });
  321 | });
  322 | 
```