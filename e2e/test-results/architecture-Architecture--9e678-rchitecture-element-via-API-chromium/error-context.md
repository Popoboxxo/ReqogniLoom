# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: architecture.spec.ts >> Architecture Management >> [REQ-L1-004] create architecture element via API
- Location: tests\architecture.spec.ts:28:7

# Error details

```
Error: expect(received).toBeTruthy()

Received: false
```

# Page snapshot

```yaml
- generic [ref=e3]:
  - navigation "Main navigation" [ref=e4]:
    - generic [ref=e7]: ReqFlow
    - searchbox "Suchen..." [ref=e9]
    - list [ref=e10]:
      - listitem [ref=e11]:
        - link "Dashboard" [ref=e12] [cursor=pointer]:
          - /url: /
      - listitem [ref=e13]:
        - link "Stakeholder Needs" [ref=e14] [cursor=pointer]:
          - /url: /needs
      - listitem [ref=e15]:
        - link "System Requirements" [ref=e16] [cursor=pointer]:
          - /url: /requirements
      - listitem [ref=e17]:
        - link "Architecture" [ref=e18] [cursor=pointer]:
          - /url: /architecture
      - listitem [ref=e19]:
        - link "Trace Links" [ref=e20] [cursor=pointer]:
          - /url: /traceability
      - listitem [ref=e21]:
        - link "ADRs" [ref=e22] [cursor=pointer]:
          - /url: /adrs
      - listitem [ref=e23]:
        - link "Risks" [ref=e24] [cursor=pointer]:
          - /url: /risks
      - listitem [ref=e25]:
        - link "Issues" [ref=e26] [cursor=pointer]:
          - /url: /issues
      - listitem [ref=e27]:
        - link "Test Cases" [ref=e28] [cursor=pointer]:
          - /url: /testcases
      - listitem [ref=e29]:
        - link "Test Runs" [ref=e30] [cursor=pointer]:
          - /url: /test-runs
      - listitem [ref=e31]:
        - link "Baselines" [ref=e32] [cursor=pointer]:
          - /url: /baselines
      - listitem [ref=e33]:
        - link "Import" [ref=e34] [cursor=pointer]:
          - /url: /import
      - listitem [ref=e35]:
        - link "ICDs" [ref=e36] [cursor=pointer]:
          - /url: /icds
      - listitem [ref=e37]:
        - link "Diagrams" [ref=e38] [cursor=pointer]:
          - /url: /diagrams
      - listitem [ref=e39]:
        - link "Glossary" [ref=e40] [cursor=pointer]:
          - /url: /glossary
      - listitem [ref=e41]:
        - link "SE Metrics" [ref=e42] [cursor=pointer]:
          - /url: /metrics
      - listitem [ref=e43]:
        - link "Workspace Settings" [ref=e44] [cursor=pointer]:
          - /url: /settings
    - switch "Optional-Artefakte" [checked] [ref=e45] [cursor=pointer]:
      - generic [ref=e46]: Optional-Artefakte
    - generic [ref=e49]:
      - button "Zahnbürste SysEng Demo" [ref=e50] [cursor=pointer]:
        - generic "Zahnbürste SysEng Demo" [ref=e51]
        - generic [ref=e52]: ▾
      - generic [ref=e53]:
        - generic [ref=e54]: extended
        - generic [ref=e55]: Requirement
      - button "+ Workspace" [ref=e56] [cursor=pointer]
    - generic [ref=e57]:
      - button "DE" [ref=e58] [cursor=pointer]
      - button "Dark mode" [ref=e59] [cursor=pointer]
      - button "Access Tokens" [ref=e60] [cursor=pointer]
      - button "Logout" [ref=e61] [cursor=pointer]
  - main [ref=e62]:
    - status [ref=e63]: Loading...
```

# Test source

```ts
  1  | // REQ-L1-004, REQ-L2-AS-004: Architecture elements CRUD
  2  | import { test, expect } from '@playwright/test';
  3  | import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
  4  | 
  5  | const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
  6  | const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
  7  | 
  8  | test.describe('Architecture Management', () => {
  9  |   test.beforeEach(async ({ page }) => {
  10 |     // Inject real workspace ID so WorkspaceContext uses the seeded workspace
  11 |     await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
  12 |     await loginAsAdmin(page);
  13 |   });
  14 | 
  15 |   test('[REQ-L1-004] architecture list page loads', async ({ page }) => {
  16 |     await page.goto(`${FRONTEND_URL}/architecture`);
  17 |     await expect(page.locator('body')).toBeVisible();
  18 |     await expect(page.locator('[data-testid="create-arch-btn"]')).toBeVisible({ timeout: 10000 });
  19 |   });
  20 | 
  21 |   test('[REQ-L1-004] can open new architecture element form', async ({ page }) => {
  22 |     await page.goto(`${FRONTEND_URL}/architecture`);
  23 |     await page.locator('[data-testid="create-arch-btn"]').click();
  24 |     // Title input should appear after successful create + navigation to /architecture/:id
  25 |     await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
  26 |   });
  27 | 
  28 |   test('[REQ-L1-004] create architecture element via API', async ({ request }) => {
  29 |     const token = await getAuthToken();
  30 |     const response = await request.post(`${BACKEND_URL}/api/v1/architecture/`, {
  31 |       headers: { Authorization: `Bearer ${token}` },
  32 |       data: {
  33 |         workspace_id: SEEDED_WORKSPACE_ID,
  34 |         title: 'E2E Test Architecture Element',
  35 |         element_type: 'component',
  36 |       },
  37 |     });
> 38 |     expect(response.ok()).toBeTruthy();
     |                           ^ Error: expect(received).toBeTruthy()
  39 |     const body = await response.json();
  40 |     expect(body.id).toBeDefined();
  41 |     expect(body.title).toBe('E2E Test Architecture Element');
  42 | 
  43 |     // Cleanup
  44 |     await request.delete(`${BACKEND_URL}/api/v1/architecture/${body.id}/`, {
  45 |       headers: { Authorization: `Bearer ${token}` },
  46 |     });
  47 |   });
  48 | 
  49 |   test('[REQ-L1-004] create and save architecture element via UI', async ({ page }) => {
  50 |     await page.goto(`${FRONTEND_URL}/architecture`);
  51 |     await page.locator('[data-testid="create-arch-btn"]').click();
  52 | 
  53 |     // Wait for navigation to /architecture/:id and the title input to appear
  54 |     await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
  55 |     await page.locator('[data-testid="arch-title"]').fill('UI E2E Arch Element');
  56 |     await page.locator('[data-testid="arch-save-btn"]').click();
  57 | 
  58 |     await expect(page.locator('[data-testid="arch-title"]')).toHaveValue('UI E2E Arch Element', { timeout: 8000 });
  59 |   });
  60 | });
  61 | 
```