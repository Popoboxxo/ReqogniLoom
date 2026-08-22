// REQ-L0-013, REQ-L2-RF-016: CSV Bulk Import E2E
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';
import path from 'path';
import fs from 'fs';
import os from 'os';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

// Sample CSV content for testing
const SAMPLE_CSV = `title,description,category,status
E2E Import Req 1,First imported requirement,functional,draft
E2E Import Req 2,Second imported requirement,non-functional,draft
E2E Import Req 3,Third imported requirement,functional,draft
`;

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
    // Create a temporary CSV file
    const tmpDir = os.tmpdir();
    const csvPath = path.join(tmpDir, 'e2e-import-test.csv');
    fs.writeFileSync(csvPath, SAMPLE_CSV, 'utf-8');

    // Get auth token for API verification
    const token = await getAuthToken();

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

    // Wait for success result
    await expect(page.locator('[data-testid="csv-import-success"]')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="csv-import-success"]')).toContainText('3');

    // Cleanup: verify requirements were created via API and delete them
    const listResp = await request.get(`${BACKEND_URL}/api/v1/requirements/?workspace_id=${SEEDED_WORKSPACE_ID}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(listResp.ok()).toBeTruthy();
    const listBody = await listResp.json();
    const importedReqs = (listBody.results || []).filter(
      (r: { title: string }) => r.title?.startsWith('E2E Import Req')
    );

    // Cleanup imported requirements
    for (const req of importedReqs) {
      await request.delete(`${BACKEND_URL}/api/v1/requirements/${req.id}/`, {
        headers: { Authorization: `Bearer ${token}` },
      });
    }

    // Cleanup temp file
    fs.unlinkSync(csvPath);
  });

  test('[REQ-L0-013] import button visible in requirements toolbar', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/requirements`);
    await expect(page.locator('[data-testid="csv-import-toolbar-btn"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L0-013] import button visible in settings', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/settings`);
    // Settings page should have a CSV import button in data management section
    await expect(page.locator('[data-testid="settings-csv-import-btn"]')).toBeVisible({ timeout: 10000 });
  });
});
