// Standalone visual design-consistency audit script (NOT part of the Playwright
// test suite — run manually via `node design-audit.js`, never via `playwright test`
// / `npm run test:e2e`). Produces screenshots + a computed-style sample report
// for a human/agent to review against frontend/src/styles/tokens.css.
//
// Usage: node design-audit.js
// Requires: frontend dev server on http://localhost:5173, backend on http://localhost:8001,
// seeded demo tenant (admin / admin12345).

const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const OUT_DIR = path.resolve(__dirname, '..', 'docs', 'test-reports', 'design-audit-screenshots');
const REPORT_PATH = path.join(OUT_DIR, '_computed-styles-report.json');

const ROUTES = [
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

// Primary pattern: the app's established "create new X" button naming
// convention (German "Neue/Neuer/Neues ...", English "New ..."). Checked
// first so it wins over secondary/alternate-flow buttons that merely
// contain "erstellen"/"create" as a verb (e.g. "Lieber im Dialog
// erstellen?", a mode-toggle, not the primary create action).
const CREATE_BTN_PRIMARY_RE = /^(neue?r?s?\s|new\s)/i;
const CREATE_BTN_FALLBACK_RE = /(neu|new|hinzufügen|erstellen|anlegen|create|add|\+ )/i;

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

async function settle(page) {
  try {
    await page.waitForLoadState('networkidle', { timeout: 8000 });
  } catch {
    // some routes keep long-poll/websocket-ish connections open; ignore
  }
  await page.waitForTimeout(400);
}

async function sampleComputedStyles(page, routeSlug) {
  // Best-effort DOM sampling for token-consistency comparison. Uses
  // page.evaluate scoped strictly to reading getComputedStyle — no app
  // state mutation, no arbitrary logic injected into the app.
  try {
    return await page.evaluate(() => {
      function sample(el) {
        if (!el) return null;
        const cs = window.getComputedStyle(el);
        return {
          tag: el.tagName.toLowerCase(),
          text: (el.textContent || '').trim().slice(0, 40),
          backgroundColor: cs.backgroundColor,
          color: cs.color,
          fontFamily: cs.fontFamily,
          fontSize: cs.fontSize,
          borderRadius: cs.borderRadius,
          padding: cs.padding,
          border: cs.border,
        };
      }
      const results = { buttons: [], headlines: [], cards: [], tables: [] };
      document.querySelectorAll('button').forEach((el, i) => {
        if (i < 8) results.buttons.push(sample(el));
      });
      document.querySelectorAll('h1, h2, h3').forEach((el, i) => {
        if (i < 6) results.headlines.push(sample(el));
      });
      document.querySelectorAll('[class*="card" i], [class*="Card"]').forEach((el, i) => {
        if (i < 6) results.cards.push(sample(el));
      });
      document.querySelectorAll('table').forEach((el, i) => {
        if (i < 3) results.tables.push(sample(el));
      });
      return results;
    });
  } catch (e) {
    return { error: String(e) };
  }
}

async function tryOpenDialog(page, routeSlug) {
  // Heuristic: find a visible button whose accessible name suggests it opens
  // a create/new dialog, click it, wait briefly, check for a dialog/modal.
  // Scoped to <main role="main"> so the sidebar's persistent "Workspace
  // erstellen" button (present on every route) never masks the route's own
  // primary action.
  const scope = page.locator('main[role="main"]');
  const buttons = await scope.locator('button:visible, a[role="button"]:visible').all();
  const candidates = [];
  for (const btn of buttons) {
    let label = '';
    try {
      label = (await btn.innerText({ timeout: 1000 })) || '';
    } catch {
      continue;
    }
    candidates.push({ btn, label });
  }
  const ordered = [
    ...candidates.filter((c) => CREATE_BTN_PRIMARY_RE.test(c.label.trim())),
    ...candidates.filter(
      (c) => !CREATE_BTN_PRIMARY_RE.test(c.label.trim()) && CREATE_BTN_FALLBACK_RE.test(c.label)
    ),
  ];
  // Only try the single best candidate (highest-priority match). The app
  // uses two equally valid "create" UI patterns depending on context/mode:
  // a true modal (`role="dialog"`) or an inline split-view editor panel
  // (no modal — the right pane swaps its content). Both are legitimate
  // states to capture for this audit, so success is "the button was
  // clickable", not "a modal specifically appeared" — the screenshot itself
  // records whichever pattern the route actually used.
  const best = ordered[0];
  if (!best) return null;
  try {
    await best.btn.click({ timeout: 3000 });
  } catch (e) {
    return null;
  }
  await page.waitForTimeout(700);
  const dialog = page
    .locator('[role="dialog"], .modal, [class*="Dialog" i][class*="overlay" i], [class*="modal" i]')
    .first();
  const hadModal = await dialog.isVisible().catch(() => false);
  return { label: best.label.trim().slice(0, 40), hadModal };
}

async function cleanStaleOutputs(routes) {
  // Remove this script's own previous PNGs/report for the routes about to be
  // re-run, so a route that no longer opens a dialog doesn't leave a stale
  // screenshot from an earlier (e.g. pre-fix) run lying around looking current.
  // Never touches a11y-*.json (owned by the parallel accessibility audit).
  if (!fs.existsSync(OUT_DIR)) return;
  const slugs = routes.map(([slug]) => slug);
  for (const f of fs.readdirSync(OUT_DIR)) {
    if (!f.endsWith('.png')) continue;
    const matches = slugs.some((slug) => f === `${slug}.png` || f.startsWith(`${slug}-`));
    if (matches) {
      fs.unlinkSync(path.join(OUT_DIR, f));
    }
  }
}

async function main() {
  ensureDir(OUT_DIR);
  const filter = process.env.AUDIT_ROUTES ? process.env.AUDIT_ROUTES.split(',') : null;
  const routes = filter ? ROUTES.filter(([slug]) => filter.includes(slug)) : ROUTES;
  await cleanStaleOutputs(routes);
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  const report = {};

  console.log('[audit] logging in...');
  await login(page);

  for (const [slug, route] of routes) {
    console.log(`[audit] route: ${route}`);
    const routeReport = { route, errors: [] };
    try {
      await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' });
      await settle(page);
      await page.screenshot({ path: path.join(OUT_DIR, `${slug}.png`), fullPage: true });

      routeReport.computedStyles1366 = await sampleComputedStyles(page, slug);

      // Interaction states: hover + focus on first few visible buttons
      // (scoped to main content, same reasoning as tryOpenDialog above)
      const btns = await page.locator('main[role="main"] button:visible').all();
      const sampleBtns = btns.slice(0, 5);
      const states = [];
      for (let i = 0; i < sampleBtns.length; i++) {
        try {
          const box = await sampleBtns[i].boundingBox();
          if (!box) continue;
          await sampleBtns[i].hover({ timeout: 1500 });
          await page.waitForTimeout(150);
          const hoverStyle = await sampleBtns[i].evaluate((el) => {
            const cs = getComputedStyle(el);
            return { backgroundColor: cs.backgroundColor, color: cs.color, cursor: cs.cursor, opacity: cs.opacity };
          });
          const disabled = await sampleBtns[i].isDisabled().catch(() => false);
          const label = (await sampleBtns[i].innerText({ timeout: 500 }).catch(() => '')) || '';
          states.push({ index: i, label: label.trim().slice(0, 30), disabled, hoverStyle });
        } catch {
          // skip flaky elements
        }
      }
      routeReport.buttonStates = states;
      if (sampleBtns.length > 0) {
        await page.screenshot({
          path: path.join(OUT_DIR, `${slug}-hover-state.png`),
          fullPage: false,
        });
      }

      // Try to open the primary create/new dialog
      const opened = await tryOpenDialog(page, slug).catch((e) => {
        routeReport.errors.push(`dialog-probe: ${String(e)}`);
        return null;
      });
      if (opened) {
        const safeName = opened.label.replace(/[^a-z0-9]+/gi, '-').toLowerCase() || 'dialog';
        await page.screenshot({
          path: path.join(OUT_DIR, `${slug}-dialog-${safeName}.png`),
          fullPage: true,
        });
        routeReport.dialogOpened = opened.label;
        routeReport.dialogWasModal = opened.hadModal;
        if (opened.hadModal) {
          await page.keyboard.press('Escape').catch(() => {});
          await page.waitForTimeout(300);
        }
      } else {
        routeReport.dialogOpened = null;
      }

      // Reset to base route, then re-screenshot at 1920 width
      await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' });
      await settle(page);
      await page.setViewportSize({ width: 1920, height: 1080 });
      await page.waitForTimeout(300);
      await page.screenshot({ path: path.join(OUT_DIR, `${slug}-1920.png`), fullPage: true });
      routeReport.computedStyles1920 = await sampleComputedStyles(page, slug);
      await page.setViewportSize({ width: 1366, height: 900 });
    } catch (e) {
      routeReport.errors.push(String(e));
      console.error(`[audit] ERROR on ${route}:`, e.message || e);
    }
    report[slug] = routeReport;
  }

  report._consoleErrors = consoleErrors.slice(0, 200);
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
  console.log(`[audit] report written to ${REPORT_PATH}`);

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
