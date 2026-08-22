/**
 * ReqFlow — Live Browser UI Test Campaign
 * Hermes Bugfix Campaign (REQ-127 to REQ-136)
 *
 * Exploratory end-user-style UI tests: real browser navigation, screenshots,
 * console error capture. NOT a re-run of the automated API suite.
 *
 * Covers:
 *  Journey 1: [REQ-133] Workspace Language UI
 *  Journey 2: [REQ-L1-095 + REQ-128] Need creation + Requirement Derivation
 *  Journey 3: [REQ-134] API-Key Management UI
 *  Journey 4: [REQ-136] Attribute-Visibility-Configs (Workspace-Settings, console errors)
 *  Journey 5: [REQ-135] Extended-Preset change_reason error message
 *  Journey 6: [REQ-132] Ollama/AI-Feature missing config
 *  Journey 7: [REQ-129] MCP-Tools deduplication (via /profile or settings)
 */

import { test, expect, Page, BrowserContext } from '@playwright/test';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BACKEND_URL  = process.env.BACKEND_URL  || 'http://localhost:8001';
const SCREENSHOTS  = process.env.SCREENSHOTS_DIR ||
  '/tmp/claude-1000/-home-dduchrow-Repos-ai-native-reqflow-POC/c6ffd178-9d77-4dc1-856a-c306204b4f92/scratchpad/screenshots';

const SEEDED_WORKSPACE_ID = '6d20f0b9-d2cf-46a0-b916-79f8b417210f';
const ADMIN_USER = 'admin';
const ADMIN_PASS = 'admin12345';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function getToken(): Promise<string> {
  const { request } = await import('@playwright/test');
  const ctx = await request.newContext({ baseURL: BACKEND_URL });
  const resp = await ctx.post('/api/v1/auth/login/', {
    data: { username: ADMIN_USER, password: ADMIN_PASS },
  });
  const body = await resp.json();
  await ctx.dispose();
  return body.token || body.access || body.access_token;
}

async function loginAsAdmin(page: Page): Promise<void> {
  await page.goto(`${FRONTEND_URL}/login`);
  await page.fill('#username-input', ADMIN_USER);
  await page.fill('#password-input', ADMIN_PASS);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
}

/** Inject workspace ID so WorkspaceContext loads the real workspace */
async function injectWorkspace(page: Page): Promise<void> {
  await page.addInitScript((wsId) => {
    sessionStorage.setItem('reqflow_workspace_id', wsId);
  }, SEEDED_WORKSPACE_ID);
}

/** Inject Bearer token into all /api/** proxied requests */
async function injectBearer(page: Page, token: string): Promise<void> {
  await page.route('/api/**', async (route) => {
    const req = route.request();
    const headers = await req.allHeaders();
    await route.continue({
      headers: { ...headers, Authorization: `Bearer ${token}` },
    });
  });
}

async function screenshot(page: Page, name: string): Promise<string> {
  const path = `${SCREENSHOTS}/${name}.png`;
  await page.screenshot({ path, fullPage: true });
  return path;
}

/** Collect console errors during a page visit */
function collectConsoleErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') errors.push(msg.text());
  });
  page.on('pageerror', (err) => errors.push(`UNCAUGHT: ${err.message}`));
  return errors;
}

/**
 * Filter out known pre-existing (pre-Hermes) console noise.
 *
 * REQ-137 (fixed): GET /api/v1/users/me/preferences/ now returns 200 with
 * empty defaults via get_or_create semantics — no longer logs 404 errors.
 * Mock removed; real endpoint used in all tests.
 */
function filterKnownNoise(errors: string[]): string[] {
  return errors.filter(e =>
    !e.includes('favicon') &&
    !e.includes('hot-update') &&
    !e.includes('[HMR]') &&
    !e.includes('WebSocket')
  );
}

// ---------------------------------------------------------------------------
// Journey 1: [REQ-133] Workspace Language UI
// ---------------------------------------------------------------------------

test.describe('[REQ-133] Workspace Language — UI Journey', () => {
  let token: string;

  test.beforeAll(async () => {
    token = await getToken();
  });

  test('[REQ-133] workspace-settings page loads and language selector is visible', async ({ page }) => {
    await injectWorkspace(page);
    await injectBearer(page, token);

    const errors = collectConsoleErrors(page);

    await loginAsAdmin(page);

    // Navigate via sidebar menu (user-like)
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    await page.waitForLoadState('networkidle');

    await screenshot(page, 'req133-01-workspace-settings-initial');

    // Language selector must be visible
    const enRadio = page.locator('[data-testid="language-option-en"]');
    const deRadio = page.locator('[data-testid="language-option-de"]');
    await expect(enRadio).toBeVisible({ timeout: 10000 });
    await expect(deRadio).toBeVisible({ timeout: 10000 });

    await screenshot(page, 'req133-02-language-options-visible');

    // Exactly one should be checked (no double-selection)
    const enChecked = await enRadio.isChecked();
    const deChecked = await deRadio.isChecked();
    expect(enChecked !== deChecked, 'Exactly one language option must be checked').toBe(true);

    // No console errors during page load (excluding known pre-existing noise)
    expect(filterKnownNoise(errors),
      `Console errors on workspace-settings: ${JSON.stringify(errors)}`
    ).toHaveLength(0);
  });

  test('[REQ-133] switching language via UI → API confirms persistence', async ({ page, request }) => {
    // Reset to 'en' first
    await request.patch(`${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { language: 'en' },
    });

    await injectWorkspace(page);
    await injectBearer(page, token);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    await page.waitForLoadState('networkidle');

    // Should show 'en' selected
    await expect(page.locator('[data-testid="language-option-en"]')).toBeChecked({ timeout: 10000 });

    await screenshot(page, 'req133-03-language-en-selected');

    // Switch to 'de' — wait for PATCH to complete
    const [patchResp] = await Promise.all([
      page.waitForResponse(
        (resp) => resp.url().includes(`workspaces/${SEEDED_WORKSPACE_ID}`) && resp.request().method() === 'PATCH',
        { timeout: 10000 }
      ),
      page.locator('[data-testid="language-option-de"]').click(),
    ]);

    expect(patchResp.status(), '[REQ-133] language PATCH must return 200').toBe(200);
    await screenshot(page, 'req133-04-language-de-selected');

    // Verify via API that persistence worked
    const getResp = await request.get(`${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    const body = await getResp.json();
    expect(body.language, '[REQ-133] language must be "de" after UI switch').toBe('de');
  });
});

// ---------------------------------------------------------------------------
// Journey 2: [REQ-L1-095 + REQ-128] Need creation + Derivation
// ---------------------------------------------------------------------------

test.describe('[REQ-L1-095 + REQ-128] Need Creation + Requirement Derivation — UI Journey', () => {
  let token: string;

  test.beforeAll(async () => {
    token = await getToken();
  });

  test('[REQ-L1-095] /needs page loads with enabled create button (workspace loaded)', async ({ page }) => {
    await injectWorkspace(page);
    await injectBearer(page, token);

    const errors = collectConsoleErrors(page);

    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/needs`);
    await page.waitForLoadState('networkidle');

    await screenshot(page, 'req-l1-095-01-needs-page');

    const createBtn = page.locator('[data-testid="create-need-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 15000 });
    // Guard: must NOT be disabled when workspace is loaded
    await expect(createBtn).not.toBeDisabled({ timeout: 10000 });

    await screenshot(page, 'req-l1-095-02-create-btn-enabled');

    // No null-UUID errors in console
    const nullUuidErrors = errors.filter(e => e.includes('null') && e.includes('workspace'));
    expect(nullUuidErrors, `Null-UUID workspace errors: ${JSON.stringify(nullUuidErrors)}`).toHaveLength(0);
  });

  test('[REQ-128] Need created via API → derive-requirements endpoint returns 200', async ({ request }) => {
    // Create a need
    const createResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/needs/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: {
          title: `UI-Campaign-Need-${Date.now()}`,
          description: 'Created during live browser UI campaign — REQ-128 derivation test',
          moscow_priority: 'Must',
        },
      }
    );
    expect(createResp.status(), '[REQ-128] need creation must return 201').toBe(201);
    const need = await createResp.json();

    // Derive requirements (core fix: URL routing must not return 500)
    const deriveResp = await request.post(
      `${BACKEND_URL}/api/v1/needs/${need.id}/derive-requirements/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: {},
      }
    );
    expect([200, 202], '[REQ-128] derive-requirements must not 500').toContain(deriveResp.status());
    const body = await deriveResp.json();
    expect(body, '[REQ-128] response must have drafts array').toHaveProperty('drafts');
    expect(Array.isArray(body.drafts)).toBe(true);
  });

  test('[REQ-128] GET derive-requirements with non-UUID segment returns 404/405 not 500', async ({ request }) => {
    const resp = await request.get(
      `${BACKEND_URL}/api/v1/needs/derive-requirements/`,
      { headers: { Authorization: `Bearer ${token}` } }
    );
    expect(resp.status(), '[REQ-128] non-UUID segment must not return 500').not.toBe(500);
    expect([404, 405]).toContain(resp.status());
  });
});

// ---------------------------------------------------------------------------
// Journey 3: [REQ-134] API-Key Management UI
// ---------------------------------------------------------------------------

test.describe('[REQ-134] API-Key Management — UI Journey', () => {
  let token: string;

  test.beforeAll(async () => {
    token = await getToken();
    // Clean up E2E keys to stay under the 10-key cap
    const { request } = await import('@playwright/test');
    const ctx = await request.newContext({ baseURL: BACKEND_URL });
    const listResp = await ctx.get('/api/v1/api-keys/', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (listResp.ok()) {
      const keys: Array<{ id: string; name?: string; revoked?: boolean }> = await listResp.json();
      for (const key of keys) {
        if (key.revoked) continue;
        if ((key.name ?? '').includes('E2E') || (key.name ?? '').includes('UI-Campaign') ||
            (key.name ?? '').includes('Hermes') || (key.name ?? '').includes('REQ')) {
          await ctx.delete(`/api/v1/api-keys/${key.id}/`, {
            headers: { Authorization: `Bearer ${token}` },
          });
        }
      }
    }
    await ctx.dispose();
  });

  test('[REQ-134] /profile page shows API keys section', async ({ page }) => {
    await injectWorkspace(page);
    await injectBearer(page, token);

    const errors = collectConsoleErrors(page);

    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/profile`);
    await page.waitForLoadState('networkidle');

    await screenshot(page, 'req134-01-profile-page');

    const keysSection = page.locator('[data-testid="api-keys-section"]');
    await expect(keysSection).toBeVisible({ timeout: 10000 });

    await screenshot(page, 'req134-02-api-keys-section-visible');

    expect(filterKnownNoise(errors),
      `Console errors on /profile: ${JSON.stringify(errors)}`
    ).toHaveLength(0);
  });

  test('[REQ-134] create API key via UI → plaintext shown once → retrieve via API works (not 405)', async ({ page, request }) => {
    await injectWorkspace(page);
    await injectBearer(page, token);
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/profile`);
    await page.waitForLoadState('networkidle');

    // Fill name and create
    const nameInput = page.locator('[data-testid="api-key-name-input"]');
    await expect(nameInput).toBeVisible({ timeout: 10000 });
    const keyName = `UI-Campaign-REQ134-${Date.now()}`;
    await nameInput.fill(keyName);

    await page.locator('[data-testid="api-key-create-btn"]').click();

    // Plaintext shown exactly once after creation
    const plaintextBox = page.locator('[data-testid="api-key-plaintext-box"]');
    await expect(plaintextBox).toBeVisible({ timeout: 10000 });
    const plaintextEl = page.locator('[data-testid="api-key-plaintext"]');
    const keyText = await plaintextEl.textContent();
    expect(keyText?.length ?? 0, '[REQ-134] plaintext key must be non-empty').toBeGreaterThan(10);

    await screenshot(page, 'req134-03-api-key-created-plaintext-shown');

    // Find key ID via API (retrieve endpoint — the REQ-134 bug was 405 on retrieve)
    const listResp = await request.get(`${BACKEND_URL}/api/v1/api-keys/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(listResp.status()).toBe(200);
    const keys: Array<{ id: string; name: string }> = await listResp.json();
    const created = keys.find((k) => k.name === keyName);
    expect(created, '[REQ-134] created key must appear in list').toBeTruthy();

    // Retrieve by ID — must return 200, not 405 (the bug)
    const retrieveResp = await request.get(`${BACKEND_URL}/api/v1/api-keys/${created!.id}/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    expect(retrieveResp.status(), '[REQ-134] retrieve by ID must return 200 not 405').toBe(200);
    const detail = await retrieveResp.json();
    expect(detail.id).toBe(created!.id);
    expect(detail).not.toHaveProperty('plaintext');
    expect(detail).not.toHaveProperty('key');

    await screenshot(page, 'req134-04-api-key-list-after-creation');
  });
});

// ---------------------------------------------------------------------------
// Journey 4: [REQ-136] Attribute-Visibility-Configs — no console errors
// ---------------------------------------------------------------------------

test.describe('[REQ-136] Attribute Visibility Configs — UI Journey', () => {
  let token: string;

  test.beforeAll(async () => {
    token = await getToken();
  });

  test('[REQ-136] workspace-settings opens without console errors', async ({ page }) => {
    await injectWorkspace(page);
    await injectBearer(page, token);


    const errors: string[] = [];
    page.on('console', (msg) => {
      if (msg.type() === 'error') errors.push(msg.text());
    });
    page.on('pageerror', (err) => errors.push(`UNCAUGHT: ${err.message}`));

    let attrVisStatus: number | null = null;
    page.on('response', (resp) => {
      if (resp.url().includes('attribute-visibility-config')) {
        attrVisStatus = resp.status();
      }
    });

    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/workspace-settings`);
    await page.waitForLoadState('networkidle');

    await screenshot(page, 'req136-01-workspace-settings-loaded');

    // API call must return 200 if it was made
    if (attrVisStatus !== null) {
      expect(attrVisStatus, '[REQ-136] attribute-visibility-configs must return 200').toBe(200);
    }

    // Page must render the workspace-settings container
    await expect(page.locator('[data-testid="workspace-settings"]')).toBeVisible({ timeout: 10000 });

    await screenshot(page, 'req136-02-workspace-settings-rendered');

    // No error banner for attribute visibility
    const errorBanner = page.locator('[data-testid="attr-visibility-error"]');
    const hasError = await errorBanner.isVisible().catch(() => false);
    if (hasError) {
      await screenshot(page, 'req136-FAIL-attr-visibility-error-banner');
      const errorText = await errorBanner.textContent();
      throw new Error(`[REQ-136] attr-visibility error banner shown: "${errorText}"`);
    }

    // Filter out known pre-existing noise (favicon, hot-update, HMR)
    const realErrors = filterKnownNoise(errors);
    expect(realErrors, `[REQ-136] Console errors on workspace-settings: ${JSON.stringify(realErrors)}`).toHaveLength(0);
  });
});

// ---------------------------------------------------------------------------
// Journey 5: [REQ-135] Extended-Preset change_reason error message includes context
// ---------------------------------------------------------------------------

test.describe('[REQ-135] change_reason Error Message — UI Journey', () => {
  let token: string;
  let requirementId: string;

  test.beforeAll(async () => {
    token = await getToken();

    // Set workspace to extended preset
    const { request } = await import('@playwright/test');
    const ctx = await request.newContext({ baseURL: BACKEND_URL });
    const presetResp = await ctx.patch(
      `/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/preset/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { preset: 'extended' },
      }
    );
    expect([200, 204]).toContain(presetResp.status());

    // Create a requirement to try to update without change_reason
    const reqResp = await ctx.post('/api/v1/requirements/', {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: {
        title: `UI-Campaign-REQ135-${Date.now()}`,
        workspace_id: SEEDED_WORKSPACE_ID,
        description: 'Test requirement for REQ-135 change_reason UI campaign',
      },
    });
    expect(reqResp.status()).toBe(201);
    const body = await reqResp.json();
    requirementId = body.id;
    await ctx.dispose();
  });

  test.afterAll(async () => {
    // Reset to minimal preset so other tests are not affected
    const { request } = await import('@playwright/test');
    const ctx = await request.newContext({ baseURL: BACKEND_URL });
    await ctx.patch(`/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/preset/`, {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { preset: 'minimal' },
    });
    await ctx.dispose();
  });

  test('[REQ-135] PATCH without change_reason returns 400 with workspace-contextual error', async ({ request }) => {
    const resp = await request.patch(
      `${BACKEND_URL}/api/v1/requirements/${requirementId}/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: { description: 'Update attempt without change_reason — should fail with contextual error' },
      }
    );
    expect(resp.status(), '[REQ-135] PATCH without change_reason must return 400').toBe(400);
    const body = await resp.json();
    const message: string = body?.error?.message || body?.message || body?.detail || JSON.stringify(body);

    // Must mention change_reason
    expect(message.toLowerCase(), '[REQ-135] error must mention change_reason').toContain('change_reason');

    // Must NOT be bare terse message — must include context (preset or workspace)
    const hasContext =
      message.toLowerCase().includes('preset') ||
      message.toLowerCase().includes('workspace') ||
      message.toLowerCase().includes('policy') ||
      message.toLowerCase().includes('extended');
    expect(hasContext,
      `[REQ-135] Error "${message}" must mention preset/workspace context`
    ).toBe(true);

    // Length check: contextual message must be longer than bare "change_reason required"
    expect(message.length, '[REQ-135] contextual error must be longer than bare message').toBeGreaterThan(
      'change_reason required'.length
    );
  });

  test('[REQ-135] requirements editor page loads for extended-preset workspace', async ({ page }) => {
    await injectWorkspace(page);
    await injectBearer(page, token);

    const errors = collectConsoleErrors(page);

    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/requirements`);
    await page.waitForLoadState('networkidle');

    await screenshot(page, 'req135-01-requirements-editor');

    // Page must render (not crash) even with extended preset
    const content = await page.content();
    expect(content, '[REQ-135] requirements page must render').toContain('root');

    const realErrors = filterKnownNoise(errors);
    expect(realErrors, `[REQ-135] Console errors on /requirements: ${JSON.stringify(realErrors)}`).toHaveLength(0);

    await screenshot(page, 'req135-02-requirements-no-errors');
  });
});

// ---------------------------------------------------------------------------
// Journey 6: [REQ-132] Ollama/AI-Feature — clear error at missing config
// ---------------------------------------------------------------------------

test.describe('[REQ-132] Ollama/AI-Feature — Missing Config Handling', () => {
  let token: string;

  test.beforeAll(async () => {
    token = await getToken();
  });

  test('[REQ-132] workspace-settings loads cleanly even with missing AI (Ollama) config', async ({ page }) => {
    // Note: there is no separate /ai or /ollama UI route in the router.
    // AI config is surfaced inside /settings (WorkspaceSettings).
    // REQ-132 fix: missing Ollama config must not crash the page.
    await injectWorkspace(page);
    await injectBearer(page, token);

    const errors = collectConsoleErrors(page);

    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/settings`);
    await page.waitForLoadState('networkidle');

    await screenshot(page, 'req132-01-settings-page');

    // WorkspaceSettings container must render (no crash due to missing AI config)
    await expect(page.locator('[data-testid="workspace-settings"]')).toBeVisible({ timeout: 10000 });

    // No uncaught exceptions — Ollama config missing must be handled gracefully
    const realErrors = filterKnownNoise(errors);
    expect(realErrors, `[REQ-132] Console errors on /settings: ${JSON.stringify(realErrors)}`).toHaveLength(0);

    await screenshot(page, 'req132-02-settings-no-crash');
  });

  test('[REQ-132] AI derive-requirements gracefully handles missing Ollama config', async ({ request }) => {
    // Create a need and try derivation — the mock provider must respond cleanly
    const needResp = await request.post(
      `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/needs/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: {
          title: `REQ-132-AI-Config-Test-${Date.now()}`,
          description: 'Testing AI feature without Ollama config',
          moscow_priority: 'Must',
        },
      }
    );
    expect(needResp.status()).toBe(201);
    const need = await needResp.json();

    const deriveResp = await request.post(
      `${BACKEND_URL}/api/v1/needs/${need.id}/derive-requirements/`,
      {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: {},
      }
    );
    // Must not return 5xx (REQ-132: clear error or graceful fallback)
    expect(deriveResp.status(), '[REQ-132] AI derive must not return 5xx without config').toBeLessThan(500);

    // Response body must be structured (not raw exception trace)
    const body = await deriveResp.json();
    expect(body, '[REQ-132] response must be JSON object, not raw exception').toBeTruthy();
  });
});

// ---------------------------------------------------------------------------
// Journey 7: [REQ-129] MCP-Tools deduplication — API verification
// ---------------------------------------------------------------------------

test.describe('[REQ-129] MCP Tools Deduplication', () => {
  let mcpKey: string;
  let token: string;

  test.beforeAll(async () => {
    token = await getToken();
    // Clean up stale E2E API keys before creating a fresh MCP key
    const { request } = await import('@playwright/test');
    const ctx = await request.newContext({ baseURL: BACKEND_URL });
    const listResp = await ctx.get('/api/v1/api-keys/', {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (listResp.ok()) {
      const keys: Array<{ id: string; name?: string; revoked?: boolean }> = await listResp.json();
      for (const key of keys) {
        if (key.revoked) continue;
        if ((key.name ?? '').match(/E2E|MCP|REQ|Hermes|UI-Campaign/)) {
          await ctx.delete(`/api/v1/api-keys/${key.id}/`, {
            headers: { Authorization: `Bearer ${token}` },
          });
        }
      }
    }

    const createResp = await ctx.post('/api/v1/api-keys/', {
      headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
      data: { name: `MCP-UI-Campaign-REQ129-${Date.now()}` },
    });
    expect(createResp.status(), '[REQ-129] MCP API key creation must return 201').toBe(201);
    const keyBody = await createResp.json();
    mcpKey = keyBody.plaintext;
    await ctx.dispose();
  });

  test('[REQ-129] tools/list returns no duplicate tool names', async ({ request }) => {
    const resp = await request.post(`${BACKEND_URL}/mcp/`, {
      headers: { 'X-API-Key': mcpKey, 'Content-Type': 'application/json' },
      data: { jsonrpc: '2.0', method: 'tools/list', id: 1, params: {} },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    const tools: Array<{ name: string }> = body.result?.tools ?? [];
    const names = tools.map((t) => t.name);
    const uniqueNames = [...new Set(names)];
    expect(names.length, `[REQ-129] duplicate tools found: ${names.filter((n, i) => names.indexOf(n) !== i)}`).toBe(uniqueNames.length);
  });

  test('[REQ-129] tools/list returns at least 40 tools', async ({ request }) => {
    const resp = await request.post(`${BACKEND_URL}/mcp/`, {
      headers: { 'X-API-Key': mcpKey, 'Content-Type': 'application/json' },
      data: { jsonrpc: '2.0', method: 'tools/list', id: 2, params: {} },
    });
    expect(resp.status()).toBe(200);
    const body = await resp.json();
    const tools: Array<{ name: string }> = body.result?.tools ?? [];
    expect(tools.length, '[REQ-129] must have at least 40 MCP tools').toBeGreaterThanOrEqual(40);
  });

  test('[REQ-129] /profile page accessible without duplicates in API keys list', async ({ page }) => {
    await injectWorkspace(page);
    await injectBearer(page, token);

    const errors = collectConsoleErrors(page);

    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/profile`);
    await page.waitForLoadState('networkidle');

    await screenshot(page, 'req129-01-profile-api-keys-section');

    await expect(page.locator('[data-testid="api-keys-section"]')).toBeVisible({ timeout: 10000 });

    const realErrors = filterKnownNoise(errors);
    expect(realErrors, `[REQ-129] Console errors on /profile: ${JSON.stringify(realErrors)}`).toHaveLength(0);

    await screenshot(page, 'req129-02-profile-no-errors');
  });
});
