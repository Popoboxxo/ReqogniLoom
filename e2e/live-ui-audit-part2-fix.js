// Targeted re-run of the subset of live-ui-audit-part2.js attempts that
// depended on the buggy CREATE_BTN_PRIMARY_RE (fixed there now) — re-verifies
// every "OK" that was actually a silent no-op, instead of trusting the first
// pass's false positives. See live-ui-audit-part2.js's regex comment for the bug.

const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://172.20.5.64:5173';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin';
const OUT_DIR = path.resolve(__dirname, '..', 'docs', 'test-reports', 'live-ui-audit-2026-10-19');
const SHOT_DIR = path.join(OUT_DIR, 'screenshots-part2');
const REPORT_PATH = path.join(OUT_DIR, 'report-part2-fix.json');

function ensureDir(p) { fs.mkdirSync(p, { recursive: true }); }

async function login(page) {
  await page.goto(`${FRONTEND_URL}/login`);
  await page.fill('#username-input', 'admin');
  await page.fill('#password-input', ADMIN_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
}
async function settle(page) {
  try { await page.waitForLoadState('networkidle', { timeout: 8000 }); } catch {}
  await page.waitForTimeout(400);
}

const CREATE_BTN_PRIMARY_RE = /^[+\s]*(neue?r?s?\s|new\s)/i;

async function clickByText(page, scopeSelector, re) {
  const scope = page.locator(scopeSelector);
  const buttons = await scope.locator('button:visible, a[role="button"]:visible').all();
  for (const btn of buttons) {
    let label = '';
    try { label = (await btn.innerText({ timeout: 800 })) || ''; } catch { continue; }
    if (re.test(label.trim())) {
      await btn.click({ timeout: 3000 }).catch(() => {});
      return label.trim();
    }
  }
  return null;
}

async function domFactsForDialog(page, dialogSel) {
  try {
    return await page.evaluate((sel) => {
      const dlg = document.querySelector(sel);
      if (!dlg) return null;
      const btns = Array.from(dlg.querySelectorAll('button')).filter((b) => {
        const r = b.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      });
      const footer = btns.slice(-3).sort((a, b) => a.getBoundingClientRect().x - b.getBoundingClientRect().x)
        .map((b) => ({ text: (b.textContent || '').trim().slice(0, 30), className: b.className }));
      const active = document.activeElement;
      return {
        footerButtons: footer,
        activeElementTag: active ? active.tagName : null,
        activeElementTestId: active ? active.getAttribute('data-testid') : null,
        hasAriaModal: dlg.getAttribute('aria-modal'),
        role: dlg.getAttribute('role'),
      };
    }, dialogSel);
  } catch (e) { return { error: String(e) }; }
}

async function attempt(report, id, fn) {
  const entry = { id, ok: false };
  try {
    const result = await fn();
    entry.ok = true;
    Object.assign(entry, result || {});
  } catch (e) {
    entry.ok = false;
    entry.reason = String(e).slice(0, 300);
  }
  report.push(entry);
  console.log(`[fix] ${id}: ${entry.ok ? 'OK' : 'SKIP/FAIL - ' + entry.reason}`);
}
async function shot(page, name) {
  const p = path.join(SHOT_DIR, `${name}.png`);
  await page.screenshot({ path: p, fullPage: true });
  return `screenshots-part2/${name}.png`;
}
async function closeAnyDialog(page) { await page.keyboard.press('Escape').catch(() => {}); await page.waitForTimeout(250); }

async function main() {
  ensureDir(SHOT_DIR);
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();
  console.log('[fix] logging in...');
  await login(page);
  await settle(page);
  const goto = async (route) => { await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' }); await settle(page); };

  const dialogReport = [];
  // re-verify every clickByText-driven create dialog
  const SIMPLE_CREATES = [
    ['requirements-create', '/requirements', '[role="dialog"]'],
    ['architecture-create', '/architecture', '[data-testid="arch-new-dialog"]'],
    ['adrs-create', '/adrs', '[data-testid="adr-create-dialog"]'],
    ['risks-create', '/risks', '[data-testid="risk-create-dialog"]'],
    ['issues-create', '/issues', '[data-testid="issue-create-dialog"]'],
    ['testcases-create', '/testcases', '[data-testid="tc-create-dialog"]'],
    ['needs-create', '/needs', '[data-testid="need-new-dialog"]'],
    ['goals-create', '/goals', '[data-testid="goal-form-dialog"]'],
    ['glossary-create', '/glossary', '[role="dialog"]'],
    ['icds-create', '/icds', '[data-testid="create-icd-dialog"]'],
    ['diagrams-create', '/diagrams', '[data-testid="create-diagram-dialog"]'],
    ['baselines-create', '/baselines', '[data-testid="baseline-create-dialog"]'],
    ['test-runs-create', '/test-runs', '[data-testid="testrun-create-dialog"]'],
    ['attributes-create', '/attributes', '[data-testid="attribute-create-dialog"]'],
    ['memory-add-fact', '/memory', '[data-testid="memory-add-fact-dialog"]'],
    ['user-management-create', '/user-management', '[data-testid="user-management-create-dialog"]'],
  ];
  for (const [id, route, dialogSel] of SIMPLE_CREATES) {
    await attempt(dialogReport, id, async () => {
      await goto(route);
      const clickedLabel = await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
      if (!clickedLabel) throw new Error('auch mit korrigierter Regex kein "+ Neue..."-Button gefunden — echte Lücke, nicht Script-Bug');
      await page.waitForTimeout(700);
      const facts = await domFactsForDialog(page, dialogSel);
      const screenshot = await shot(page, `${id}-REVERIFIED`);
      const actuallyOpened = !!(facts && (facts.footerButtons?.length || facts.activeElementTestId));
      await closeAnyDialog(page);
      if (!actuallyOpened) throw new Error(`Button "${clickedLabel}" geklickt, aber Dialog-Selektor ${dialogSel} fand keinen befüllten Dialog (facts=${JSON.stringify(facts)})`);
      return { screenshot, facts, clickedLabel };
    });
  }

  const buttonPosReport = [];
  const LIST_ROUTES = [
    ['requirements', '/requirements'], ['adrs', '/adrs'], ['risks', '/risks'], ['issues', '/issues'],
    ['testcases', '/testcases'], ['needs', '/needs'], ['goals', '/goals'], ['test-runs', '/test-runs'],
    ['icds', '/icds'], ['diagrams', '/diagrams'], ['baselines', '/baselines'],
  ];
  for (const [slug, route] of LIST_ROUTES) {
    await attempt(buttonPosReport, `btnpos-${slug}`, async () => {
      await goto(route);
      const scope = page.locator('main[role="main"]');
      const buttons = await scope.locator('button:visible, a[role="button"]:visible').all();
      let primary = null;
      for (const btn of buttons) {
        let text = '';
        try { text = (await btn.innerText({ timeout: 500 })) || ''; } catch { continue; }
        if (CREATE_BTN_PRIMARY_RE.test(text.trim())) {
          const box = await btn.boundingBox();
          primary = { text: text.trim(), box };
          break;
        }
      }
      const firstRow = page.locator('main[role="main"] tbody tr, main[role="main"] li').first();
      let rowActionsBox = null;
      if (await firstRow.count()) {
        const rowBtns = await firstRow.locator('button:visible').all();
        if (rowBtns.length) {
          const lastBtn = rowBtns[rowBtns.length - 1];
          rowActionsBox = await lastBtn.boundingBox();
        }
      }
      const viewport = page.viewportSize();
      if (!primary) throw new Error('kein primärer "+ Neue..."-Button in main gefunden (auch nach Regex-Fix)');
      return {
        primaryButton: { text: primary.text, x: primary.box?.x, y: primary.box?.y, width: primary.box?.width, rightAligned: (viewport.width - (primary.box.x + primary.box.width)) < 100 },
        rowActionBox: rowActionsBox,
        viewportWidth: viewport.width,
      };
    });
  }

  const report = { generatedAt: new Date().toISOString(), dialogReport, buttonPosReport };
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
  console.log(`[fix] report written to ${REPORT_PATH}`);
  await browser.close();
}
main().catch((e) => { console.error(e); process.exit(1); });
