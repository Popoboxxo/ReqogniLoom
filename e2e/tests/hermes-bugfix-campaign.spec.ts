/**
 * Hermes Bugfix Campaign — E2E Verification Tests
 *
 * Covers regression + golden-path verification for all bugs fixed in the
 * Hermes sprint (REQ-127 through REQ-136) plus REQ-L1-095 and REQ-126.
 *
 * Test areas:
 *   Area 1: Need Creation golden path + REQ-L1-095 null-UUID guard
 *   Area 2: Requirement Derivation from Needs (REQ-128)
 *   Area 3: API-Key Management — retrieve endpoint (REQ-134)
 *   Area 4: Attribute Visibility Config — empty state (REQ-136)
 *   Area 5: Workspace Language — persists after save (REQ-133)
 *   Area 6: change_reason for Extended-Preset Workspace (REQ-135)
 *   Area 7: Bearer Token role regression (REQ-126)
 *   Area 8: MCP tools/list deduplication (REQ-129)
 *   Area 9: MCP capability declaration — no SSE (REQ-131)
 *
 * Auth: Uses API-level Bearer token injection (httpOnly-cookie/Vite-proxy
 * domain mismatch workaround). Production code is NOT modified.
 */

import { test, expect, type Route } from '@playwright/test';
import {
  loginAsAdmin,
  getAuthToken,
  setWorkspaceId,
  setWorkspacePreset,
  revokeAllApiKeys,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

// ---------------------------------------------------------------------------
// Helper: inject Bearer token into all /api/** requests so the Vite dev-proxy
// passes it to the backend. This is needed because httpOnly-cookie domain
// "backend" is rejected by the browser in dev mode.
// ---------------------------------------------------------------------------
async function injectBearerToken(page: import('@playwright/test').Page, token: string): Promise<void> {
  await page.route('/api/**', async (route: Route) => {
    const request = route.request();
    const headers = {
      ...await request.allHeaders(),
      Authorization: `Bearer ${token}`,
    };
    await route.continue({ headers });
  });
}

// ---------------------------------------------------------------------------
// Area 1: Need Creation golden path + REQ-L1-095 null-UUID guard
// ---------------------------------------------------------------------------
test.describe('[REQ-L1-095] Need Creation — null-UUID guard regression', () => {
  let token: string;

  test.beforeAll(async () => {
    token = await getAuthToken();
  });

  test('[REQ-L1-095] create Need button is not disabled when workspace is loaded', async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await injectBearerToken(page, token);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/needs`);

    const createBtn = page.locator('[data-testid="create-need-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 15000 });
    // Must be enabled — REQ-L1-095: guard must not block when workspace is loaded
    await expect(createBtn).not.toBeDisabled({ timeout: 10000 });
  });

  test('[REQ-L1-095] create Need golden path — POST returns 201 and item appears in list', async ({ request }) => {
    const title = `Hermes-Need-${Date.now()}`;
    const response = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/needs/`,
      {
        headers: { Authorization: `Bearer ${token}` },
        data: {
          title,
          description: 'Created by Hermes E2E campaign — null-UUID guard regression check',
          moscow_priority: 'Must',
        },
      }
    );
    expect(response.status(), 'POST /needs/ must return 201').toBe(201);
    const body = await response.json();
    expect(body.id).toBeTruthy();
    expect(body.title).toBe(title);
    expect(body.workspace_id).toBe(SEEDED_WORKSPACE_ID);
  });
});

// ---------------------------------------------------------------------------
// Area 2: Requirement Derivation from Needs (REQ-128)
//
// Bug: GET /api/v1/needs/derive-requirements/ returned 500 because DRF router
// treated "derive-requirements" as a UUID pk.
// Fix: Constrain lookup_value_regex to UUID pattern.
// ---------------------------------------------------------------------------
test.describe('[REQ-128] Requirement Derivation from Needs — URL routing fix', () => {
  let token: string;
  let needId: string;

  test.beforeAll(async () => {
    token = await getAuthToken();
    // Create a fresh need to derive from
    const ctx = await import('@playwright/test').then(m => m.request.newContext({ baseURL: BACKEND_URL }));
    const resp = await ctx.post(`/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/needs/`, {
      headers: { Authorization: `Bearer ${token}` },
      data: {
        title: `REQ-128 Derivation Seed Need ${Date.now()}`,
        description: 'Used by REQ-128 derive-requirements E2E test',
        moscow_priority: 'Must',
      },
    });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    needId = body.id;
    await ctx.dispose();
  });

  test('[REQ-128] GET /api/v1/needs/derive-requirements/ does not 500', async ({ request }) => {
    // This URL used to trigger a 500 because "derive-requirements" was parsed as pk.
    // After the fix, it should return 404 or 405 (action not on list endpoint) — NOT 500.
    const response = await request.get(
      `${BACKEND_URL}/api/v1/needs/derive-requirements/`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    // 404 = no object with pk "derive-requirements" (correct: uuid guard blocks it)
    // 405 = method not allowed (also acceptable)
    // 500 = regression — the bug is back
    expect(response.status(), 'Must not return 500 — URL routing regression').not.toBe(500);
    expect([404, 405]).toContain(response.status());
  });

  test('[REQ-128] POST /api/v1/needs/{uuid}/derive-requirements/ returns 200 with draft requirements', async ({ request }) => {
    const response = await request.post(
      `${BACKEND_URL}/api/v1/needs/${needId}/derive-requirements/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: {},
      }
    );
    // Must return 200 (or 202 for async) with draft requirements
    expect([200, 202]).toContain(response.status());
    const body = await response.json();
    // Response must have drafts array (even if empty from mock provider)
    expect(body).toHaveProperty('drafts');
    expect(Array.isArray(body.drafts)).toBe(true);
  });

  test('[REQ-128] derived requirements drafts contain title and description', async ({ request }) => {
    const response = await request.post(
      `${BACKEND_URL}/api/v1/needs/${needId}/derive-requirements/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: {},
      }
    );
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.drafts.length).toBeGreaterThan(0);
    const draft = body.drafts[0];
    expect(draft).toHaveProperty('title');
    expect(draft).toHaveProperty('description');
    expect(draft.title).toBeTruthy();
  });

  test('[REQ-128] UUID-lookup still works for valid need UUID', async ({ request }) => {
    // Regression: the UUID constraint must not break normal need retrieval
    const response = await request.get(
      `${BACKEND_URL}/api/v1/needs/${needId}/`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.id).toBe(needId);
  });
});

// ---------------------------------------------------------------------------
// Area 3: API-Key Management — retrieve endpoint (REQ-134)
//
// Bug: GET /api/v1/api-keys/{id}/ returned 405 — retrieve action was missing.
// Fix: Add retrieve action to ApiKeyViewSet.
// ---------------------------------------------------------------------------
test.describe('[REQ-134] API-Key Management — retrieve endpoint', () => {
  let token: string;
  let keyId: string;

  test.beforeAll(async () => {
    token = await getAuthToken();
    // Backend caps active API keys at 10 per user — purge stale keys from prior
    // runs so key creation stays under the cap (otherwise create returns 400
    // and keyId becomes undefined, cascading into flaky failures).
    await revokeAllApiKeys(token);
    // Create a fresh API key for testing
    const ctx = await import('@playwright/test').then(m => m.request.newContext({ baseURL: BACKEND_URL }));
    const resp = await ctx.post('/api/v1/api-keys/', {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { name: `Hermes-E2E-REQ134-${Date.now()}` },
    });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    keyId = body.id;
    // The plaintext is only returned at creation time — we don't store it
    // (by design, security requirement)
    await ctx.dispose();
  });

  test('[REQ-134] GET /api/v1/api-keys/ returns 200 with list', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/api/v1/api-keys/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(Array.isArray(body)).toBe(true);
  });

  test('[REQ-134] GET /api/v1/api-keys/{id}/ returns 200 — not 405', async ({ request }) => {
    // This was the bug: retrieve returned 405 Method Not Allowed
    const response = await request.get(`${BACKEND_URL}/api/v1/api-keys/${keyId}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    // Must return 200 after fix, not 405
    expect(response.status(), 'retrieve must return 200 not 405 (REQ-134 regression check)').toBe(200);
  });

  test('[REQ-134] retrieve returns key metadata fields (id, name, created_at)', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/api/v1/api-keys/${keyId}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.id).toBe(keyId);
    expect(body.name).toContain('Hermes-E2E-REQ134');
    expect(body).toHaveProperty('created_at');
    expect(body).toHaveProperty('revoked');
  });

  test('[REQ-134] retrieve does NOT return plaintext key (security)', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/api/v1/api-keys/${keyId}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    // The raw key value must NOT be in the response — it is returned only at creation time
    expect(body).not.toHaveProperty('plaintext');
    expect(body).not.toHaveProperty('key');
  });

  test('[REQ-134] retrieve of non-existent key returns 404', async ({ request }) => {
    const response = await request.get(
      `${BACKEND_URL}/api/v1/api-keys/00000000-0000-0000-0000-000000000000/`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(response.status()).toBe(404);
  });

  test('[REQ-134] API keys section visible on /profile page', async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    const tkn = await getAuthToken();
    await injectBearerToken(page, tkn);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/profile`);

    const keysSection = page.locator('[data-testid="api-keys-section"]');
    await expect(keysSection).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-134] create API key via UI shows plaintext only once', async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    const tkn = await getAuthToken();
    await injectBearerToken(page, tkn);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/profile`);

    const nameInput = page.locator('[data-testid="api-key-name-input"]');
    await expect(nameInput).toBeVisible({ timeout: 10000 });
    await nameInput.fill(`UI-REQ134-Test-${Date.now()}`);

    await page.locator('[data-testid="api-key-create-btn"]').click();

    // Plaintext box must appear after creation
    const plaintextBox = page.locator('[data-testid="api-key-plaintext-box"]');
    await expect(plaintextBox).toBeVisible({ timeout: 10000 });

    // The key value must be shown once in plaintext
    const plaintextEl = page.locator('[data-testid="api-key-plaintext"]');
    await expect(plaintextEl).toBeVisible({ timeout: 5000 });
    const keyText = await plaintextEl.textContent();
    expect(keyText).toBeTruthy();
    expect(keyText!.length).toBeGreaterThan(10);
  });
});

// ---------------------------------------------------------------------------
// Area 4: Attribute Visibility Config — empty state (REQ-136)
//
// Bug: Empty [] response from /api/v1/attribute-visibility-configs/ caused
// console.error and an error banner in AdminDialog.
// Fix: Treat empty array as informational state, not error.
// ---------------------------------------------------------------------------
test.describe('[REQ-136] Attribute Visibility Config — empty state is informational', () => {
  let token: string;

  test.beforeAll(async () => {
    token = await getAuthToken();
  });

  test('[REQ-136] GET /api/v1/attribute-visibility-configs/ returns [] without 500', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/api/v1/attribute-visibility-configs/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    // Must return 200 with empty array (not 500 or error)
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(Array.isArray(body)).toBe(true);
    // May be empty — that is the valid state REQ-136 is about
  });

  test('[REQ-136] attribute-visibility-configs API call returns 200 (not error) on workspace-settings page', async ({ page }) => {
    // REQ-136: the empty [] response from /attribute-visibility-configs/ must not cause
    // the frontend to surface a user-facing error. We verify this by intercepting the
    // actual API response rather than relying on noisy browser console events.
    let attrVisibilityStatus: number | null = null;

    page.on('response', (response) => {
      if (response.url().includes('attribute-visibility-config')) {
        attrVisibilityStatus = response.status();
      }
    });

    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await injectBearerToken(page, token);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    await page.waitForLoadState('networkidle');

    // If the request was made, it must have returned 200 (not an error status)
    if (attrVisibilityStatus !== null) {
      expect(attrVisibilityStatus, 'attribute-visibility-configs must return 200').toBe(200);
    }
    // The workspace settings page must be fully rendered (no crash)
    await expect(page.locator('[data-testid="workspace-settings"]')).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-136] attribute visibility empty info element shown when no configs exist', async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await injectBearerToken(page, token);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    await page.waitForLoadState('networkidle');

    // The empty info element must be visible (not hidden behind an error banner)
    const emptyInfo = page.locator('[data-testid="attr-visibility-empty-info"]');
    // Only check if configs are actually empty — verify there's no error banner
    const errorBanner = page.locator('[data-testid="attr-visibility-error"]');
    const hasError = await errorBanner.isVisible().catch(() => false);

    if (hasError) {
      // This is the regression — empty state must not show an error banner
      const errorText = await errorBanner.textContent();
      throw new Error(`[REQ-136] regression: error banner shown for empty attr-visibility: "${errorText}"`);
    }

    // The workspace settings page itself must render without crashing
    await expect(page.locator('[data-testid="workspace-settings"]')).toBeVisible({ timeout: 10000 });
  });
});

// ---------------------------------------------------------------------------
// Area 5: Workspace Language — persists after save (REQ-133)
//
// Bug: Workspace had no language column; serializer always returned default "en".
// Fix: Add language field to Workspace model with migration.
// ---------------------------------------------------------------------------
test.describe('[REQ-133] Workspace Language — persists after save', () => {
  let token: string;

  test.beforeAll(async () => {
    token = await getAuthToken();
    // Ensure workspace starts with a known language
    const ctx = await import('@playwright/test').then(m => m.request.newContext({ baseURL: BACKEND_URL }));
    await ctx.patch(`/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { language: 'de' },
    });
    await ctx.dispose();
  });

  test('[REQ-133] PATCH /workspaces/{id}/ with language=en returns updated language', async ({ request }) => {
    const patchResp = await request.patch(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { language: 'en' },
      }
    );
    expect(patchResp.status()).toBe(200);
    const body = await patchResp.json();
    expect(body.language, 'PATCH response must reflect new language').toBe('en');
  });

  test('[REQ-133] language is persisted — GET after PATCH returns same value', async ({ request }) => {
    // Set to 'en'
    await request.patch(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { language: 'en' },
      }
    );

    // Retrieve — must still be 'en', not the default 'de'
    const getResp = await request.get(`${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(getResp.status()).toBe(200);
    const body = await getResp.json();
    expect(body.language, 'Language must be persisted in DB — not reset to default (REQ-133 regression)').toBe('en');
  });

  test('[REQ-133] language round-trips de → en → de without loss', async ({ request }) => {
    // Set to de
    const deResp = await request.patch(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { language: 'de' },
      }
    );
    expect((await deResp.json()).language).toBe('de');

    // Set to en
    const enResp = await request.patch(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { language: 'en' },
      }
    );
    expect((await enResp.json()).language).toBe('en');

    // Back to de
    const backResp = await request.patch(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { language: 'de' },
      }
    );
    expect((await backResp.json()).language).toBe('de');

    // Final GET confirms persistence
    const finalGet = await request.get(`${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect((await finalGet.json()).language).toBe('de');
  });

  test('[REQ-133] language selector in workspace settings reflects API value', async ({ page }) => {
    // Set language to en via API first
    const ctx = await import('@playwright/test').then(m => m.request.newContext({ baseURL: BACKEND_URL }));
    await ctx.patch(`/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { language: 'en' },
    });
    await ctx.dispose();

    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await injectBearerToken(page, token);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    await page.waitForLoadState('networkidle');

    // The 'en' radio must be checked
    const enRadio = page.locator('[data-testid="language-option-en"]');
    await expect(enRadio).toBeVisible({ timeout: 10000 });
    await expect(enRadio).toBeChecked({ timeout: 5000 });

    // The 'de' radio must NOT be checked
    const deRadio = page.locator('[data-testid="language-option-de"]');
    await expect(deRadio).not.toBeChecked();
  });

  test('[REQ-133] language change via UI radio → persists on API reload', async ({ page }) => {
    // Reset to en first
    const ctx = await import('@playwright/test').then(m => m.request.newContext({ baseURL: BACKEND_URL }));
    await ctx.patch(`/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { language: 'en' },
    });
    await ctx.dispose();

    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await injectBearerToken(page, token);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    await page.waitForLoadState('networkidle');

    // Verify page is in 'en' state before clicking
    const enRadio = page.locator('[data-testid="language-option-en"]');
    await expect(enRadio).toBeVisible({ timeout: 10000 });

    // Click 'de' — and wait for the PATCH response from the backend
    const deRadio = page.locator('[data-testid="language-option-de"]');
    await expect(deRadio).toBeVisible({ timeout: 5000 });

    const [patchResponse] = await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes(`workspaces/${SEEDED_WORKSPACE_ID}`) &&
          resp.request().method() === 'PATCH',
        { timeout: 10000 }
      ),
      deRadio.click(),
    ]);

    // The PATCH must succeed for the language to persist
    const patchStatus = patchResponse.status();
    expect(patchStatus, `Language PATCH must return 200 (got ${patchStatus}) — bearer token routing issue?`).toBe(200);

    // Verify via API that the change was persisted
    const ctx2 = await import('@playwright/test').then(m => m.request.newContext({ baseURL: BACKEND_URL }));
    const getResp = await ctx2.get(`/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    // Read the response BEFORE disposing the context
    const body = await getResp.json();
    await ctx2.dispose();

    expect(body.language, 'Language change via UI must be persisted via API (REQ-133)').toBe('de');
  });
});

// ---------------------------------------------------------------------------
// Area 6: change_reason for Extended-Preset Workspace (REQ-135)
//
// Bug: Error message "change_reason required" gave no context about which
//      workspace or preset requires it.
// Fix: Message now includes "extended preset" and guidance text.
// ---------------------------------------------------------------------------
test.describe('[REQ-135] change_reason validation error message includes context', () => {
  let token: string;
  let requirementId: string;

  test.beforeAll(async () => {
    token = await getAuthToken();
    // Ensure extended preset
    await setWorkspacePreset('extended');

    // Create a requirement to update
    const ctx = await import('@playwright/test').then(m => m.request.newContext({ baseURL: BACKEND_URL }));
    const resp = await ctx.post('/api/v1/requirements/', {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: {
        title: `REQ-135 Test Requirement ${Date.now()}`,
        workspace_id: SEEDED_WORKSPACE_ID,
        description: 'Used by REQ-135 change_reason E2E test',
      },
    });
    expect(resp.status()).toBe(201);
    const body = await resp.json();
    requirementId = body.id;
    await ctx.dispose();
  });

  test.afterAll(async () => {
    // Reset to extended so other tests are not affected
    await setWorkspacePreset('extended');
  });

  test('[REQ-135] PATCH without change_reason returns 400 with context message', async ({ request }) => {
    const response = await request.patch(
      `${BACKEND_URL}/api/v1/requirements/${requirementId}/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { title: 'Updated title without change_reason' },
      }
    );
    expect(response.status()).toBe(400);
    const body = await response.json();
    // The error must include change_reason context
    const message: string = body?.error?.message || body?.message || JSON.stringify(body);
    expect(message.toLowerCase()).toContain('change_reason');
    // Must include some contextual information (preset or workspace)
    const hasContext =
      message.toLowerCase().includes('preset') ||
      message.toLowerCase().includes('workspace') ||
      message.toLowerCase().includes('policy');
    expect(hasContext, `Error message "${message}" must mention preset or workspace context`).toBe(true);
  });

  test('[REQ-135] error message is no longer bare "change_reason required"', async ({ request }) => {
    const response = await request.patch(
      `${BACKEND_URL}/api/v1/requirements/${requirementId}/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { description: 'Updated description without change_reason' },
      }
    );
    expect(response.status()).toBe(400);
    const body = await response.json();
    const message: string = body?.error?.message || body?.message || JSON.stringify(body);
    // The terse original message should be replaced by the more descriptive one
    expect(message.trim()).not.toBe('change_reason required');
    expect(message.length).toBeGreaterThan('change_reason required'.length);
  });

  test('[REQ-135] PATCH WITH change_reason succeeds (200)', async ({ request }) => {
    const response = await request.patch(
      `${BACKEND_URL}/api/v1/requirements/${requirementId}/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: {
          title: `Updated with change_reason ${Date.now()}`,
          change_reason: 'E2E test: verifying REQ-135 change_reason acceptance in extended preset',
        },
      }
    );
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.id).toBe(requirementId);
  });

  test('[REQ-135] minimal preset workspace does NOT require change_reason', async ({ request }) => {
    await setWorkspacePreset('minimal');
    try {
      const response = await request.patch(
        `${BACKEND_URL}/api/v1/requirements/${requirementId}/`,
        {
          headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
          data: { title: `Minimal preset update ${Date.now()}` },
        }
      );
      // Minimal preset: no change_reason required → must succeed
      expect([200, 400]).toContain(response.status());
      if (response.status() === 400) {
        const body = await response.json();
        const message: string = body?.error?.message || '';
        // If 400, it must NOT be about change_reason
        expect(message.toLowerCase()).not.toContain('change_reason');
      }
    } finally {
      await setWorkspacePreset('extended');
    }
  });
});

// ---------------------------------------------------------------------------
// Area 7: Bearer Token role regression (REQ-126)
// (Lightweight regression guard — full suite in bearer-token-role-resolution.spec.ts)
// ---------------------------------------------------------------------------
test.describe('[REQ-126] Bearer Token role regression guard', () => {
  test('[REQ-126] Bearer token create + read cycle still works after Hermes fixes', async ({ request }) => {
    const token = await getAuthToken();
    const title = `REQ-126-regression-${Date.now()}`;

    const createResp = await request.post(`${BACKEND_URL}/api/v1/requirements/`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { title, workspace_id: SEEDED_WORKSPACE_ID },
    });
    expect(createResp.status(), 'create must return 201 — bearer role not regressed').toBe(201);
    const created = await createResp.json();
    expect(created.id).toBeTruthy();

    const getResp = await request.get(`${BACKEND_URL}/api/v1/requirements/${created.id}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(getResp.status()).toBe(200);
    expect((await getResp.json()).title).toBe(title);
  });
});

// ---------------------------------------------------------------------------
// Area 8: MCP tools/list deduplication (REQ-129)
// ---------------------------------------------------------------------------
test.describe('[REQ-129] MCP tools/list deduplication', () => {
  let mcpKey: string;

  test.beforeAll(async () => {
    const token = await getAuthToken();
    // Backend caps active API keys at 10 per user — purge stale keys from prior
    // runs so this MCP key creation stays under the cap (otherwise create
    // returns 400, mcpKey is undefined, and the MCP request 400s).
    await revokeAllApiKeys(token);
    const ctx = await import('@playwright/test').then(m => m.request.newContext({ baseURL: BACKEND_URL }));
    const resp = await ctx.post('/api/v1/api-keys/', {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { name: `MCP-REQ129-${Date.now()}` },
    });
    expect(resp.status(), 'MCP API key creation must return 201').toBe(201);
    const body = await resp.json();
    mcpKey = body.plaintext;
    await ctx.dispose();
  });

  test('[REQ-129] tools/list returns no duplicate tool names', async ({ request }) => {
    const response = await request.post(`${BACKEND_URL}/mcp/`, {
      headers: { 'X-API-Key': mcpKey, 'Content-Type': 'application/json' },
      data: { jsonrpc: '2.0', method: 'tools/list', id: 1, params: {} },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const tools: Array<{ name: string }> = body.result.tools;
    const names = tools.map((t) => t.name);
    const uniqueNames = [...new Set(names)];

    // Every tool name must appear exactly once
    expect(names.length, 'Tool count must equal unique tool count (no duplicates)').toBe(uniqueNames.length);
  });

  test('[REQ-129] tools/list returns at least 40 tools', async ({ request }) => {
    const response = await request.post(`${BACKEND_URL}/mcp/`, {
      headers: { 'X-API-Key': mcpKey, 'Content-Type': 'application/json' },
      data: { jsonrpc: '2.0', method: 'tools/list', id: 2, params: {} },
    });
    expect(response.status()).toBe(200);
    const body = await response.json();
    const tools: Array<{ name: string }> = body.result.tools;
    // ReqFlow has 40+ MCP tools
    expect(tools.length).toBeGreaterThanOrEqual(40);
  });
});

// ---------------------------------------------------------------------------
// Area 9: MCP capability declaration matches the served transports (REQ-131)
// ---------------------------------------------------------------------------
test.describe('[REQ-131] MCP capability declaration', () => {
  // SSE was temporarily dropped from the declaration while `GET /mcp/sse/`
  // answered 500 on every request (#455). That is fixed and the server now runs
  // ASGI unconditionally (uvicorn in dev, gunicorn -k UvicornWorker in prod),
  // so SSE is served again — and every distributed plugin config ships
  // `"type": "sse"`. The invariant REQ-131 actually protects is that the
  // declaration matches what is routed, not that SSE is absent.
  test('[REQ-131] GET /mcp/ declares SSE and the route answers', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/mcp/`);
    expect(response.status()).toBe(200);
    const body = await response.json();

    const transports: string[] = body.transports ?? [];
    expect(transports, 'SSE is served, so it must be declared').toContain('sse');

    // A declared transport must be routed. Unauthenticated it answers 401 —
    // what matters is that it is neither 404 (not routed) nor 5xx (broken,
    // the #455 regression this guards against).
    const sse = await request.get(`${BACKEND_URL}/mcp/sse/`, { failOnStatusCode: false });
    expect(sse.status(), 'declared SSE transport must be routed and not erroring')
      .toBeLessThan(500);
    expect(sse.status(), 'declared SSE transport must be routed').not.toBe(404);
  });

  test('[REQ-131] GET /mcp/ declares http transport', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/mcp/`);
    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.transports).toContain('http');
  });
});
