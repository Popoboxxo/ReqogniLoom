// Visual regression baseline (docs/GESAMTTEST_BERICHT_2026-08-21.md §9.8).
// Real snapshot comparisons via expect(page).toHaveScreenshot(), not ad-hoc
// screenshots. To update the baseline after a deliberate UI change:
//   npx playwright test visual-regression --update-snapshots
// then re-run WITHOUT --update-snapshots and confirm it is 100% green.
import { test, expect, request as pwRequest, type Page, type Locator } from '@playwright/test';
import { loginAsAdmin, getAuthToken, setWorkspaceId } from '../helpers/auth';
import fs from 'fs';
import os from 'os';
import path from 'path';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8000';

// ---------------------------------------------------------------------------
// All 24 top-level routes from SidebarNavigation.tsx's NAV_ITEMS (kept in the
// same order/slugs as the pre-existing e2e/design-audit.js ad-hoc audit list,
// so findings from both tools stay easy to cross-reference).
// ---------------------------------------------------------------------------
const ROUTES: Array<[string, string]> = [
  ['dashboard', '/'],
  ['goals', '/goals'],
  ['metrics', '/metrics'],
  ['interviews', '/interviews'],
  ['needs', '/needs'],
  ['requirements', '/requirements'],
  ['adrs', '/adrs'],
  ['risks', '/risks'],
  ['issues', '/issues'],
  ['glossary', '/glossary'],
  ['architecture', '/architecture'],
  ['traceability', '/traceability'],
  ['impact', '/impact'],
  ['icds', '/icds'],
  ['diagrams', '/diagrams'],
  ['testcases', '/testcases'],
  ['test-runs', '/test-runs'],
  ['baselines', '/baselines'],
  ['reviews', '/reviews'],
  ['import', '/import'],
  ['workflows', '/workflows'],
  ['audit', '/audit'],
  ['settings', '/settings'],
  ['system-settings', '/system-settings'],
];

// A brand-new, dedicated workspace (not the populated "Zahnbürste"/demo
// workspace, and not the shared SEEDED_WORKSPACE_ID other specs mutate) so
// the baseline never drifts from unrelated data growth. Created once via API
// with the 'extended' preset so every gated route (baselines, reviews, ...)
// renders its real (empty-state) UI instead of a preset-disabled notice.
let ISOLATED_WORKSPACE_ID: string;

test.beforeAll(async () => {
  const token = await getAuthToken();
  const ctx = await pwRequest.newContext({ baseURL: BACKEND_URL });
  const wsName = `e2e-visual-regression-${Date.now()}`;
  const response = await ctx.post('/api/v1/workspaces/', {
    headers: { Authorization: `Bearer ${token}` },
    data: {
      name: wsName,
      preset: 'extended',
      terminology_profile: 'se_mode',
      language: 'en',
    },
  });
  if (!response.ok()) {
    throw new Error(`Failed to create isolated visual-regression workspace: ${response.status()} ${await response.text()}`);
  }
  const body = await response.json();
  ISOLATED_WORKSPACE_ID = body.id as string;
  await ctx.dispose();
});

test.beforeEach(async ({ page }) => {
  // Disable CSS animations/transitions + native caret blink before any app
  // script runs, and on every subsequent navigation (addInitScript re-runs
  // per document). Playwright's toHaveScreenshot already freezes CSS
  // animations/transitions to their end state by default ("animations:
  // disabled") — this additionally covers JS-timer-driven restarts and the
  // native text-cursor blink, which that built-in does not touch.
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.addInitScript(() => {
    const style = document.createElement('style');
    style.setAttribute('data-e2e-visual-freeze', 'true');
    style.textContent = `
      *, *::before, *::after {
        animation-duration: 0s !important;
        animation-delay: 0s !important;
        transition-duration: 0s !important;
        transition-delay: 0s !important;
        scroll-behavior: auto !important;
      }
      input, textarea, [contenteditable="true"] {
        caret-color: transparent !important;
      }
    `;
    document.documentElement.appendChild(style);
  });

  await setWorkspaceId(page, ISOLATED_WORKSPACE_ID);
  await loginAsAdmin(page);
});

/**
 * Locators masked out (solid overlay, layout untouched) on every screenshot:
 * build/version indicator (deployed commit, changes every deploy) and any
 * native <time> element (relative/absolute timestamps).
 */
function volatileMasks(page: Page): Locator[] {
  return [
    page.locator('[data-testid="build-version-indicator"]'),
    page.locator('time'),
  ];
}

async function gotoAndSettle(page: Page, route: string): Promise<void> {
  await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' });
  // Lazy-loaded route chunks render a Suspense fallback first — wait for it
  // to be gone rather than a fixed sleep.
  await expect(page.locator('[data-testid="route-suspense-fallback"]')).toHaveCount(0, { timeout: 15000 });
  await expect(page.locator('main[role="main"]')).toBeVisible({ timeout: 10000 });
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {
    // Some routes keep a long-poll/websocket-ish connection open; the
    // Suspense-fallback + main-visible waits above are the real gate.
  });
}

test.describe('[VISUAL] Route screenshots (isolated empty workspace)', () => {
  for (const [slug, route] of ROUTES) {
    if (slug === 'dashboard') {
      // The dashboard lists ALL workspaces for the tenant (DashboardViews.tsx
      // -> useDashboardData), not just the isolated one — it is not scoped
      // by active-workspace selection. Across repeated E2E-suite runs this
      // list grows without bound (25+ workspaces observed from prior specs
      // at authoring time), so a full-page screenshot of it can never be
      // stable: new cards would grow the scrollable page height itself, not
      // just the pixels under a mask. Mitigation: clip to the viewport
      // (fullPage: false, constant image dimensions) and mask the entire
      // card-list container, so the route chrome (header, sidebar, nav) is
      // still regression-tested while the volatile card list never affects
      // the diff.
      test(`[VISUAL] ${slug} route renders consistently`, async ({ page }) => {
        await gotoAndSettle(page, route);
        await expect(page.locator('[data-testid="workspace-list"]')).toBeVisible({ timeout: 10000 });
        await expect(page).toHaveScreenshot(`route-${slug}.png`, {
          fullPage: false,
          mask: [...volatileMasks(page), page.locator('[data-testid="workspace-list"]')],
        });
      });
      continue;
    }

    test(`[VISUAL] ${slug} route renders consistently`, async ({ page }) => {
      await gotoAndSettle(page, route);
      await expect(page).toHaveScreenshot(`route-${slug}.png`, {
        fullPage: true,
        mask: volatileMasks(page),
      });
    });
  }
});

test.describe('[VISUAL] Dialog screenshots', () => {
  test('[VISUAL] requirement create quick-form dialog', async ({ page }) => {
    await gotoAndSettle(page, '/requirements');
    await page.locator('[data-testid="create-req-btn"]').click();
    await expect(page.locator('[data-testid="req-new-title-input"]')).toBeVisible({ timeout: 10000 });
    await expect(page).toHaveScreenshot('dialog-requirement-create.png', {
      fullPage: true,
      mask: volatileMasks(page),
    });
  });

  test('[VISUAL] create workspace modal dialog', async ({ page }) => {
    await gotoAndSettle(page, '/');
    await expect(page.locator('[data-testid="create-workspace-btn"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="create-workspace-btn"]').click();
    await expect(page.locator('[data-testid="create-workspace-modal"]')).toBeVisible({ timeout: 5000 });
    await expect(page).toHaveScreenshot('dialog-workspace-create.png', {
      fullPage: true,
      // The dashboard behind the modal overlay is the same tenant-wide,
      // ever-growing workspace list as the dashboard route test above — mask
      // it too so the modal itself is the only thing under test.
      mask: [...volatileMasks(page), page.locator('[data-testid="workspace-list"]')],
    });
  });

  test('[VISUAL] csv import panel — initial (no file selected)', async ({ page }) => {
    await gotoAndSettle(page, '/import');
    await expect(page.locator('[data-testid="csv-import-page"]')).toBeVisible({ timeout: 10000 });
    await expect(page).toHaveScreenshot('dialog-csv-import-initial.png', {
      fullPage: true,
      mask: volatileMasks(page),
    });
  });

  test('[VISUAL] csv import panel — file selected', async ({ page }) => {
    await gotoAndSettle(page, '/import');
    await expect(page.locator('[data-testid="csv-import-page"]')).toBeVisible({ timeout: 10000 });

    const tmpDir = os.tmpdir();
    const csvPath = path.join(tmpDir, 'e2e-visual-regression-fixture.csv');
    fs.writeFileSync(
      csvPath,
      'title,description,category,status\nVisual Regression Fixture Req,Deterministic fixture row,functional,draft\n',
      'utf-8'
    );
    try {
      await page.locator('[data-testid="csv-file-input"]').setInputFiles(csvPath);
      await expect(page.locator('[data-testid="csv-drop-zone"]')).toContainText('e2e-visual-regression-fixture.csv');
      await expect(page).toHaveScreenshot('dialog-csv-import-file-selected.png', {
        fullPage: true,
        mask: volatileMasks(page),
      });
    } finally {
      fs.unlinkSync(csvPath);
    }
  });

  test('[VISUAL] trace link create dialog', async ({ page }) => {
    // RequirementEditors uses its own older inline ReqTraceLinkPanel (no
    // modal) — the unified CreateTraceLinkDialog (data-testid
    // "create-trace-link-dialog") only exists in the shared TraceLinkPanel,
    // which is used by Adr/Architecture/Issue/Need/Risk editors instead.
    // Risks is the simplest of those quick-create flows.
    await gotoAndSettle(page, '/risks');
    await page.locator('[data-testid="create-risk-btn"]').click();
    // Save is disabled until a title is entered.
    await page.locator('[data-testid="risk-new-title-input"]').fill('Visual Regression Fixture Risk');
    await page.locator('[data-testid="risk-new-save-btn"]').click();

    await expect(page.locator('[data-testid="trace-link-panel-open-dialog"]')).toBeVisible({ timeout: 10000 });
    await page.locator('[data-testid="trace-link-panel-open-dialog"]').click();
    await expect(page.locator('[data-testid="create-trace-link-dialog"]')).toBeVisible({ timeout: 5000 });
    await expect(page).toHaveScreenshot('dialog-trace-link-create.png', {
      fullPage: true,
      mask: volatileMasks(page),
    });
  });
});
