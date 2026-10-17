// REQ-L0-013, REQ-L2-RF-016: CSV Bulk Import E2E
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
import path from 'path';
import fs from 'fs';
import os from 'os';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

// Sample CSV content for testing.
//
// Issue #1342: the importer dedupes on the requirement title (natural key), and
// this spec used to import the fixed titles "E2E Import Req 1..3". When an
// earlier run failed before its API cleanup ran, those rows stayed in the
// seeded workspace and every later run imported *nothing*: all three rows came
// back as `skipped` / `DUPLICATE`, the UI correctly rendered
// "0 Zeilen erfolgreich importiert", and the spec failed with an assertion
// that looked like an importer regression. Titles are now unique per run; the
// shared prefix keeps the cleanup filter working (and also sweeps rows left
// behind by older runs).
const CSV_TITLE_PREFIX = 'E2E Import Req';

function buildSampleCsv(runId: string): string {
  return `title,description,category,status
${CSV_TITLE_PREFIX} ${runId}-1,First imported requirement,functional,draft
${CSV_TITLE_PREFIX} ${runId}-2,Second imported requirement,non-functional,draft
${CSV_TITLE_PREFIX} ${runId}-3,Third imported requirement,functional,draft
`;
}

test.describe('CSV Import', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L0-013] import page loads', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/import`);
    await expect(page.locator('[data-testid="csv-import-page"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="csv-import-btn"]')).toBeVisible();
  });

  test('[REQ-L0-013] csv import creates requirements', async ({ page, request }) => {
    // Unique per run: see the CSV_TITLE_PREFIX comment above (issue #1342).
    const runId = `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;

    // Create a temporary CSV file
    const tmpDir = os.tmpdir();
    const csvPath = path.join(tmpDir, 'e2e-import-test.csv');
    fs.writeFileSync(csvPath, buildSampleCsv(runId), 'utf-8');

    // Get auth token for API verification
    const token = await getAuthToken();

    try {
      // Navigate to import page
      await page.goto(`${FRONTEND_URL}/import`);
      await expect(page.locator('[data-testid="csv-import-page"]')).toBeVisible({ timeout: 10000 });

      // Select entity type (Requirement is default)
      await expect(page.locator('[data-testid="entity-type-Requirement"]')).toBeChecked();

      // Upload file
      const fileInput = page.locator('[data-testid="csv-file-input"]');
      await fileInput.setInputFiles(csvPath);

      // Verify file is shown
      await expect(page.locator('[data-testid="csv-drop-zone"]')).toContainText('e2e-import-test.csv');

      // Click import button
      await page.locator('[data-testid="csv-import-btn"]').click();

      // Wait for success result. `imported_count` must be 3 - not just any
      // digit in the box: a duplicate-only import renders "0 ... importiert"
      // and is exactly the failure mode of #1342.
      const success = page.locator('[data-testid="csv-import-success"]');
      await expect(success).toBeVisible({ timeout: 10000 });
      await expect(success).toContainText(/3\b/);
    } finally {
      // Cleanup runs even when an assertion above fails, so a red run cannot
      // leave the duplicate titles behind for the *next* run (#1342).
      fs.unlinkSync(csvPath);
      try {
        const listResp = await request.get(
          `${BACKEND_URL}/api/v1/requirements/?workspace_id=${SEEDED_WORKSPACE_ID}&page_size=100`,
          { headers: { Authorization: `Bearer ${token}` } }
        );
        if (listResp.ok()) {
          const listBody = await listResp.json();
          const importedReqs = (listBody.results || []).filter(
            (r: { title: string }) => r.title?.startsWith(CSV_TITLE_PREFIX)
          );
          for (const req of importedReqs) {
            await request.delete(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
              headers: { Authorization: `Bearer ${token}` },
            });
          }
        }
      } catch (err) {
        // Best-effort: a cleanup failure must never mask the assertion result.
        console.warn(`csv-import cleanup failed: ${(err as Error).message}`);
      }
    }
  });

  test('[REQ-L0-013] import button visible in requirements toolbar', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);

    // UI-consistency P1: CSV import is a rare action and now lives in the page
    // header's "⋯" overflow menu (UI concept ch. 12.1), so it is not mounted
    // until the menu is opened — same as PDF export, see pdf-export.spec.ts.
    const overflowTrigger = page.locator('[data-testid="page-header-overflow-trigger"]');
    await expect(overflowTrigger).toBeVisible({ timeout: 10000 });
    await overflowTrigger.click();

    await expect(page.locator('[data-testid="csv-import-toolbar-btn"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L0-013] import button visible in settings', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/settings`);
    // Settings page should have a CSV import button in data management section
    await expect(page.locator('[data-testid="settings-csv-import-btn"]')).toBeVisible({ timeout: 10000 });
  });
});
