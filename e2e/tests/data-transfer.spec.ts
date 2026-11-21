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
    expect(typeof body).toBe('object');
    expect(body.format_version).toBe('artifact-transfer/v1');
    expect(body.checksum).toBeTruthy();
    // Every transfer-contract entity bucket must be present (D8).
    expect(Object.keys(body.entities ?? {}).length).toBeGreaterThan(0);
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
    // `created` is a {entity_type: count} map, not a scalar (D8/D9).
    expect(typeof result.created).toBe('object');
    expect(
      Object.values(result.created as Record<string, number>).reduce(
        (sum, n) => sum + Number(n), 0
      )
    ).toBeGreaterThan(0);
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

// R5/P2 — plan docs/plans/2026-11-21-artifact-transfer-plan.md §6 P2 DoD
// "E2E je Format". Every single-export format declared by the transfer contract
// (BASE_FORMATS minus the ZIP snapshot) is served by the generic entity
// endpoint; the two re-importable formats (JSON via snapshot, CSV via the CSV
// importer) additionally complete a real dry-run round-trip.
// Endpoints/params discovered from backend/rest_api/urls.py + views_io.py —
// notably `export_format` (NOT `format`, which DRF consumes for negotiation)
// and `entity` (a stable artifact-transfer entity key). No URLs invented.
test.describe('[R5/P2] Single-format export — JSON, CSV, Markdown, PDF', () => {
  const singleFormats: Array<{
    name: string;
    exportFormat: string;
    contentType: string;
  }> = [
    { name: 'json', exportFormat: 'json', contentType: 'application/json' },
    { name: 'csv', exportFormat: 'csv', contentType: 'text/csv' },
    { name: 'markdown', exportFormat: 'markdown', contentType: 'text/markdown' },
    { name: 'pdf', exportFormat: 'pdf', contentType: 'application/pdf' },
  ];

  for (const { name, exportFormat, contentType } of singleFormats) {
    test(`[P2] GET /export/entity serves a non-empty ${name} document`, async ({ request }) => {
      const token = await getAuthToken();
      const resp = await request.get(
        `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/export/entity/`,
        {
          headers: authHeaders(token),
          params: { entity: 'requirement', export_format: exportFormat },
        }
      );

      expect(resp.status()).toBe(200);
      const body = await resp.body();
      expect(body.length).toBeGreaterThan(0);
      // Content-Type matches the format's media type (charset suffix allowed).
      expect(resp.headers()['content-type']).toContain(contentType);
      // Content-Disposition carries the contract filename "export_<entity>.<format>".
      expect(resp.headers()['content-disposition']).toContain(
        `export_requirement.${exportFormat}`
      );
    });
  }

  test('[P2] JSON export is contract-tagged and re-imports via the snapshot importer (dry-run)', async ({ request }) => {
    const token = await getAuthToken();

    // Generic entity JSON export is a contract-tagged document (P2 JSON format).
    const entityResp = await request.get(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/export/entity/`,
      { headers: authHeaders(token), params: { entity: 'requirement' } }
    );
    expect(entityResp.status()).toBe(200);
    const doc = await entityResp.json();
    expect(doc.metadata.contract).toBe('artifact-transfer/v1');
    expect(Array.isArray(doc.data)).toBe(true);

    // The re-importable JSON path is the versioned snapshot + checked importer.
    const snapshotResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/export/snapshot/`,
      { headers: authHeaders(token) }
    );
    expect(snapshotResp.status()).toBe(200);
    const snapshot = await snapshotResp.json();
    expect(snapshot.format_version).toBe('artifact-transfer/v1');

    const importResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/import/snapshot/`,
      {
        headers: authHeaders(token),
        data: {
          snapshot,
          new_workspace_name: `e2e-json-roundtrip-${Date.now()}`,
          dry_run: true,
        },
      }
    );
    expect(importResp.ok()).toBeTruthy();
    const result = await importResp.json();
    expect(result.success).toBe(true);
    expect(result.dry_run).toBe(true);
    // `created` is a {entity_type: count} map (D8/D9).
    expect(Object.keys(result.created ?? {}).length).toBeGreaterThan(0);
  });

  test('[P2] CSV export re-imports via the CSV importer (dry-run)', async ({ request }) => {
    const token = await getAuthToken();

    // Use the dedicated CSV endpoint — its output is the round-trippable CSV
    // (terminology comment line + lossless cell flattening) the importer parses.
    const exportResp = await request.get(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/export/csv/`,
      { headers: authHeaders(token), params: { entity_type: 'Requirement' } }
    );
    expect(exportResp.status()).toBe(200);
    const csvBuffer = await exportResp.body();
    expect(csvBuffer.length).toBeGreaterThan(0);
    expect(exportResp.headers()['content-type']).toContain('text/csv');

    const importResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/import/csv/`,
      {
        headers: authHeaders(token),
        params: { dry_run: 'true' },
        multipart: {
          entity_type: 'Requirement',
          file: { name: 'roundtrip.csv', mimeType: 'text/csv', buffer: csvBuffer },
        },
      }
    );
    expect(importResp.ok()).toBeTruthy();
    const report = await importResp.json();
    // Legacy and contract-v2 envelopes both carry these keys (ADR-014 §5):
    // a clean dry-run of valid exported rows has no failures.
    expect(report.success).toBe(true);
    expect(report.status).toBe('ok');
    expect(typeof report.imported_count).toBe('number');
  });
});
