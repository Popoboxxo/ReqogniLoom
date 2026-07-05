# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: architecture-editor.spec.ts >> [COMP-RF-004] ArchitectureEditors >> [REQ-L3-RF004-002] description field with markdown preview toggle is present
- Location: tests\architecture-editor.spec.ts:40:7

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
  - paragraph: Select an architecture element from the list.
```

# Test source

```ts
  1  | // REQ-L2-RF-004, REQ-L3-RF004-001/002/003: Architecture editor (CRUD, markdown, linked reqs)
  2  | import { test, expect } from '@playwright/test';
  3  | import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
  4  | 
  5  | const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
  6  | 
  7  | test.describe('[COMP-RF-004] ArchitectureEditors', () => {
  8  |   test.beforeEach(async ({ page }) => {
  9  |     await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
  10 |     await loginAsAdmin(page);
  11 |   });
  12 | 
  13 |   test('[REQ-L3-RF004-001] element-type dropdown and delete confirmation dialog work', async ({ page }) => {
  14 |     await page.goto(`${FRONTEND_URL}/architecture`);
  15 |     await page.locator('[data-testid="create-arch-btn"]').click();
  16 |     await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
  17 | 
  18 |     // Element-type dropdown is visible with the 5 ADR-L3-RF-007 options
  19 |     const typeSelect = page.locator('[data-testid="arch-element-type-select"]');
  20 |     await expect(typeSelect).toBeVisible();
  21 |     const options = await typeSelect.locator('option').allTextContents();
  22 |     expect(options).toEqual(
  23 |       expect.arrayContaining(['Component', 'Interface', 'Subsystem', 'Layer', 'Module'])
  24 |     );
  25 | 
  26 |     // Delete button is visible
  27 |     const deleteBtn = page.locator('[data-testid="arch-delete-btn"]');
  28 |     await expect(deleteBtn).toBeVisible();
  29 | 
  30 |     // Clicking delete must show the confirmation dialog
  31 |     await deleteBtn.click();
  32 |     await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 4000 });
  33 |     await expect(page.locator('[data-testid="confirm-delete-btn"]')).toBeVisible();
  34 | 
  35 |     // Cancel the dialog so we don't leave dangling state
  36 |     await page.locator('[role="dialog"] button', { hasText: /cancel|abbrechen/i }).click();
  37 |     await expect(page.locator('[role="dialog"]')).toBeHidden({ timeout: 4000 });
  38 |   });
  39 | 
  40 |   test('[REQ-L3-RF004-002] description field with markdown preview toggle is present', async ({ page }) => {
  41 |     await page.goto(`${FRONTEND_URL}/architecture`);
  42 |     await page.locator('[data-testid="create-arch-btn"]').click();
> 43 |     await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
     |                                                              ^ Error: expect(locator).toBeVisible() failed
  44 | 
  45 |     // Markdown toggle controls exist for the description field
  46 |     const previewBtn = page.locator('[data-testid="md-preview-btn"]').first();
  47 |     const editBtn = page.locator('[data-testid="md-edit-btn"]').first();
  48 |     await expect(previewBtn).toBeVisible();
  49 |     await expect(editBtn).toBeVisible();
  50 | 
  51 |     // Edit mode reveals a textarea
  52 |     await editBtn.click();
  53 |     await expect(page.locator('textarea').first()).toBeVisible({ timeout: 4000 });
  54 |   });
  55 | 
  56 |   test('[REQ-L3-RF004-003] linked-requirements sidebar is rendered (empty state ok)', async ({ page }) => {
  57 |     await page.goto(`${FRONTEND_URL}/architecture`);
  58 |     await page.locator('[data-testid="create-arch-btn"]').click();
  59 |     await expect(page.locator('[data-testid="arch-title"]')).toBeVisible({ timeout: 10000 });
  60 | 
  61 |     // Linked-requirements panel must be rendered
  62 |     const panel = page.locator('[data-testid="arch-linked-reqs-panel"]');
  63 |     await expect(panel).toBeVisible({ timeout: 6000 });
  64 | 
  65 |     // Either has linked items list OR shows "none" message — both are valid
  66 |     const panelText = await panel.innerText();
  67 |     expect(panelText.length).toBeGreaterThan(0);
  68 |   });
  69 | });
  70 | 
```