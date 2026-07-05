# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: dashboard.spec.ts >> [COMP-RF-002] DashboardViews >> [REQ-L3-RF002-001] dashboard renders workspace cards with name and metrics
- Location: tests\dashboard.spec.ts:13:7

# Error details

```
Test timeout of 10000ms exceeded.
```

```
Error: expect(locator).toBeVisible() failed

Locator: locator('[data-testid="workspace-list"]')
Expected: visible
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for locator('[data-testid="workspace-list"]')

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
  - status: Loading...
```

# Test source

```ts
  1  | // REQ-L2-RF-002, REQ-L3-RF002-001/002/003: Dashboard with workspace cards
  2  | import { test, expect } from '@playwright/test';
  3  | import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
  4  | 
  5  | const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
  6  | 
  7  | test.describe('[COMP-RF-002] DashboardViews', () => {
  8  |   test.beforeEach(async ({ page }) => {
  9  |     await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
  10 |     await loginAsAdmin(page);
  11 |   });
  12 | 
  13 |   test('[REQ-L3-RF002-001] dashboard renders workspace cards with name and metrics', async ({ page }) => {
  14 |     // Navigate to dashboard root
  15 |     await page.goto(`${FRONTEND_URL}/`);
  16 | 
  17 |     // Workspace list container must be visible
  18 |     const list = page.locator('[data-testid="workspace-list"]');
> 19 |     await expect(list).toBeVisible({ timeout: 10000 });
     |                        ^ Error: expect(locator).toBeVisible() failed
  20 | 
  21 |     // At least one workspace card must be rendered (seeded demo workspace)
  22 |     const cards = page.locator('[data-testid="workspace-card"]');
  23 |     await expect(cards.first()).toBeVisible({ timeout: 5000 });
  24 | 
  25 |     // First card content checks — it must contain a name (h3), requirement count, open items
  26 |     const firstCard = cards.first();
  27 |     await expect(firstCard.locator('h3')).toBeVisible();
  28 |     // Card text contains numeric metrics for requirements + open items
  29 |     const cardText = await firstCard.innerText();
  30 |     expect(cardText.length).toBeGreaterThan(0);
  31 |     // Two <strong> values: requirement_count + open_item_count
  32 |     const strongCount = await firstCard.locator('strong').count();
  33 |     expect(strongCount).toBeGreaterThanOrEqual(2);
  34 |   });
  35 | 
  36 |   test('[REQ-L3-RF002-002] workspace cards render terminology-profile-aware label', async ({ page }) => {
  37 |     await page.goto(`${FRONTEND_URL}/`);
  38 |     const firstCard = page.locator('[data-testid="workspace-card"]').first();
  39 |     await expect(firstCard).toBeVisible({ timeout: 10000 });
  40 | 
  41 |     // Card shows preset and a terminology profile label (devMode / seMode)
  42 |     const text = await firstCard.innerText();
  43 |     // Preset name appears (minimal / standard / extended)
  44 |     expect(text).toMatch(/minimal|standard|extended/i);
  45 |     // Either "Dev" or "SE" mode label is rendered (i18n English/German tolerant)
  46 |     expect(text).toMatch(/(dev|developer|systems engineer|se mode|engineer)/i);
  47 |   });
  48 | 
  49 |   test('[REQ-L3-RF002-003] clicking workspace card navigates away from dashboard', async ({ page }) => {
  50 |     await page.goto(`${FRONTEND_URL}/`);
  51 |     const firstCard = page.locator('[data-testid="workspace-card"]').first();
  52 |     await expect(firstCard).toBeVisible({ timeout: 10000 });
  53 | 
  54 |     await firstCard.click();
  55 |     // After selection, navigate is called -> /requirements
  56 |     await page.waitForURL(/\/requirements/, { timeout: 8000 });
  57 |     await expect(page).toHaveURL(/\/requirements/);
  58 |   });
  59 | });
  60 | 
```