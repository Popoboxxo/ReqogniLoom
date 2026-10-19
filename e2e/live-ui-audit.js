// Standalone LIVE UI audit against a running test deployment (NOT the
// Playwright test suite — run manually via `node live-ui-audit.js`).
// Adapted from design-audit.js's login/settle/tryOpenDialog conventions,
// extended with: raw-ID/undefined text scanning, sidebar measurement,
// and a responsive (mobile/tablet) viewport pass.
//
// Usage: FRONTEND_URL=... ADMIN_PASSWORD=... node live-ui-audit.js
// Defaults target the live test system given for this audit.

const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://172.20.5.64:5173';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin';
const OUT_DIR = path.resolve(__dirname, '..', 'docs', 'test-reports', 'live-ui-audit-2026-10-19');
const SHOT_DIR = path.join(OUT_DIR, 'screenshots');
const REPORT_PATH = path.join(OUT_DIR, 'report.json');

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

// Routes where we also try to open the primary create dialog (subset, not
// every route, to keep the run bounded — picked for module diversity).
const DIALOG_ROUTES = new Set(['requirements', 'risks', 'testcases', 'adrs', 'issues']);

const UUID_RE = /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi;
const BUG_STRING_RE = /\b(undefined|null|NaN|\[object Object\])\b/g;

function ensureDir(p) {
  fs.mkdirSync(p, { recursive: true });
}

async function login(page) {
  await page.goto(`${FRONTEND_URL}/login`);
  await page.fill('#username-input', 'admin');
  await page.fill('#password-input', ADMIN_PASSWORD);
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

function scanText(text, slug, findings) {
  const uuidMatches = [...new Set((text.match(UUID_RE) || []))];
  const bugMatches = [...new Set((text.match(BUG_STRING_RE) || []))];
  if (uuidMatches.length) findings.push({ slug, kind: 'raw-uuid', matches: uuidMatches.slice(0, 10) });
  if (bugMatches.length) findings.push({ slug, kind: 'bug-string', matches: bugMatches.slice(0, 10) });
}

const CREATE_BTN_PRIMARY_RE = /^(neue?r?s?\s|new\s)/i;
const CREATE_BTN_FALLBACK_RE = /(neu|new|hinzufügen|erstellen|anlegen|create|add|\+ )/i;

async function tryOpenDialog(page) {
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
  const best = ordered[0];
  if (!best) return null;
  try {
    await best.btn.click({ timeout: 3000 });
  } catch {
    return null;
  }
  await page.waitForTimeout(700);
  const dialog = page
    .locator('[role="dialog"], .modal, [class*="Dialog" i][class*="overlay" i], [class*="modal" i]')
    .first();
  const hadModal = await dialog.isVisible().catch(() => false);
  return { label: best.label.trim().slice(0, 40), hadModal };
}

async function sidebarInventory(page) {
  const nav = page.locator('nav[aria-label]').first();
  const box = await nav.boundingBox().catch(() => null);
  const links = await page.locator('nav[aria-label] a[href]').evaluateAll((els) =>
    els.map((e) => ({ text: (e.textContent || '').trim(), href: e.getAttribute('href') }))
  );
  const hasBurger = await page.locator('[data-testid="sidebar-burger"]').isVisible().catch(() => false);
  return { boundingBox: box, linkCount: links.length, links, burgerVisible: hasBurger };
}

async function main() {
  ensureDir(SHOT_DIR);
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();

  const consoleErrorsByRoute = {};
  let currentSlug = 'init';
  page.on('console', (msg) => {
    if (msg.type() === 'error' || msg.type() === 'warning') {
      (consoleErrorsByRoute[currentSlug] = consoleErrorsByRoute[currentSlug] || []).push(
        `[${msg.type()}] ${msg.text()}`
      );
    }
  });
  page.on('pageerror', (e) => {
    (consoleErrorsByRoute[currentSlug] = consoleErrorsByRoute[currentSlug] || []).push(
      `[pageerror] ${e.message}`
    );
  });

  const textFindings = [];
  const dialogFindings = {};
  const routeReports = {};

  console.log('[live-audit] logging in...');
  await login(page);

  console.log('[live-audit] sidebar inventory...');
  await settle(page);
  const sidebar = await sidebarInventory(page);
  await page.locator('nav[aria-label]').first().screenshot({ path: path.join(SHOT_DIR, '_sidebar-closeup.png') }).catch(() => {});

  for (const [slug, route] of ROUTES) {
    currentSlug = slug;
    console.log(`[live-audit] route: ${route}`);
    try {
      await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' });
      await settle(page);
      await page.screenshot({ path: path.join(SHOT_DIR, `${slug}.png`), fullPage: true });
      const bodyText = await page.locator('body').innerText().catch(() => '');
      scanText(bodyText, slug, textFindings);
      routeReports[slug] = { route, ok: true };

      if (DIALOG_ROUTES.has(slug)) {
        const opened = await tryOpenDialog(page).catch(() => null);
        if (opened) {
          const dialogText = await page.locator('[role="dialog"], .modal').first().innerText().catch(() => '');
          scanText(dialogText, `${slug}-dialog`, textFindings);
          await page.screenshot({ path: path.join(SHOT_DIR, `${slug}-dialog.png`), fullPage: true });
          dialogFindings[slug] = { label: opened.label, hadModal: opened.hadModal };
          if (opened.hadModal) {
            await page.keyboard.press('Escape').catch(() => {});
            await page.waitForTimeout(300);
          }
        } else {
          dialogFindings[slug] = null;
        }
      }
    } catch (e) {
      routeReports[slug] = { route, ok: false, error: String(e) };
      console.error(`[live-audit] ERROR on ${route}:`, e.message || e);
    }
  }

  // Responsive pass
  const responsive = {};
  for (const [vp, size] of [['mobile-375', { width: 375, height: 800 }], ['tablet-768', { width: 768, height: 1024 }]]) {
    responsive[vp] = {};
    await page.setViewportSize(size);
    for (const slug of ['dashboard', 'requirements']) {
      currentSlug = `${vp}-${slug}`;
      const route = ROUTES.find((r) => r[0] === slug)[1];
      await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' });
      await settle(page);
      await page.screenshot({ path: path.join(SHOT_DIR, `${vp}-${slug}.png`), fullPage: true });
      const burgerVisible = await page.locator('[data-testid="sidebar-burger"]').isVisible().catch(() => false);
      const navVisible = await page.locator('nav[aria-label]').first().isVisible().catch(() => false);
      responsive[vp][slug] = { burgerVisible, navVisible };
    }
  }
  await page.setViewportSize({ width: 1366, height: 900 });

  const report = {
    generatedAt: new Date().toISOString(),
    frontendUrl: FRONTEND_URL,
    sidebar,
    routeReports,
    dialogFindings,
    textFindings,
    responsive,
    consoleErrorsByRoute,
  };
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
  console.log(`[live-audit] report written to ${REPORT_PATH}`);
  console.log(`[live-audit] screenshots in ${SHOT_DIR}`);

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
