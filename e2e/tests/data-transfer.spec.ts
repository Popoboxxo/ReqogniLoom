// P8 — Datenübernahme: Snapshot export/copy, ReqIF round-trip, checked restore.
import { test, expect } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

function authHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

test.describe('[P8/D18] Datenübernahme page', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('renders export, import and restore panels', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/data-transfer`);

    await expect(page.getByTestId('data-transfer-page')).toBeVisible({ timeout: 10000 });
    await expect(page.getByTestId('snapshot-export-button')).toBeVisible();
    await expect(page.getByTestId('snapshot-import-file')).toBeVisible();
    await expect(page.getByTestId('restore-button')).toBeVisible();
  });

  test('[D14b] snapshot export returns a versioned document', async ({ request }) => {
    const token = await getAuthToken();
    const resp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/export/snapshot/`,
      { headers: authHeaders(token) }
    );
    expect(resp.ok()).toBeTruthy();
    const body = await resp.json();
    expect(body).toBeTruthy();
    expect(typeof body).toBe('object');
    expect(body.entities || body.workspace).toBeTruthy();
  });

  test('[D9/D12b] snapshot dry-run import copies into a new workspace without writes', async ({ request }) => {
    const token = await getAuthToken();
    const exportResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/export/snapshot/`,
      { headers: authHeaders(token) }
    );
    expect(exportResp.ok()).toBeTruthy();
    const snapshot = await exportResp.json();

    const copyName = `e2e-copy-${Date.now()}`;
    const dryResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/import/snapshot/`,
      {
        headers: authHeaders(token),
        data: { snapshot, new_workspace_name: copyName, dry_run: true },
      }
    );
    expect(dryResp.ok()).toBeTruthy();
    const result = await dryResp.json();
    expect(result.dry_run).toBe(true);
    expect(result.created).toBeGreaterThanOrEqual(0);
  });

  test('[D14d] ReqIF export -> dry-run import round-trip', async ({ request }) => {
    const token = await getAuthToken();
    const exportResp = await request.get(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/export/reqif/`,
      { headers: authHeaders(token) }
    );
    expect(exportResp.ok()).toBeTruthy();
    const xml = await exportResp.body();
    expect(xml.length).toBeGreaterThan(0);

    const multipart = {
      file: {
        name: 'roundtrip.reqif',
        mimeType: 'application/xml',
        buffer: xml,
      },
    };
    const importResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/import/reqif/?dry_run=true`,
      { headers: authHeaders(token), multipart }
    );
    expect(importResp.ok()).toBeTruthy();
    const result = await importResp.json();
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(true);
  });

  test('[D17] admin restore dry-run returns a checked plan; wrong captcha is refused', async ({ request }) => {
    const token = await getAuthToken();

    const wrong = await request.post(`${BACKEND_URL}/api/v1/admin/restore/`, {
      headers: authHeaders(token),
      data: { backup_id: '00000000-0000-0000-0000-000000000000', confirmation_text: 'WRONG' },
    });
    expect(wrong.status()).toBe(400);

    const backupResp = await request.post(`${BACKEND_URL}/api/v1/admin/backups/`, {
      headers: authHeaders(token),
      data: { backup_type: 'full' },
    });
    expect(backupResp.ok()).toBeTruthy();
    const backup = (await backupResp.json()).backup;
    expect(backup?.id).toBeTruthy();

    const dry = await request.post(`${BACKEND_URL}/api/v1/admin/restore/`, {
      headers: authHeaders(token),
      data: { backup_id: backup.id, confirmation_text: 'RESTORE', dry_run: true },
    });
    expect(dry.ok()).toBeTruthy();
    const report = (await dry.json()).restore;
    expect(report.dry_run).toBe(true);
    expect(report.format_version).toBeTruthy();
    expect(report.plan).toBeTruthy();
    expect(report.plan.loaddata).toBe(false);
  });
});
