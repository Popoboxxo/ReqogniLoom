# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: csv-import.spec.ts >> CSV Import >> [REQ-L0-013] csv import creates requirements
- Location: tests\csv-import.spec.ts:30:7

# Error details

```
Test timeout of 10000ms exceeded.
```

```
Error: expect(locator).toBeVisible() failed

Locator: locator('[data-testid="csv-import-success"]')
Expected: visible
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for locator('[data-testid="csv-import-success"]')

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
  - heading "CSV Import" [level=2]
  - heading "Entity Type" [level=3]
  - radio "Requirement" [checked]
  - text: Requirement
  - radio "ArchitectureElement"
  - text: ArchitectureElement
  - radio "TestCase"
  - text: TestCase
  - heading "Select CSV File" [level=3]
  - paragraph: e2e-import-test.csv
  - paragraph: 0.2 KB
  - button "Import"
  - button "Reset"
  - alert: Import failed (HTTP 400)
```

# Test source

```ts
  1  | // REQ-L0-013, REQ-L2-RF-016: CSV Bulk Import E2E
  2  | import { test, expect } from '@playwright/test';
  3  | import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
  4  | import path from 'path';
  5  | import fs from 'fs';
  6  | import os from 'os';
  7  | 
  8  | const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
  9  | const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
  10 | 
  11 | // Sample CSV content for testing
  12 | const SAMPLE_CSV = `title,description,category,status
  13 | E2E Import Req 1,First imported requirement,functional,draft
  14 | E2E Import Req 2,Second imported requirement,non-functional,draft
  15 | E2E Import Req 3,Third imported requirement,functional,draft
  16 | `;
  17 | 
  18 | test.describe('CSV Import', () => {
  19 |   test.beforeEach(async ({ page }) => {
  20 |     await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
  21 |     await loginAsAdmin(page);
  22 |   });
  23 | 
  24 |   test('[REQ-L0-013] import page loads', async ({ page }) => {
  25 |     await page.goto(`${FRONTEND_URL}/import`);
  26 |     await expect(page.locator('[data-testid="csv-import-page"]')).toBeVisible({ timeout: 10000 });
  27 |     await expect(page.locator('[data-testid="csv-import-btn"]')).toBeVisible();
  28 |   });
  29 | 
  30 |   test('[REQ-L0-013] csv import creates requirements', async ({ page, request }) => {
  31 |     // Create a temporary CSV file
  32 |     const tmpDir = os.tmpdir();
  33 |     const csvPath = path.join(tmpDir, 'e2e-import-test.csv');
  34 |     fs.writeFileSync(csvPath, SAMPLE_CSV, 'utf-8');
  35 | 
  36 |     // Get auth token for API verification
  37 |     const token = await getAuthToken();
  38 | 
  39 |     // Navigate to import page
  40 |     await page.goto(`${FRONTEND_URL}/import`);
  41 |     await expect(page.locator('[data-testid="csv-import-page"]')).toBeVisible({ timeout: 10000 });
  42 | 
  43 |     // Select entity type (Requirement is default)
  44 |     await expect(page.locator('[data-testid="entity-type-Requirement"]')).toBeChecked();
  45 | 
  46 |     // Upload file
  47 |     const fileInput = page.locator('[data-testid="csv-file-input"]');
  48 |     await fileInput.setInputFiles(csvPath);
  49 | 
  50 |     // Verify file is shown
  51 |     await expect(page.locator('[data-testid="csv-drop-zone"]')).toContainText('e2e-import-test.csv');
  52 | 
  53 |     // Click import button
  54 |     await page.locator('[data-testid="csv-import-btn"]').click();
  55 | 
  56 |     // Wait for success result
> 57 |     await expect(page.locator('[data-testid="csv-import-success"]')).toBeVisible({ timeout: 10000 });
     |                                                                      ^ Error: expect(locator).toBeVisible() failed
  58 |     await expect(page.locator('[data-testid="csv-import-success"]')).toContainText('3');
  59 | 
  60 |     // Cleanup: verify requirements were created via API and delete them
  61 |     const listResp = await request.get(`${BACKEND_URL}/api/v1/requirements/?workspace_id=${SEEDED_WORKSPACE_ID}`, {
  62 |       headers: { Authorization: `Bearer ${token}` },
  63 |     });
  64 |     expect(listResp.ok()).toBeTruthy();
  65 |     const listBody = await listResp.json();
  66 |     const importedReqs = (listBody.results || []).filter(
  67 |       (r: { title: string }) => r.title?.startsWith('E2E Import Req')
  68 |     );
  69 | 
  70 |     // Cleanup imported requirements
  71 |     for (const req of importedReqs) {
  72 |       await request.delete(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
  73 |         headers: { Authorization: `Bearer ${token}` },
  74 |       });
  75 |     }
  76 | 
  77 |     // Cleanup temp file
  78 |     fs.unlinkSync(csvPath);
  79 |   });
  80 | 
  81 |   test('[REQ-L0-013] import button visible in requirements toolbar', async ({ page }) => {
  82 |     await page.goto(`${FRONTEND_URL}/requirements`);
  83 |     await expect(page.locator('[data-testid="csv-import-toolbar-btn"]')).toBeVisible({ timeout: 10000 });
  84 |   });
  85 | 
  86 |   test('[REQ-L0-013] import button visible in settings', async ({ page }) => {
  87 |     await page.goto(`${FRONTEND_URL}/settings`);
  88 |     // Settings page should have a CSV import button in data management section
  89 |     await expect(page.locator('[data-testid="settings-csv-import-btn"]')).toBeVisible({ timeout: 10000 });
  90 |   });
  91 | });
  92 | 
```