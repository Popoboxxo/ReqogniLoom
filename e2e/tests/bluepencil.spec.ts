// Issue #972 / docs/bluepencil-integration.md §4 — bluepencil review layer (Option B: sidecar).
//
// Proves the review layer end-to-end against the *real* stack: the layer mounts only
// when the sidecar's health probe succeeds, a text note created on a `data-testid`
// anchor lands in the sidecar's store (asserted outside the page, §4.1), and the note
// is cleaned up again.
//
// The sidecar is OPTIONAL and is NOT started in CI (`make bluepencil`). This spec must
// therefore skip visibly — with an actionable reason — when it is unavailable, and must
// never fail spuriously. A missing *browser* may still turn the job red (§4.4); a missing
// optional sidecar may not.
//
// Run (dev stack up + sidecar healthy):
//   cd e2e && npx playwright test tests/bluepencil.spec.ts
import { test, expect, request as playwrightRequest, type Page } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/** Same-origin path the Vite dev server proxies to `bluepencil:8787` (vite.config.ts). */
const HEALTH_URL = '/bluepencil/api/health';
const NOTES_URL = '/bluepencil/api/notes';
const BULK_DELETE_URL = '/bluepencil/api/notes/bulk-delete';

const SKIP_REASON =
  "bluepencil sidecar not reachable — run 'make bluepencil' to enable this spec";

/** Unique per run so repeated / parallel runs never collide in the shared JSON store. */
const NOTE_MARKER = `e2e-bluepencil-${Date.now()}`;

/** Probe result of `beforeAll`, re-stated per test because `test.skip()` needs a test scope. */
let sidecarAvailable = false;

/** Id of the note this run created, so `afterEach` can remove it again. */
let createdNoteId: string | null = null;

test.beforeAll(async () => {
  // `request.newContext` (not the test-scoped `request` fixture): only worker-scoped
  // fixtures are available in `beforeAll`. Probe through the app origin so we exercise
  // the same same-origin path the frontend loader uses (vite proxy → sidecar).
  const ctx = await playwrightRequest.newContext({ baseURL: FRONTEND_URL });
  try {
    const response = await ctx.get(HEALTH_URL, { timeout: 5000 });
    if (response.ok()) {
      const body = (await response.json()) as { ok?: unknown };
      sidecarAvailable = body.ok === true;
    }
  } catch {
    sidecarAvailable = false;
  } finally {
    await ctx.dispose();
  }
});

/**
 * Skip the current test unless the sidecar answered `/health` with `{ok: true}`.
 *
 * `test.skip()` is re-stated on every test instead of in `beforeAll` so the probe
 * stays a pure measurement and the skip is reported against each test with the
 * actionable reason above. A skipped run is visible in the report — it never
 * silently passes.
 */
function requireSidecar(): void {
  test.skip(!sidecarAvailable, SKIP_REASON);
}

const ARMING_SKIP_REASON =
  'frontend review layer not armed — set BLUEPENCIL_ENABLED=1 and restart the frontend ' +
  '(the sidecar alone is not enough; the loader is gated by VITE_BLUEPENCIL_ENABLED at ' +
  'build/dev-server start).';

/**
 * Skip unless the frontend actually injected the layer loader (issue #947).
 *
 * A running sidecar is necessary but NOT sufficient: the loader is gated by
 * `VITE_BLUEPENCIL_ENABLED`, read when Vite starts. With the sidecar up but the
 * flag `0` (the dev default) both tests below used to fail instead of skipping.
 * The injected `script[data-bluepencil-loader]` is only present when the layer
 * is armed AND the probe succeeded, so it is the honest arming signal.
 */
async function requireReviewLayerArmed(page: Page): Promise<void> {
  const armed = await page
    .waitForSelector('script[data-bluepencil-loader]', { timeout: 5000 })
    .then(() => true)
    .catch(() => false);
  test.skip(!armed, ARMING_SKIP_REASON);
}

/**
 * Remove the note this run created. Contract verified against the sidecar
 * (`server/handler.ts::bulkDelete`): `POST {base}/notes/bulk-delete` requires
 * `{ confirm: true }` plus either `ids` or `filter`, and answers `{ removed }`.
 */
test.afterEach(async ({ request }) => {
  if (createdNoteId === null) return;
  const id = createdNoteId;
  createdNoteId = null;
  const response = await request.post(BULK_DELETE_URL, {
    data: { ids: [id], confirm: true },
  });
  expect(response.ok(), `cleanup of note ${id} failed: ${response.status()}`).toBeTruthy();
  const body = (await response.json()) as { removed?: number };
  expect(body.removed, `cleanup of note ${id} removed nothing`).toBe(1);
});

test.describe('[issue #972] bluepencil review layer', () => {
  test('creates a text note on a data-testid anchor and persists it to the sidecar store', async ({
    page,
  }) => {
    requireSidecar();

    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
    // Deterministic authenticated route that renders the sidebar with the anchor below.
    await page.goto(`${FRONTEND_URL}/requirements`);
    await requireReviewLayerArmed(page);

    // (b) The layer mounted. `bluepencil-notes` is the vendored custom element and the
    // toolbar is its stable, locale-independent hook (`role="toolbar"`): matching a
    // localized label would break as soon as the app language flips de↔en.
    const layerElement = page.locator('bluepencil-notes');
    await expect(layerElement).toHaveCount(1);
    await expect(layerElement).toHaveAttribute('data-bp-version', /.+/);
    await expect(page.locator('[data-bp-part="bar"]')).toBeVisible();

    // (c) Activate text-note mode, click a `data-testid` anchor, type the marker, save.
    const textModeButton = page.locator('[data-bp-action="mode-text"]');
    await textModeButton.click();
    await expect(textModeButton).toHaveAttribute('aria-pressed', 'true');

    const anchor = page.locator('[data-testid="build-version-indicator"]');
    await expect(anchor).toBeVisible();
    await anchor.click();

    const composerBody = page.locator('[data-bp-part="composer-body"]');
    await expect(composerBody).toBeVisible();
    await composerBody.fill(NOTE_MARKER);
    await page.locator('[data-bp-action="composer-save"]').click();

    // The composer closes only after a *successful* store round-trip; on failure it
    // stays open and reports inline. So a closed composer is the in-page confirmation.
    await expect(page.locator('[data-bp-part="composer"]')).toBeHidden();

    // (d) The assertion that matters is outside the page (§4.1): poll the sidecar's own
    // store over the same origin and prove the marker — and the `data-testid` anchor —
    // actually landed. `expect.poll` auto-waits; no arbitrary sleep.
    let storedId: string | null = null;
    await expect
      .poll(
        async () => {
          const response = await page.request.get(NOTES_URL);
          if (!response.ok()) return null;
          const body = (await response.json()) as {
            notes?: Array<{ id?: string; body?: string; anchor?: { hook?: string } }>;
          };
          const match = (body.notes ?? []).find((note) => (note.body ?? '').includes(NOTE_MARKER));
          storedId = match?.id ?? null;
          return storedId;
        },
        { timeout: 15000, message: 'note never appeared in GET /bluepencil/api/notes' },
      )
      .not.toBeNull();
    createdNoteId = storedId;

    // The anchor must be the hook taken from `data-testid` (not a brittle CSS path).
    const stored = await (
      await page.request.get(NOTES_URL)
    ).json() as { notes?: Array<{ id?: string; body?: string; anchor?: { hook?: string } }> };
    const persisted = (stored.notes ?? []).find((note) => note.id === storedId);
    expect(persisted?.body).toContain(NOTE_MARKER);
    expect(persisted?.anchor?.hook).toBe('build-version-indicator');
  });

  test('mounts the layer exactly when the health probe succeeds', async ({ page }) => {
    requireSidecar();

    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
    // First load un-routed so the arming precondition can be judged honestly.
    await page.goto(`${FRONTEND_URL}/requirements`);
    // Authenticated shell is up — so an absent layer is a real absence, not a blank page.
    await expect(page.locator('[data-testid="build-version-indicator"]')).toBeVisible();
    await requireReviewLayerArmed(page);

    // Force the "health probe fails" state without touching the shared container: route
    // the probe to an error. This is the honest invariant we can test here — removing the
    // already-enabled loader from the DOM is not something the test can do.
    await page.route('**/bluepencil/api/health', (route) =>
      route.fulfill({ status: 503, json: { ok: false, status: 'unavailable' } }),
    );
    await page.reload();

    // (1) Probe fails → no loader injected, no custom element, no toolbar.
    await expect(page.locator('bluepencil-notes')).toHaveCount(0);
    await expect(page.locator('[data-bp-part="bar"]')).toHaveCount(0);

    // (2) Probe succeeds again → the next bootstrap mounts the layer.
    await page.unroute('**/bluepencil/api/health');
    await page.reload();
    await expect(page.locator('bluepencil-notes')).toHaveCount(1);
    await expect(page.locator('[data-bp-part="bar"]')).toBeVisible();
  });
});
