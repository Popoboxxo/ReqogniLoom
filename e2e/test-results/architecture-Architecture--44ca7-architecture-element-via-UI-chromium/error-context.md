# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: architecture.spec.ts >> Architecture Management >> [REQ-L1-004] create and save architecture element via UI
- Location: tests\architecture.spec.ts:49:7

# Error details

```
Test timeout of 10000ms exceeded.
```

```
Error: expect(locator).toBeVisible() failed

Locator: locator('[data-testid="arch-title"]')
Expected: visible
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for locator('[data-testid="arch-title"]')

```

```yaml
- navigation "Main navigation":
  - text: ReqFlow
  - searchbox "Suchen..."
  - list:
    - listitem:
      - link "Dashboard":
        - /url: /
    - listitem:
      - link "Stakeholder Needs":
        - /url: /needs
    - listitem:
      - link "System Requirements":
        - /url: /requirements
    - listitem:
      - link "Architecture":
        - /url: /architecture
    - listitem:
      - link "Trace Links":
        - /url: /traceability
    - listitem:
      - link "ADRs":
        - /url: /adrs
    - listitem:
      - link "Risks":
        - /url: /risks
    - listitem:
      - link "Issues":
        - /url: /issues
    - listitem:
      - link "Test Cases":
        - /url: /testcases
    - listitem:
      - link "Test Runs":
        - /url: /test-runs
    - listitem:
      - link "Baselines":
        - /url: /baselines
    - listitem:
      - link "Import":
        - /url: /import
    - listitem:
      - link "ICDs":
        - /url: /icds
    - listitem:
      - link "Diagrams":
        - /url: /diagrams
    - listitem:
      - link "Glossary":
        - /url: /glossary
    - listitem:
      - link "SE Metrics":
        - /url: /metrics
    - listitem:
      - link "Workspace Settings":
        - /url: /settings
  - switch "Optional-Artefakte" [checked]
  - button "Zahnbürste SysEng Demo"
  - text: extended Requirement
  - button "+ Workspace"
  - button "DE"
  - button "Dark mode"
  - button "Access Tokens"
  - button "Logout"
- main:
  - heading "Architecture" [level=3]
  - button "+ New"
  - button "▼"
  - text: subsystem Smart Toothbrush System L0
  - button "+"
  - button "✕"
  - button "▼"
  - text: subsystem Handstück L1
  - button "+"
  - button "✕"
  - button "▼"
  - text: component Motor Assembly L2
  - button "+"
  - button "✕"
  - button "▼"
  - text: component BLDC Motor L3
  - button "+"
  - button "✕"
  - text: component Rotor-Magnet L4
  - button "+"
  - button "✕"
  - text: component Stator-Spule L4
  - button "+"
  - button "✕"
  - text: component Antriebswelle L3
  - button "+"
  - button "✕"
  - button "▼"
  - text: component Batterie Assembly L2
  - button "+"
  - button "✕"
  - text: component Li-Ion Zelle 18650 L3
  - button "+"
  - button "✕"
  - button "▼"
  - text: component Main PCBA L2
  - button "+"
  - button "✕"
  - button "▼"
  - text: component Microcontroller STM32 L3
  - button "+"
  - button "✕"
  - text: module Motor PWM Modul L4
  - button "+"
  - button "✕"
  - text: module BLE Stack L4
  - button "+"
  - button "✕"
  - text: module Battery Management L4
  - button "+"
  - button "✕"
  - text: module UI Logik L4
  - button "+"
  - button "✕"
  - text: module Druckauswertung L4
  - button "+"
  - button "✕"
  - text: component Bluetooth IC L3
  - button "+"
  - button "✕"
  - text: component Drucksensor L3
  - button "+"
  - button "✕"
  - text: component Status-LED L3
  - button "+"
  - button "✕"
  - button "▼"
  - text: component Gehäuse L2
  - button "+"
  - button "✕"
  - text: component Dichtungsring L3
  - button "+"
  - button "✕"
  - text: component Gummiknopf L3
  - button "+"
  - button "✕"
  - button "▼"
  - text: subsystem Bürstenkopf L1
  - button "+"
  - button "✕"
  - text: component Borsten-Block L2
  - button "+"
  - button "✕"
  - button "▼"
  - text: subsystem Ladestation L1
  - button "+"
  - button "✕"
  - text: component Induktionsspule L2
  - button "+"
  - button "✕"
  - button "▼"
  - text: component Reise-Etui L2
  - button "+"
  - button "✕"
  - text: component Etui Powerbank L3
  - button "+"
  - button "✕"
  - text: component Etui Ladeelektronik L3
  - button "+"
  - button "✕"
  - text: component Scharnier L3
  - button "+"
  - button "✕"
  - button "▼"
  - text: subsystem Putz-Coaching App L1
  - button "+"
  - button "✕"
  - text: module App Dashboard L2
  - button "+"
  - button "✕"
  - text: module App Sync Manager L2
  - button "+"
  - button "✕"
  - text: component New Element L0
  - button "+"
  - button "✕"
  - text: component New Element L0
  - button "+"
  - button "✕"
  - text: component New Element L0
  - button "+"
  - button "✕"
  - paragraph: Select an architecture element from the list.
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
  38 |     expect(response.ok()).toBeTruthy();
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
> 54 |     await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
     |                                                              ^ Error: expect(locator).toBeVisible() failed
  55 |     await page.locator('[data-testid="arch-title"]').fill('UI E2E Arch Element');
  56 |     await page.locator('[data-testid="arch-save-btn"]').click();
  57 | 
  58 |     await expect(page.locator('[data-testid="arch-title"]')).toHaveValue('UI E2E Arch Element', { timeout: 8000 });
  59 |   });
  60 | });
  61 | 
```