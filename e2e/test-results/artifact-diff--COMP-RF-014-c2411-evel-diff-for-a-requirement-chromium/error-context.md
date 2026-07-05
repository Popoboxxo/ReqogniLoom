# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: artifact-diff.spec.ts >> [COMP-RF-014] ArtifactDiff >> [REQ-L1-040] diff view opens and shows field-level diff for a requirement
- Location: tests\artifact-diff.spec.ts:14:7

# Error details

```
Test timeout of 10000ms exceeded.
```

```
Error: locator.click: Test timeout of 10000ms exceeded.
Call log:
  - waiting for locator('[data-testid="create-req-btn"]')
    - locator resolved to <button data-testid="create-req-btn">+ New</button>
  - attempting click action
    - waiting for element to be visible, enabled and stable
  - element was detached from the DOM, retrying

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
  1   | // REQ-L1-040, REQ-L2-RF-014: Artifact Diff — visual diff view
  2   | // Create a requirement, modify it, open diff view, assert changed field visible
  3   | import { test, expect } from '@playwright/test';
  4   | import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
  5   | 
  6   | const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
  7   | 
  8   | test.describe('[COMP-RF-014] ArtifactDiff', () => {
  9   |   test.beforeEach(async ({ page }) => {
  10  |     await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
  11  |     await loginAsAdmin(page);
  12  |   });
  13  | 
  14  |   test('[REQ-L1-040] diff view opens and shows field-level diff for a requirement', async ({ page }) => {
  15  |     test.setTimeout(10000);
  16  | 
  17  |     // Navigate to requirements and create a new one
  18  |     await page.goto(`${FRONTEND_URL}/requirements`);
> 19  |     await page.locator('[data-testid="create-req-btn"]').click();
      |                                                          ^ Error: locator.click: Test timeout of 10000ms exceeded.
  20  |     await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 10000 });
  21  | 
  22  |     // Fill in initial data
  23  |     const titleInput = page.locator('[data-testid="req-title"]');
  24  |     await titleInput.fill('Diff Test Requirement');
  25  | 
  26  |     // Save the requirement
  27  |     await page.locator('[data-testid="save-btn"]').click();
  28  |     // Wait for save to complete (button text returns from "Saving..." to "Save")
  29  |     await expect(page.locator('[data-testid="save-btn"]')).toContainText('Save', { timeout: 10000 });
  30  |     // Small delay for state stabilization
  31  |     await page.waitForTimeout(1000);
  32  | 
  33  |     // Now modify the title
  34  |     await titleInput.fill('Diff Test Requirement - Modified');
  35  | 
  36  |     // Save again to create a new version
  37  |     await page.locator('[data-testid="save-btn"]').click();
  38  |     await expect(page.locator('[data-testid="save-btn"]')).toContainText('Save', { timeout: 10000 });
  39  |     await page.waitForTimeout(1000);
  40  | 
  41  |     // Click the "View Diff" button
  42  |     const viewDiffBtn = page.locator('[data-testid="view-diff-btn"]');
  43  |     await expect(viewDiffBtn).toBeVisible({ timeout: 10000 });
  44  |     await viewDiffBtn.click();
  45  | 
  46  |     // The diff view should appear
  47  |     const diffView = page.locator('[data-testid="artifact-diff-view"]');
  48  |     await expect(diffView).toBeVisible({ timeout: 10000 });
  49  | 
  50  |     // Version selectors should be present
  51  |     const versionSelectors = page.locator('[data-testid="diff-version-selectors"]');
  52  |     await expect(versionSelectors).toBeVisible({ timeout: 4000 });
  53  | 
  54  |     // The from-version dropdown should be visible
  55  |     const fromVersionSelect = page.locator('[data-testid="diff-from-version"]');
  56  |     await expect(fromVersionSelect).toBeVisible({ timeout: 4000 });
  57  | 
  58  |     // The to-version dropdown should be visible
  59  |     const toVersionSelect = page.locator('[data-testid="diff-to-version"]');
  60  |     await expect(toVersionSelect).toBeVisible({ timeout: 4000 });
  61  | 
  62  |     // Diff fields should be rendered
  63  |     const diffFields = page.locator('[data-testid="diff-fields"]');
  64  |     await expect(diffFields).toBeVisible({ timeout: 10000 });
  65  | 
  66  |     // Close button should work
  67  |     const closeBtn = page.locator('[data-testid="diff-close-btn"]');
  68  |     await expect(closeBtn).toBeVisible({ timeout: 4000 });
  69  |     await closeBtn.click();
  70  | 
  71  |     // Diff view should be hidden
  72  |     await expect(diffView).not.toBeVisible({ timeout: 4000 });
  73  |   });
  74  | 
  75  |   test('[REQ-L2-RF-014] diff view shows version 0 baseline as all fields added', async ({ page }) => {
  76  |     test.setTimeout(10000);
  77  | 
  78  |     // Navigate to requirements and create a new one
  79  |     await page.goto(`${FRONTEND_URL}/requirements`);
  80  |     await page.locator('[data-testid="create-req-btn"]').click();
  81  |     await expect(page.locator('[data-testid="req-title"]')).toBeVisible({ timeout: 10000 });
  82  | 
  83  |     // Fill in data and save
  84  |     await page.locator('[data-testid="req-title"]').fill('Baseline Diff Test');
  85  |     await page.locator('[data-testid="save-btn"]').click();
  86  |     await expect(page.locator('[data-testid="save-btn"]')).toContainText('Save', { timeout: 10000 });
  87  |     await page.waitForTimeout(1000);
  88  | 
  89  |     // Open diff view
  90  |     const viewDiffBtn = page.locator('[data-testid="view-diff-btn"]');
  91  |     await expect(viewDiffBtn).toBeVisible({ timeout: 10000 });
  92  |     await viewDiffBtn.click();
  93  | 
  94  |     const diffView = page.locator('[data-testid="artifact-diff-view"]');
  95  |     await expect(diffView).toBeVisible({ timeout: 10000 });
  96  | 
  97  |     // Select from_version=0 (Creation baseline)
  98  |     const fromSelect = page.locator('[data-testid="diff-from-version"]');
  99  |     await fromSelect.selectOption({ value: '0' });
  100 | 
  101 |     // Wait for diff to load
  102 |     const diffFields = page.locator('[data-testid="diff-fields"]');
  103 |     await expect(diffFields).toBeVisible({ timeout: 10000 });
  104 | 
  105 |     // All fields should show "Added" status when comparing from baseline
  106 |     // (since version 0 has no data, all current fields are "added")
  107 |     const addedBadges = diffFields.locator('text=Added');
  108 |     // At least the title field should be marked as added
  109 |     await expect(addedBadges.first()).toBeVisible({ timeout: 10000 });
  110 |   });
  111 | });
  112 | 
```