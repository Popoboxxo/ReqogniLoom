# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: requirements.spec.ts >> Requirements Management >> [REQ-L1-002] create and edit requirement via UI
- Location: tests\requirements.spec.ts:51:7

# Error details

```
Test timeout of 10000ms exceeded while running "beforeEach" hook.
```

```
Error: page.fill: Test timeout of 10000ms exceeded.
Call log:
  - waiting for locator('#username-input')

```

# Test source

```ts
  1   | import { Page, request } from '@playwright/test';
  2   | 
  3   | const BASE_URL = process.env.BACKEND_URL || 'http://localhost:8000';
  4   | const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
  5   | 
  6   | export const TEST_USER = {
  7   |   username: 'admin',
  8   |   password: 'admin12345',
  9   | };
  10  | 
  11  | /**
  12  |  * Login via UI on the /login page.
  13  |  * Uses real selectors: #username-input, #password-input, button[type="submit"]
  14  |  */
  15  | export async function loginAsAdmin(page: Page): Promise<void> {
  16  |   await page.goto(`${FRONTEND_URL}/login`);
> 17  |   await page.fill('#username-input', TEST_USER.username);
      |              ^ Error: page.fill: Test timeout of 10000ms exceeded.
  18  |   await page.fill('#password-input', TEST_USER.password);
  19  |   await page.click('button[type="submit"]');
  20  |   // Wait for redirect away from /login
  21  |   await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 10000 });
  22  | }
  23  | 
  24  | /**
  25  |  * Get a JWT token directly via API (no browser needed).
  26  |  */
  27  | export async function getAuthToken(): Promise<string> {
  28  |   const ctx = await request.newContext({ baseURL: BASE_URL });
  29  |   const response = await ctx.post('/api/v1/auth/login/', {
  30  |     data: { username: TEST_USER.username, password: TEST_USER.password },
  31  |   });
  32  |   if (!response.ok()) {
  33  |     throw new Error(`Login failed: ${response.status()} ${await response.text()}`);
  34  |   }
  35  |   const body = await response.json();
  36  |   await ctx.dispose();
  37  |   // Token field may be 'token' or 'access' depending on backend implementation
  38  |   return body.token || body.access || body.access_token;
  39  | }
  40  | 
  41  | /**
  42  |  * Get the first available workspace ID for the logged-in user.
  43  |  * Falls back to the tenant's default workspace from the login response.
  44  |  */
  45  | export async function getWorkspaceId(token: string): Promise<string> {
  46  |   const ctx = await request.newContext({ baseURL: BASE_URL });
  47  |   // Try /api/v1/workspaces/ first (may not be implemented)
  48  |   try {
  49  |     const wsResp = await ctx.get('/api/v1/workspaces/', {
  50  |       headers: { Authorization: `Bearer ${token}` },
  51  |     });
  52  |     if (wsResp.ok()) {
  53  |       const body = await wsResp.json();
  54  |       const items = Array.isArray(body) ? body : body.results ?? [];
  55  |       if (items.length > 0 && items[0].id) {
  56  |         await ctx.dispose();
  57  |         return items[0].id as string;
  58  |       }
  59  |     }
  60  |   } catch {
  61  |     // endpoint not implemented — fall through
  62  |   }
  63  |   await ctx.dispose();
  64  |   // Fall back to the workspace ID seeded by seed_demo (discovered at test setup time)
  65  |   // This is the real workspace created for the demo tenant.
  66  |   return SEEDED_WORKSPACE_ID;
  67  | }
  68  | 
  69  | /**
  70  |  * Inject JWT token and workspace ID into sessionStorage so tests skip the
  71  |  * login UI and the WorkspaceContext picks up the real workspace.
  72  |  */
  73  | export async function setAuthToken(page: Page, token: string): Promise<void> {
  74  |   await page.addInitScript((t) => {
  75  |     sessionStorage.setItem('reqflow_token', t);
  76  |   }, token);
  77  | }
  78  | 
  79  | /**
  80  |  * Inject workspace ID into sessionStorage before page load so WorkspaceContext
  81  |  * uses the real workspace instead of the default zero-UUID mock.
  82  |  */
  83  | export async function setWorkspaceId(page: Page, workspaceId: string): Promise<void> {
  84  |   await page.addInitScript((wsId) => {
  85  |     sessionStorage.setItem('reqflow_workspace_id', wsId);
  86  |   }, workspaceId);
  87  | }
  88  | 
  89  | /**
  90  |  * Workspace preset tier name as accepted by PATCH /api/v1/workspaces/{id}/preset/.
  91  |  */
  92  | export type WorkspacePresetName = 'minimal' | 'standard' | 'extended';
  93  | 
  94  | /**
  95  |  * Reset the seeded workspace's active preset via API.
  96  |  *
  97  |  * The REQ-L0-002 preset switcher test mutates the seeded workspace's preset
  98  |  * (extended → minimal → extended) and its UI-driven cleanup is not always
  99  |  * reliable as a state reset for downstream tests. Tests that depend on a
  100 |  * specific preset (e.g. REQ-L0-012 smoke test, which requires the extended
  101 |  * preset so /api/v1/baselines/ returns 200) call this helper in their
  102 |  * beforeEach to guarantee a known starting preset regardless of file order
  103 |  * or test isolation state.
  104 |  */
  105 | export async function setWorkspacePreset(preset: WorkspacePresetName): Promise<void> {
  106 |   const token = await getAuthToken();
  107 |   const ctx = await request.newContext({ baseURL: BASE_URL });
  108 |   const response = await ctx.patch(
  109 |     `/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/preset/`,
  110 |     {
  111 |       headers: { Authorization: `Bearer ${token}` },
  112 |       data: { preset },
  113 |     }
  114 |   );
  115 |   await ctx.dispose();
  116 |   if (!response.ok()) {
  117 |     throw new Error(
```