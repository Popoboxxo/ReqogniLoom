/**
 * Ad-hoc verification test: create a stakeholder need via browser UI.
 * Verifies the fix for the null-UUID guard (NeedsEditors.tsx line 59).
 * Branch: fix/workspace-null-uuid-guard
 *
 * Auth note: The app uses httpOnly-cookie auth (REQ-052). Vite's dev-proxy
 * rewrites the Host header (changeOrigin:true), so the Set-Cookie domain
 * becomes "backend" rather than "localhost" — the browser silently rejects it.
 * Fix: Playwright intercepts all /api/** requests and injects the Bearer
 * token obtained directly from the API. Production code is unchanged.
 */
import { test, expect, type Route } from '@playwright/test';
import {
  getAuthToken,
  setWorkspaceId,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

const NEED_TITLE = `Test-Bedarf-Fix-Verifikation-${Date.now()}`;

// ---------------------------------------------------------------------------
// [REQ-L0-003 / null-UUID guard] Create a stakeholder need via browser UI
// ---------------------------------------------------------------------------
test.describe('[REQ-L0-003] create stakeholder need via browser UI', () => {
  let token: string;

  test.beforeAll(async () => {
    token = await getAuthToken();
  });

  test.beforeEach(async ({ page }) => {
    // Inject workspace ID into sessionStorage before every page load
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);

    // Inject Bearer token into every /api/** request so the Vite proxy
    // passes it to the backend. This works around the httpOnly-cookie/domain
    // mismatch that occurs with Vite's changeOrigin proxy in dev mode.
    await page.route('/api/**', async (route: Route) => {
      const request = route.request();
      const headers = {
        ...await request.allHeaders(),
        Authorization: `Bearer ${token}`,
      };
      await route.continue({ headers });
    });

    // Navigate to login page and submit form (sets React app auth state
    // so WorkspaceContext, nav, etc. render correctly).
    await page.goto(`${FRONTEND_URL}/login`);
    await page.fill('#username-input', 'admin');
    await page.fill('#password-input', 'admin12345');
    await page.click('button[type="submit"]');
    // Wait for redirect away from /login (app renders nav shell)
    await page.waitForURL((url) => !url.pathname.includes('/login'), {
      timeout: 10000,
    });
  });

  test('[REQ-L0-003] POST /workspaces/{id}/needs/ returns 201 and item appears in list', async ({ page }) => {
    // Navigate to the needs view for the seeded workspace
    await page.goto(`${FRONTEND_URL}/needs`);

    // Wait until the create button is enabled (workspaces loaded, guard lifted)
    const createBtn = page.locator('[data-testid="create-need-btn"]');
    await expect(createBtn).toBeVisible({ timeout: 15000 });
    // The button is disabled (opacity 0.6, cursor not-allowed) until workspaces
    // are loaded — wait for the enabled state
    await expect(createBtn).not.toBeDisabled({ timeout: 10000 });

    // Open the inline create form
    await createBtn.click();

    // Title input inside the form
    const titleInput = page.locator('form input[type="text"]').first();
    await expect(titleInput).toBeVisible({ timeout: 5000 });
    await titleInput.fill(NEED_TITLE);

    // Intercept POST and submit concurrently
    const [response] = await Promise.all([
      page.waitForResponse(
        (resp) =>
          resp.url().includes('/needs/') &&
          resp.request().method() === 'POST',
        { timeout: 15000 },
      ),
      page.locator('form button[type="submit"]').click(),
    ]);

    const postStatus = response.status();
    console.log(`POST ${response.url()} → HTTP ${postStatus}`);

    expect(postStatus, 'POST /needs/ must return 201 Created').toBe(201);

    // After successful create the new item must appear in the list
    await expect(page.locator(`text=${NEED_TITLE}`)).toBeVisible({
      timeout: 10000,
    });

    console.log(`Need "${NEED_TITLE}" visible in list — test PASSED`);
  });
});

// ---------------------------------------------------------------------------
// Fallback: pure API smoke-test (no browser) to isolate backend from UI
// ---------------------------------------------------------------------------
test('[REQ-L0-003] API only — POST /workspaces/{id}/needs/ returns 201', async ({ request }) => {
  const tkn = await getAuthToken();
  const apiTitle = `API-Smoke-${Date.now()}`;

  const response = await request.post(
    `${BACKEND_URL}/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/needs/`,
    {
      headers: { Authorization: `Bearer ${tkn}` },
      data: {
        title: apiTitle,
        description: 'Created by create-need-verification.spec.ts',
        moscow_priority: 'Must',
      },
    },
  );

  console.log(`POST /api/v1/workspaces/${SEEDED_WORKSPACE_ID}/needs/ → HTTP ${response.status()}`);
  expect(response.status()).toBe(201);

  const body = await response.json();
  expect(body).toMatchObject({ title: apiTitle });
  console.log(`Created need id=${body.id}`);
});
