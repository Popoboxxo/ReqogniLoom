// Standalone visual design-consistency audit script — POPULATED WORKSPACE variant.
// Follow-up to `e2e/design-audit.js`, which ran against an empty demo tenant and
// therefore could not observe table/row rendering with real data volume.
// Run manually via `node design-audit-populated.js` — NOT part of the Playwright
// test suite, never via `playwright test` / `npm run test:e2e`.
//
// Usage: node design-audit-populated.js
// Requires: frontend dev server on http://localhost:5173, backend on http://localhost:8001,
// admin/admin12345, and the pre-seeded "Zahnbürste SysEng Demo" workspace
// (~880 requirements + related artifacts).

const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const OUT_DIR = path.resolve(__dirname, '..', 'docs', 'test-reports', 'design-audit-populated');
const REPORT_PATH = path.join(OUT_DIR, '_report.json');
const TARGET_WORKSPACE = 'Zahnbürste SysEng Demo';

// List-/table-heavy routes only — where real data volume actually becomes visible.
const ROUTES = [
  ['requirements', '/requirements', 'req-list'],
  ['needs', '/needs', 'need-list'],
  ['adrs', '/adrs', 'adr-list'],
  ['risks', '/risks', 'risk-list'],
  ['issues', '/issues', 'issue-list'],
  ['testcases', '/testcases', 'tc-list'],
  ['traceability', '/traceability', 'tracelink-list'],
  ['architecture', '/architecture', 'arch'],
  ['diagrams', '/diagrams', 'diagram-list'],
  ['baselines', '/baselines', 'baseline-list'],
  ['test-runs', '/test-runs', 'testrun-list'],
];

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

async function login(page) {
  await page.goto(`${FRONTEND_URL}/login`);
  await page.fill('#username-input', 'admin');
  await page.fill('#password-input', 'admin12345');
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
}

async function settle(page, timeout = 8000) {
  try {
    await page.waitForLoadState('networkidle', { timeout });
  } catch {
    // some routes keep long-poll/websocket-ish connections open; ignore
  }
  await page.waitForTimeout(400);
}

async function installWorkspaceListWorkaround(page) {
  // KNOWN PRODUCT BUG (discovered during this audit): the workspace switcher
  // fetches only page 1 (default page_size=25) of GET /api/v1/workspaces/ and
  // never follows `next`, so with >25 workspaces in this dev stack (25
  // leftover e2e-isolated-* debris + 3 real ones = 28 total) the target
  // "Zahnbürste SysEng Demo" workspace (page 2) is UNREACHABLE via the UI —
  // it never appears in the switcher dropdown, no search/pagination exists
  // in the dropdown either. See BUGS_FOUND in the final report.
  //
  // Workaround for THIS AUDIT ONLY (not a fix, not a mock): intercept the
  // real outgoing request and raise page_size so the real backend returns
  // all real workspaces in one response. No fake data, no stubbed body —
  // same endpoint, same DB, just a larger page requested.
  await page.route('**/api/v1/workspaces/*', async (route) => {
    const req = route.request();
    if (req.method() !== 'GET') return route.continue();
    const url = new URL(req.url());
    if (url.searchParams.has('page')) return route.continue(); // leave pagination sub-requests alone
    url.searchParams.set('page_size', '100');
    await route.continue({ url: url.toString() });
  });
}

async function switchWorkspace(page, workspaceName) {
  const switcherBtn = page.locator('[data-testid="workspace-switcher"]');
  await switcherBtn.click();
  await page.waitForTimeout(300);
  const list = page.getByRole('listbox', { name: 'Workspace switcher' });
  await list.waitFor({ state: 'visible', timeout: 5000 });
  const option = list.locator('[data-testid="workspace-switcher-option"]', { hasText: workspaceName });
  await option.first().click();
  await page.waitForTimeout(500);
  await settle(page, 15000);
}

async function main() {
  ensureDir(OUT_DIR);
  const filter = process.env.AUDIT_ROUTES ? process.env.AUDIT_ROUTES.split(',') : null;
  const routes = filter ? ROUTES.filter(([slug]) => filter.includes(slug)) : ROUTES;

  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  const pageErrors = [];
  page.on('pageerror', (err) => pageErrors.push(String(err)));

  const report = {};

  console.log('[audit] logging in...');
  await login(page);

  await installWorkspaceListWorkaround(page);
  await page.reload({ waitUntil: 'domcontentloaded' });
  await settle(page, 15000);
  console.log(`[audit] switching workspace -> "${TARGET_WORKSPACE}"...`);
  await switchWorkspace(page, TARGET_WORKSPACE);
  await page.screenshot({ path: path.join(OUT_DIR, '_workspace-switched-dashboard.png'), fullPage: true });

  for (const [slug, route, testIdPrefix] of routes) {
    console.log(`[audit] route: ${route}`);
    const t0 = Date.now();
    const routeReport = { route, errors: [] };
    try {
      await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' });
      await settle(page, 15000);
      routeReport.loadMs = Date.now() - t0;

      // Row/entry count sample: try the toolbar count testid first, else count
      // table rows / tree items visible in the DOM.
      const countLocator = page.locator(`[data-testid="${testIdPrefix}-count"]`);
      routeReport.toolbarCount = (await countLocator.first().innerText().catch(() => null)) || null;
      routeReport.visibleRowCount = await page
        .locator('main[role="main"] tbody tr, main[role="main"] [role="treeitem"], main[role="main"] [data-testid$="-tree-item"]')
        .count()
        .catch(() => -1);

      // Baseline screenshot at 1366px, full data set, default sort/filter.
      await page.screenshot({ path: path.join(OUT_DIR, `${slug}-1366.png`), fullPage: true });

      // Pagination probe: look for any element that smells like pagination
      // controls (page numbers, next/prev, "load more").
      const paginationCandidates = await page
        .locator('main[role="main"] [class*="pagination" i], main[role="main"] [aria-label*="pagination" i], main[role="main"] button:has-text("Weiter"), main[role="main"] button:has-text("Nächste"), main[role="main"] button:has-text("Load more"), main[role="main"] button:has-text("Mehr laden")')
        .count()
        .catch(() => 0);
      routeReport.paginationControlsFound = paginationCandidates;

      // Sort-select interaction: cycle through all options, screenshot the
      // sort dropdown area itself (to check the known caret-clipping bug)
      // plus one full-page shot for the resulting order.
      const sortSelect = page.locator(`[data-testid="${testIdPrefix}-sort-select"]`);
      const hasSortSelect = await sortSelect.count();
      routeReport.hasSortSelect = hasSortSelect > 0;
      if (hasSortSelect > 0) {
        try {
          await sortSelect.first().scrollIntoViewIfNeeded();
          const box = await sortSelect.first().boundingBox();
          if (box) {
            await page.screenshot({
              path: path.join(OUT_DIR, `${slug}-sort-dropdown-closeup.png`),
              clip: { x: Math.max(0, box.x - 40), y: Math.max(0, box.y - 20), width: box.width + 120, height: box.height + 40 },
            });
          }
          const options = await sortSelect.first().locator('option').allTextContents();
          routeReport.sortOptions = options;
          if (options.length > 1) {
            await sortSelect.first().selectOption({ index: options.length - 1 });
            await page.waitForTimeout(500);
            await page.screenshot({ path: path.join(OUT_DIR, `${slug}-sorted-alt.png`), fullPage: true });
            // reset
            await sortSelect.first().selectOption({ index: 0 });
            await page.waitForTimeout(400);
          }
        } catch (e) {
          routeReport.errors.push(`sort-probe: ${String(e)}`);
        }
      }

      // Filter interaction: click the first status/category filter chip found
      // and screenshot the filtered result to check layout stability.
      const filterCandidates = page.locator(`[data-testid^="${testIdPrefix}-filter-"]`);
      const filterCount = await filterCandidates.count();
      routeReport.filterControlsFound = filterCount;
      if (filterCount > 0) {
        try {
          const first = filterCandidates.first();
          const tag = await first.evaluate((el) => el.tagName.toLowerCase());
          if (tag === 'select') {
            const opts = await first.locator('option').allTextContents();
            if (opts.length > 1) {
              await first.selectOption({ index: 1 });
              await page.waitForTimeout(500);
              await page.screenshot({ path: path.join(OUT_DIR, `${slug}-filtered.png`), fullPage: true });
              await first.selectOption({ index: 0 });
              await page.waitForTimeout(400);
            }
          } else {
            await first.click({ timeout: 2000 });
            await page.waitForTimeout(500);
            await page.screenshot({ path: path.join(OUT_DIR, `${slug}-filtered.png`), fullPage: true });
            await first.click({ timeout: 2000 }).catch(() => {});
          }
        } catch (e) {
          routeReport.errors.push(`filter-probe: ${String(e)}`);
        }
      }

      // Search interaction with a realistic partial term from the real
      // dataset (toothbrush domain) to check truncation/highlight behavior
      // on genuine long titles instead of synthetic ones.
      const searchInput = page.locator(`[data-testid="${testIdPrefix}-search-input"]`);
      if ((await searchInput.count()) > 0) {
        try {
          await searchInput.first().fill('Zahnbürste');
          await page.waitForTimeout(600);
          await page.screenshot({ path: path.join(OUT_DIR, `${slug}-search-result.png`), fullPage: true });
          await searchInput.first().fill('');
          await page.waitForTimeout(400);
        } catch (e) {
          routeReport.errors.push(`search-probe: ${String(e)}`);
        }
      }

      // Reset to base route, re-screenshot at 1920 width for the same
      // (default) state.
      await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' });
      await settle(page, 15000);
      await page.setViewportSize({ width: 1920, height: 1080 });
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(OUT_DIR, `${slug}-1920.png`), fullPage: true });
      await page.setViewportSize({ width: 1366, height: 900 });
    } catch (e) {
      routeReport.errors.push(String(e));
      console.error(`[audit] ERROR on ${route}:`, e.message || e);
    }
    report[slug] = routeReport;
  }

  report._consoleErrors = consoleErrors.slice(0, 200);
  report._pageErrors = pageErrors.slice(0, 200);
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
  console.log(`[audit] report written to ${REPORT_PATH}`);

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
