// W1 / INT-01: CsvImport UI outcome contract.
//
// W1 changed `frontend/src/api/import.ts` + `CsvImport.tsx` so the UI consumes
// the ADR-014 import *result envelope* instead of collapsing every non-2xx into
// an opaque error, and renders the `idempotent_replay` notice. The existing
// `csv-import.spec.ts` only covers the CSV success path; this spec adds the
// branches W1 touched:
//
//   * CSV per-row validation failure -> the `rejected` outcome with the
//     per-row error report (a real 400, no mock),
//   * ReqIF file-level PARSE_ERROR -> the v2 422 result envelope rendered as a
//     result (not as `reqif-import-error`),
//   * ReqIF Idempotency-Key replay -> the replay badge on the second import.
//
// The two ReqIF branches depend on `IMPORT_CONTRACT_V2`, which since the
// 2026-10-04 amendment (ADR-014 §5 Phase 2 / D2b) is ON by default;
// `IMPORT_CONTRACT_V2=false` is the rollback switch back to the legacy
// contract. When the running backend answers the legacy contract they are
// skipped with the exact flag to check (never silently passed) — see
// `importContractV2Active`.
import { test, expect, type APIRequestContext } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  setWorkspaceId,
  createIsolatedWorkspace,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';
import path from 'path';
import fs from 'fs';
import os from 'os';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

const INVALID_CSV = `title,description,category
,Missing title,functional
`;

const MALFORMED_REQIF = '<not-a-valid-reqif><unclosed>';

const IMPORT_CONTRACT_HINT =
  'IMPORT_CONTRACT_V2 is off on the running backend (rollback switch, ADR-014 §5). ' +
  'Set IMPORT_CONTRACT_V2=true and recreate the backend, then re-run this spec.';

/**
 * Probe the live backend for the ADR-014 v2 contract.
 *
 * ADR-014 §2 answers a file-level PARSE_ERROR with HTTP 422 + `contract:"v2"`.
 * The legacy path answers 400 with the generic `{error: ...}` envelope, which
 * the UI correctly treats as a transport error. The probe changes nothing
 * (a parse failure persists no row and claims no idempotency key).
 */
async function importContractV2Active(
  request: APIRequestContext,
  token: string
): Promise<boolean> {
  const response = await request.post(
    `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/import/reqif/`,
    {
      headers: { Authorization: `Bearer ${token}` },
      multipart: {
        file: {
          name: 'e2e-contract-probe.reqif',
          mimeType: 'application/xml',
          buffer: Buffer.from(MALFORMED_REQIF),
        },
      },
    }
  );
  if (response.status() !== 422) return false;
  const body = await response.json();
  return body.contract === 'v2';
}

function writeTempFile(name: string, content: string | Buffer): string {
  const filePath = path.join(os.tmpdir(), name);
  fs.writeFileSync(filePath, content);
  return filePath;
}

test.describe('[INT-01] Import outcome contract', () => {
  test('[INT-01] CSV validation failure renders the rejected outcome, not an opaque error', async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);

    const csvPath = writeTempFile('e2e-w1-invalid.csv', INVALID_CSV);
    try {
      await page.goto(`${FRONTEND_URL}/import`);
      await expect(page.locator('[data-testid="csv-import-page"]')).toBeVisible({ timeout: 10000 });

      await page.locator('[data-testid="csv-file-input"]').setInputFiles(csvPath);
      await page.locator('[data-testid="csv-import-btn"]').click();

      const result = page.locator('[data-testid="csv-import-result"]');
      await expect(result).toBeVisible({ timeout: 10000 });
      // A backend 400 that carries a full ImportResult is a *rejected import*,
      // not the generic `csv-import-error` box.
      await expect(result).toHaveAttribute('data-outcome', 'rejected');
      await expect(page.locator('[data-testid="csv-import-failed"]')).toBeVisible();
      await expect(page.locator('[data-testid="csv-import-atomicity-note"]')).toBeVisible();
      await expect(page.locator('[data-testid="csv-import-error-list"]')).toBeVisible();
      await expect(page.locator('[data-testid="csv-import-success"]')).toHaveCount(0);
    } finally {
      fs.unlinkSync(csvPath);
    }
  });

  test('[INT-01] ReqIF file-level parse error is rendered as a v2 result envelope', async ({ page, request }) => {
    const token = await getAuthToken();
    test.skip(
      !(await importContractV2Active(request, token)),
      `Cannot exercise the ReqIF 422 result envelope: ${IMPORT_CONTRACT_HINT}`
    );

    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);

    const reqifPath = writeTempFile('e2e-w1-broken.reqif', MALFORMED_REQIF);
    try {
      await page.goto(`${FRONTEND_URL}/import`);
      await expect(page.locator('[data-testid="reqif-import-page"]')).toBeVisible({ timeout: 10000 });

      await page.locator('[data-testid="reqif-file-input"]').setInputFiles(reqifPath);
      await page.locator('[data-testid="reqif-import-btn"]').click();

      // ADR-014 §1: a 422 carrying the result envelope is a *result*, so the UI
      // must render `reqif-import-result` and not the opaque error box.
      await expect(page.locator('[data-testid="reqif-import-result"]')).toBeVisible({ timeout: 10000 });
      await expect(page.locator('[data-testid="reqif-import-error"]')).toHaveCount(0);

      const counts = page.locator('[data-testid="reqif-import-counts"]');
      await expect(counts).toBeVisible();
      await expect(counts).toContainText(/failed:\s*1|fehlgeschlagen:\s*1/);
    } finally {
      fs.unlinkSync(reqifPath);
    }
  });

  test('[INT-01] ReqIF Idempotency-Key replay shows the replay badge on the second import', async ({ page, request }) => {
    const token = await getAuthToken();
    test.skip(
      !(await importContractV2Active(request, token)),
      `Cannot exercise the ReqIF idempotent replay: ${IMPORT_CONTRACT_HINT}`
    );

    // Real ReqIF document: exported from the seeded workspace via the public
    // export endpoint (no fixture, no mock).
    const exportResp = await request.get(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/export/reqif/`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(exportResp.ok()).toBeTruthy();
    const reqifPath = writeTempFile('e2e-w1-replay.reqif', await exportResp.body());

    // Import into a fresh, empty workspace so the first call is a real write;
    // the UI keeps one Idempotency-Key per selected file, so clicking import a
    // second time must be served from the replay store.
    const targetWorkspaceId = await createIsolatedWorkspace(token, 'e2e-w1-reqif-replay');
    await setWorkspaceId(page, targetWorkspaceId);
    await loginAsAdmin(page);

    try {
      await page.goto(`${FRONTEND_URL}/import`);
      await expect(page.locator('[data-testid="reqif-import-page"]')).toBeVisible({ timeout: 10000 });
      await page.locator('[data-testid="reqif-file-input"]').setInputFiles(reqifPath);

      const importBtn = page.locator('[data-testid="reqif-import-btn"]');
      await importBtn.click();
      await expect(page.locator('[data-testid="reqif-import-result"]')).toBeVisible({ timeout: 30000 });
      await expect(page.locator('[data-testid="reqif-import-replay-badge"]')).toHaveCount(0);

      await importBtn.click();
      await expect(page.locator('[data-testid="reqif-import-replay-badge"]')).toBeVisible({ timeout: 30000 });
    } finally {
      fs.unlinkSync(reqifPath);
    }
  });
});
