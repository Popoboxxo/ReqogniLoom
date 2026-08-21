// Standalone follow-up accessibility audit (NOT part of the Playwright test
// suite — run manually via `node a11y-followup.js`, never via `playwright
// test` / `npm run test:e2e`). Covers what the first WCAG audit
// (docs/GESAMTTEST_BERICHT_2026-08-21.md §5) explicitly did not:
//   Teil A — 3 canvas-/tab-panel dialogs (StateDialog, TransitionDialog,
//            EnforcementFlipDialog) on the default dark theme.
//   Teil B — 4 additional theme variants (light, bauhaus, nordic, sepia) on
//            3 anchor points each (/, /requirements, requirement-create dialog).
//
// Usage: node a11y-followup.js
// Requires: frontend dev server on http://localhost:5173, backend on
// http://localhost:8001, seeded demo tenant (admin / admin12345).

const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const OUT_DIR = path.resolve(__dirname, '..', 'docs', 'test-reports', 'design-audit-screenshots');
const AXE_SCRIPT = path.resolve(__dirname, 'node_modules', 'axe-core', 'axe.min.js');
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa'];

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

async function runAxe(page, contextSelector) {
  await page.addScriptTag({ path: AXE_SCRIPT });
  const result = await page.evaluate(
    async ({ tags, sel }) => {
      const opts = { runOnly: { type: 'tag', values: tags } };
      const context = sel ? { include: [[sel]] } : document;
      // eslint-disable-next-line no-undef
      return await axe.run(context, opts);
    },
    { tags: AXE_TAGS, sel: contextSelector || null }
  );
  return result;
}

function summarizeAxe(result) {
  const byImpact = { critical: 0, serious: 0, moderate: 0, minor: 0 };
  const details = result.violations.map((v) => {
    byImpact[v.impact || 'minor'] = (byImpact[v.impact || 'minor'] || 0) + 1;
    const isContrast = v.id === 'color-contrast';
    return {
      id: v.id,
      impact: v.impact,
      help: v.help,
      wcag: (v.tags || []).filter((t) => t.startsWith('wcag')),
      nodes: v.nodes.slice(0, 8).map((n) => {
        const base = { target: n.target.join(' ') };
        if (isContrast) {
          const d = n.any?.[0]?.data;
          if (d) {
            base.contrastData = {
              fgColor: d.fgColor,
              bgColor: d.bgColor,
              contrastRatio: d.contrastRatio,
              expectedContrastRatio: d.expectedContrastRatio,
              fontSize: d.fontSize,
              fontWeight: d.fontWeight,
            };
          }
        }
        return base;
      }),
      nodeCount: v.nodes.length,
    };
  });
  return {
    violations: result.violations.length,
    byImpact,
    details,
  };
}

async function keyboardProbe(page, dialogSelector, triggerSelector) {
  // Tab order sample + focus trap + Escape close + focus restore.
  const probe = { tabSequence: [], trapHeld: null, escapeCloses: null, focusRestored: null, errors: [] };
  try {
    const focusables = await page.locator(
      `${dialogSelector} button:visible, ${dialogSelector} input:visible, ${dialogSelector} select:visible, ${dialogSelector} textarea:visible, ${dialogSelector} a[href]:visible, ${dialogSelector} [tabindex]:not([tabindex="-1"]):visible`
    ).all();
    const activeInit = await page.evaluate(() => document.activeElement?.getAttribute('data-testid') || document.activeElement?.tagName);
    probe.initialFocus = activeInit;

    for (let i = 0; i < focusables.length + 2; i++) {
      await page.keyboard.press('Tab');
      const active = await page.evaluate(() => {
        const el = document.activeElement;
        return {
          tag: el?.tagName,
          testid: el?.getAttribute('data-testid'),
          insideDialog: !!el?.closest('[role="dialog"]'),
        };
      });
      probe.tabSequence.push(active);
    }
    // Trap check: after cycling one extra Tab beyond the number of focusables,
    // focus should still be inside the dialog.
    const last = probe.tabSequence[probe.tabSequence.length - 1];
    probe.trapHeld = !!last?.insideDialog;

    // Escape closes
    await page.keyboard.press('Escape');
    await page.waitForTimeout(300);
    const dialogVisible = await page.locator(dialogSelector).first().isVisible().catch(() => false);
    probe.escapeCloses = !dialogVisible;

    // Focus restore to trigger
    if (triggerSelector) {
      const active = await page.evaluate(() => document.activeElement?.getAttribute('data-testid'));
      const triggerTestId = await page.locator(triggerSelector).first().getAttribute('data-testid').catch(() => null);
      probe.focusRestored = active === triggerTestId;
      probe.focusAfterCloseTestId = active;
      probe.triggerTestId = triggerTestId;
    }
  } catch (e) {
    probe.errors.push(String(e));
  }
  return probe;
}

async function partA(page, report) {
  console.log('[a11y-followup] Teil A: canvas/tab-panel dialogs');

  // Playwright's default context has no explicit colorScheme, which Chromium
  // resolves to `prefers-color-scheme: light` — so without forcing it, the
  // app's own light/dark auto-detect (ThemeContext.resolveInitialTheme)
  // would silently test the LIGHT theme, not the "default Dark-Theme" the
  // task asks for. Force it explicitly via the same localStorage key the
  // app itself uses.
  await page.evaluate(() => window.localStorage.setItem('reqflow-theme', 'dark'));
  report._themeForceNote =
    "Playwright-Kontext emuliert standardmäßig prefers-color-scheme:light; ohne explizites Setzen von localStorage['reqflow-theme']='dark' hätte Teil A versehentlich das Light-Theme getestet, nicht das angeforderte Default-Dark-Theme.";

  // --- A1: StateDialog (edit) via /workflows ---
  try {
    await page.goto(`${FRONTEND_URL}/workflows`, { waitUntil: 'domcontentloaded' });
    await settle(page);
    await page.screenshot({ path: path.join(OUT_DIR, 'a11y-followup-workflows-canvas.png'), fullPage: true });

    // enable edit mode
    const editToggle = page.locator('[data-testid="workflow-edit-toggle"]');
    if (await editToggle.count()) {
      const checked = await editToggle.getAttribute('aria-checked');
      if (checked !== 'true') {
        await editToggle.click();
        await page.waitForTimeout(400);
      }
    }

    const stateNode = page.locator('[data-testid^="workflow-state-node-"]').first();
    await stateNode.waitFor({ state: 'visible', timeout: 10000 });
    const stateNodeTestId = await stateNode.getAttribute('data-testid');
    await stateNode.click();
    await page.waitForTimeout(300);

    const editStateBtn = page.locator('[data-testid="workflow-inspector-edit-state"]');
    await editStateBtn.waitFor({ state: 'visible', timeout: 5000 });
    await editStateBtn.click();
    await page.waitForTimeout(500);

    const stateDialogSel = '[data-testid="workflow-state-dialog"]';
    await page.locator(stateDialogSel).waitFor({ state: 'visible', timeout: 5000 });
    await page.screenshot({ path: path.join(OUT_DIR, 'a11y-followup-state-dialog.png'), fullPage: true });

    const axeResult = await runAxe(page, stateDialogSel);
    const kbProbe = await keyboardProbe(page, stateDialogSel, `[data-testid="${stateNodeTestId}"]`);

    report.stateDialog = {
      trigger: `click ${stateNodeTestId} -> click workflow-inspector-edit-state`,
      axe: summarizeAxe(axeResult),
      keyboard: kbProbe,
    };
  } catch (e) {
    report.stateDialog = { error: String(e) };
    console.error('[a11y-followup] StateDialog ERROR:', e.message || e);
  }

  // --- A2: TransitionDialog (edit) via /workflows ---
  try {
    await page.goto(`${FRONTEND_URL}/workflows`, { waitUntil: 'domcontentloaded' });
    await settle(page);
    const editToggle = page.locator('[data-testid="workflow-edit-toggle"]');
    if (await editToggle.count()) {
      const checked = await editToggle.getAttribute('aria-checked');
      if (checked !== 'true') {
        await editToggle.click();
        await page.waitForTimeout(400);
      }
    }

    const edge = page.locator('[data-testid^="workflow-transition-edge-"]').first();
    await edge.waitFor({ state: 'visible', timeout: 10000 });
    const edgeTestId = await edge.getAttribute('data-testid');
    // The edge label div has tabIndex=-1 / role=button but the actual click
    // handler lives on ReactFlow's edge path element (onEdgeClick) — click
    // the visible label, which sits over the wide invisible hit-path.
    await edge.click({ force: true });
    await page.waitForTimeout(300);

    const editTransBtn = page.locator('[data-testid="workflow-inspector-edit-transition"]');
    await editTransBtn.waitFor({ state: 'visible', timeout: 5000 });
    await editTransBtn.click();
    await page.waitForTimeout(500);

    const transDialogSel = '[data-testid="workflow-transition-dialog"]';
    await page.locator(transDialogSel).waitFor({ state: 'visible', timeout: 5000 });
    await page.screenshot({ path: path.join(OUT_DIR, 'a11y-followup-transition-dialog.png'), fullPage: true });

    const axeResult = await runAxe(page, transDialogSel);
    const kbProbe = await keyboardProbe(page, transDialogSel, `[data-testid="${edgeTestId}"]`);

    report.transitionDialog = {
      trigger: `click ${edgeTestId} -> click workflow-inspector-edit-transition`,
      edgeKeyboardReachable: null, // filled below
      axe: summarizeAxe(axeResult),
      keyboard: kbProbe,
    };

    // Extra: is the edge label itself keyboard-reachable (Tab) given tabIndex=-1?
    report.transitionDialog.edgeKeyboardReachable = await page.evaluate((sel) => {
      const el = document.querySelector(sel);
      return el ? el.tabIndex : null;
    }, `[data-testid="${edgeTestId}"]`);
  } catch (e) {
    report.transitionDialog = { error: String(e) };
    console.error('[a11y-followup] TransitionDialog ERROR:', e.message || e);
  }

  // --- A3: EnforcementFlipDialog via /system-settings ---
  try {
    await page.goto(`${FRONTEND_URL}/system-settings`, { waitUntil: 'domcontentloaded' });
    await settle(page);
    await page.screenshot({ path: path.join(OUT_DIR, 'a11y-followup-system-settings.png'), fullPage: true });

    const permTab = page.locator('[data-testid="system-settings-tab-permission-defaults"]');
    if (await permTab.count()) {
      await permTab.click();
      await settle(page);
      await page.waitForTimeout(500);
    }
    await page.screenshot({ path: path.join(OUT_DIR, 'a11y-followup-permission-defaults-tab.png'), fullPage: true });

    // NOTE: deliberately does NOT click "Roll Back to Shadow" — that is a
    // real, backend-persisted state mutation (enforcement_mode DB row) gated
    // behind a native window.confirm(), out of scope for a read-only a11y
    // scan. If enforcement is already "authoritative" the live flip dialog
    // is unreachable this run; see the static jsdom+axe render check instead
    // (frontend/src/test, EnforcementFlipDialog rendered directly with a
    // mocked API module — no backend call).
    const sideEffectNote = null;
    const flipBtn = page.locator('[data-testid="enforcement-flip-btn"]');
    const flipBtnCount = await flipBtn.count();
    if (flipBtnCount === 0) {
      report.enforcementFlipDialog = { error: 'enforcement-flip-btn not found/visible on /system-settings even after rollback attempt', sideEffectNote };
    } else {
      await flipBtn.scrollIntoViewIfNeeded();
      await flipBtn.click();
      await page.waitForTimeout(600);

      const dialogSel = '[role="dialog"]';
      await page.locator(dialogSel).first().waitFor({ state: 'visible', timeout: 5000 });
      await page.screenshot({ path: path.join(OUT_DIR, 'a11y-followup-enforcement-flip-dialog.png'), fullPage: true });

      const axeResult = await runAxe(page, dialogSel);
      const kbProbe = await keyboardProbe(page, dialogSel, '[data-testid="enforcement-flip-btn"]');

      report.enforcementFlipDialog = {
        trigger: 'click enforcement-flip-btn',
        sideEffectNote,
        axe: summarizeAxe(axeResult),
        keyboard: kbProbe,
      };
    }
  } catch (e) {
    report.enforcementFlipDialog = { error: String(e) };
    console.error('[a11y-followup] EnforcementFlipDialog ERROR:', e.message || e);
  }
}

const THEMES = ['light', 'bauhaus', 'nordic', 'sepia'];

async function setTheme(page, themeId) {
  await page.evaluate((id) => {
    window.localStorage.setItem('reqflow-theme', id);
  }, themeId);
}

async function openRequirementCreateDialog(page) {
  const scope = page.locator('main[role="main"]');
  const buttons = await scope.locator('button:visible, a[role="button"]:visible').all();
  const primaryRe = /^(neue?r?s?\s|new\s)/i;
  const fallbackRe = /(neu|new|hinzufügen|erstellen|anlegen|create|add|\+ )/i;
  let best = null;
  for (const btn of buttons) {
    let label = '';
    try {
      label = (await btn.innerText({ timeout: 1000 })) || '';
    } catch {
      continue;
    }
    if (primaryRe.test(label.trim())) {
      best = btn;
      break;
    }
    if (!best && fallbackRe.test(label)) best = btn;
  }
  if (!best) return false;
  await best.click({ timeout: 3000 });
  await page.waitForTimeout(600);
  return true;
}

async function partB(page, report) {
  console.log('[a11y-followup] Teil B: theme variants');
  report.themes = {};

  for (const themeId of THEMES) {
    console.log(`[a11y-followup] theme: ${themeId}`);
    const themeReport = {};
    try {
      // Anchor 1: Dashboard
      await page.goto(`${FRONTEND_URL}/`, { waitUntil: 'domcontentloaded' });
      await setTheme(page, themeId);
      await page.reload({ waitUntil: 'domcontentloaded' });
      await settle(page);
      const activeTheme = await page.evaluate(() => document.documentElement.dataset.theme);
      await page.screenshot({ path: path.join(OUT_DIR, `a11y-followup-theme-${themeId}-dashboard.png`), fullPage: true });
      const dashAxe = await runAxe(page);
      themeReport.dashboard = { activeTheme, axe: summarizeAxe(dashAxe) };

      // Anchor 2: /requirements list
      await page.goto(`${FRONTEND_URL}/requirements`, { waitUntil: 'domcontentloaded' });
      await settle(page);
      await page.screenshot({ path: path.join(OUT_DIR, `a11y-followup-theme-${themeId}-requirements.png`), fullPage: true });
      const reqAxe = await runAxe(page);
      themeReport.requirements = { axe: summarizeAxe(reqAxe) };

      // Anchor 3: requirement-create dialog
      const opened = await openRequirementCreateDialog(page);
      if (opened) {
        await page.screenshot({ path: path.join(OUT_DIR, `a11y-followup-theme-${themeId}-requirement-dialog.png`), fullPage: true });
        const dlgAxe = await runAxe(page);
        themeReport.requirementDialog = { opened: true, axe: summarizeAxe(dlgAxe) };
        // close if a real modal
        const modal = page.locator('[role="dialog"]').first();
        if (await modal.isVisible().catch(() => false)) {
          await page.keyboard.press('Escape').catch(() => {});
          await page.waitForTimeout(300);
        }
      } else {
        themeReport.requirementDialog = { opened: false };
      }
    } catch (e) {
      themeReport.error = String(e);
      console.error(`[a11y-followup] theme ${themeId} ERROR:`, e.message || e);
    }
    report.themes[themeId] = themeReport;
  }
}

async function main() {
  ensureDir(OUT_DIR);
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();

  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  console.log('[a11y-followup] logging in...');
  await login(page);

  const report = { generatedAt: new Date().toISOString() };

  const part = process.env.AUDIT_PART; // 'A' | 'B' | undefined (both)
  if (!part || part === 'A') await partA(page, report);
  if (!part || part === 'B') await partB(page, report);

  report._consoleErrors = consoleErrors.slice(0, 200);

  const outPath = path.join(OUT_DIR, 'a11y-followup-full.json');
  fs.writeFileSync(outPath, JSON.stringify(report, null, 2));
  console.log(`[a11y-followup] report written to ${outPath}`);

  await browser.close();
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
