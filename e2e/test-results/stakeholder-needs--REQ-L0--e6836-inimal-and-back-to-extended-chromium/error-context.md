# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: stakeholder-needs.spec.ts >> [REQ-L0-002] Scalable SE depth — preset switcher >> [REQ-L0-002] can switch preset to minimal and back to extended
- Location: tests\stakeholder-needs.spec.ts:47:7

# Error details

```
Error: expect(locator).toBeChecked() failed

Locator:  locator('[data-testid="preset-option-minimal"]')
Expected: checked
Received: unchecked
Timeout:  5000ms

Call log:
  - Expect "toBeChecked" with timeout 5000ms
  - waiting for locator('[data-testid="preset-option-minimal"]')
    14 × locator resolved to <input type="radio" name="preset" value="minimal" data-testid="preset-option-minimal"/>
       - unexpected value "unchecked"

```

```yaml
- 'radio "minimal Baselines: ✗ | change_reason: optional | Basic (Draft/Approved)"'
```

# Test source

```ts
  1   | // L0 Stakeholder Needs — E2E coverage for REQ-L0-001 through REQ-L0-012
  2   | import { test, expect } from '@playwright/test';
  3   | import {
  4   |   loginAsAdmin,
  5   |   getAuthToken,
  6   |   setWorkspaceId,
  7   |   setWorkspacePreset,
  8   |   SEEDED_WORKSPACE_ID,
  9   | } from '../helpers/auth';
  10  | 
  11  | const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';
  12  | const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
  13  | 
  14  | // ---------------------------------------------------------------------------
  15  | // REQ-L0-001 — MCP Server endpoint exists
  16  | // ---------------------------------------------------------------------------
  17  | test.describe('[REQ-L0-001] MCP Server', () => {
  18  |   test('[REQ-L0-001] MCP endpoint exists (not 404)', async ({ request }) => {
  19  |     const token = await getAuthToken();
  20  |     const response = await request.get(`${BACKEND_URL}/mcp/`, {
  21  |       headers: { Authorization: `Bearer ${token}` },
  22  |     });
  23  |     // 200 (SSE stream) or 405 (method not allowed) both confirm the endpoint exists
  24  |     expect([200, 405, 400]).toContain(response.status());
  25  |   });
  26  | });
  27  | 
  28  | // ---------------------------------------------------------------------------
  29  | // REQ-L0-002 — Skalierbare SE-Tiefe: Preset-Wechsel in Workspace Settings
  30  | // ---------------------------------------------------------------------------
  31  | test.describe('[REQ-L0-002] Scalable SE depth — preset switcher', () => {
  32  |   test.beforeEach(async ({ page }) => {
  33  |     await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
  34  |     await loginAsAdmin(page);
  35  |   });
  36  | 
  37  |   test('[REQ-L0-002] preset selector has at least 3 options (radio buttons)', async ({ page }) => {
  38  |     await page.goto(`${FRONTEND_URL}/workspace-settings`);
  39  |     const selectorContainer = page.locator('[data-testid="preset-selector"]');
  40  |     await expect(selectorContainer).toBeVisible({ timeout: 10000 });
  41  |     // Preset is rendered as radio buttons with data-testid="preset-option-<name>"
  42  |     const radioOptions = selectorContainer.locator('input[type="radio"]');
  43  |     const count = await radioOptions.count();
  44  |     expect(count).toBeGreaterThanOrEqual(3);
  45  |   });
  46  | 
  47  |   test('[REQ-L0-002] can switch preset to minimal and back to extended', async ({ page }) => {
  48  |     await page.goto(`${FRONTEND_URL}/workspace-settings`);
  49  |     await expect(page.locator('[data-testid="preset-selector"]')).toBeVisible({ timeout: 10000 });
  50  | 
  51  |     // Preset is radio buttons — click the minimal radio
  52  |     const minimalRadio = page.locator('[data-testid="preset-option-minimal"]');
  53  |     await expect(minimalRadio).toBeVisible({ timeout: 6000 });
  54  |     await minimalRadio.click();
  55  |     await page.waitForLoadState('networkidle');
> 56  |     await expect(minimalRadio).toBeChecked({ timeout: 5000 });
      |                                ^ Error: expect(locator).toBeChecked() failed
  57  | 
  58  |     // Switch back to extended
  59  |     const extendedRadio = page.locator('[data-testid="preset-option-extended"]');
  60  |     await extendedRadio.click();
  61  |     await page.waitForLoadState('networkidle');
  62  |     await expect(extendedRadio).toBeChecked({ timeout: 5000 });
  63  |   });
  64  | });
  65  | 
  66  | // ---------------------------------------------------------------------------
  67  | // REQ-L0-003 — Vollständige Traceability: TraceLink anlegen via UI
  68  | // ---------------------------------------------------------------------------
  69  | test.describe('[REQ-L0-003] Traceability — create TraceLink via UI', () => {
  70  |   test.beforeEach(async ({ page }) => {
  71  |     await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
  72  |     await loginAsAdmin(page);
  73  |   });
  74  | 
  75  |   test('[REQ-L0-003] create TraceLink button opens creation form', async ({ page }) => {
  76  |     await page.goto(`${FRONTEND_URL}/traceability`);
  77  |     const createBtn = page.locator('[data-testid="tracelink-create-btn"]');
  78  |     await expect(createBtn).toBeVisible({ timeout: 10000 });
  79  |     await createBtn.click();
  80  |     await expect(page.locator('[data-testid="tracelink-create-form"]')).toBeVisible({ timeout: 8000 });
  81  |   });
  82  | 
  83  |   test('[REQ-L0-003] TraceLink creation form source and target dropdowns are populated', async ({ page }) => {
  84  |     await page.goto(`${FRONTEND_URL}/traceability`);
  85  |     const createBtn = page.locator('[data-testid="tracelink-create-btn"]');
  86  |     await expect(createBtn).toBeVisible({ timeout: 10000 });
  87  |     await createBtn.click();
  88  |     await expect(page.locator('[data-testid="tracelink-create-form"]')).toBeVisible({ timeout: 8000 });
  89  | 
  90  |     const sourceSelect = page.locator('[data-testid="tracelink-source-select"]');
  91  |     const targetSelect = page.locator('[data-testid="tracelink-target-select"]');
  92  |     await expect(sourceSelect).toBeVisible({ timeout: 6000 });
  93  |     await expect(targetSelect).toBeVisible({ timeout: 6000 });
  94  | 
  95  |     // Count non-placeholder options
  96  |     const sourceOptions = await sourceSelect.locator('option').count();
  97  |     const targetOptions = await targetSelect.locator('option').count();
  98  | 
  99  |     if (sourceOptions <= 1 || targetOptions <= 1) {
  100 |       // No artifacts seeded — graceful skip
  101 |       test.skip(true, 'Dropdowns empty — no artifacts seeded for this workspace');
  102 |     }
  103 |     expect(sourceOptions).toBeGreaterThan(1);
  104 |     expect(targetOptions).toBeGreaterThan(1);
  105 |   });
  106 | });
  107 | 
  108 | // ---------------------------------------------------------------------------
  109 | // REQ-L0-004 — Baselines anlegen via UI
  110 | // ---------------------------------------------------------------------------
  111 | test.describe('[REQ-L0-004] Baselines — create via UI', () => {
  112 |   test.beforeEach(async ({ page }) => {
  113 |     await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
  114 |     await loginAsAdmin(page);
  115 |   });
  116 | 
  117 |   test('[REQ-L0-004] create baseline form appears on button click', async ({ page }) => {
  118 |     await page.goto(`${FRONTEND_URL}/baselines`);
  119 |     await expect(page.locator('[data-testid="baselines-view"]')).toBeVisible({ timeout: 15000 });
  120 |     const createBtn = page.locator('[data-testid="create-baseline-btn"]');
  121 |     await expect(createBtn).toBeVisible({ timeout: 10000 });
  122 |     await createBtn.click();
  123 |     // Inline form appears (no dialog — toggled by showForm state)
  124 |     await expect(page.locator('[data-testid="create-baseline-form"]')).toBeVisible({ timeout: 6000 });
  125 |   });
  126 | 
  127 |   test('[REQ-L0-004] baseline creation form has artifact select and scope input', async ({ page }) => {
  128 |     await page.goto(`${FRONTEND_URL}/baselines`);
  129 |     await expect(page.locator('[data-testid="baselines-view"]')).toBeVisible({ timeout: 15000 });
  130 |     await page.locator('[data-testid="create-baseline-btn"]').click();
  131 |     await expect(page.locator('[data-testid="create-baseline-form"]')).toBeVisible({ timeout: 6000 });
  132 | 
  133 |     // Artifact select must be present
  134 |     await expect(page.locator('[data-testid="baseline-artifact-select"]')).toBeVisible({ timeout: 5000 });
  135 |     // Scope input must be present
  136 |     await expect(page.locator('[data-testid="baseline-scope-input"]')).toBeVisible({ timeout: 5000 });
  137 |     // Submit button must be present
  138 |     await expect(page.locator('[data-testid="baseline-submit-btn"]')).toBeVisible({ timeout: 5000 });
  139 |   });
  140 | });
  141 | 
  142 | // ---------------------------------------------------------------------------
  143 | // REQ-L0-005 — Konfigurierbarer Lifecycle: workflow states in req editor
  144 | // ---------------------------------------------------------------------------
  145 | test.describe('[REQ-L0-005] Configurable lifecycle — workflow states', () => {
  146 |   test.beforeEach(async ({ page }) => {
  147 |     await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
  148 |     await loginAsAdmin(page);
  149 |   });
  150 | 
  151 |   test('[REQ-L0-005] req-workflow selector exists with draft / review / approved options', async ({ page }) => {
  152 |     await page.goto(`${FRONTEND_URL}/requirements`);
  153 |     await page.locator('[data-testid="create-req-btn"]').click();
  154 |     const workflow = page.locator('[data-testid="req-workflow"]');
  155 |     await expect(workflow).toBeVisible({ timeout: 12000 });
  156 |     const options = await workflow.locator('option').allTextContents();
```