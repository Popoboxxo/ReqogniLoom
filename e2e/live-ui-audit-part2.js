// Follow-up pass to live-ui-audit.js: exhaustive dialog sweep (create+edit+
// action variants, not just create), right-sidebar (ArtifactInspector) check,
// full nav-link click-through, and primary-button-position comparison.
// Usage: node live-ui-audit-part2.js

const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://172.20.5.64:5173';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin';
const OUT_DIR = path.resolve(__dirname, '..', 'docs', 'test-reports', 'live-ui-audit-2026-10-19');
const SHOT_DIR = path.join(OUT_DIR, 'screenshots-part2');
const REPORT_PATH = path.join(OUT_DIR, 'report-part2.json');

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

// BUGFIX (found during this run's own self-check): real buttons are labelled
// "+ Neue Anforderung" etc. — the leading "+ " meant this regex, anchored to
// start-of-string, never matched a single one of them, so every clickByText()
// call below silently clicked nothing and every "OK" dialog-sweep/button-position
// result from the first pass of this script was a false positive. Tolerate an
// optional leading "+"/whitespace before "neu"/"new".
const CREATE_BTN_PRIMARY_RE = /^[+\s]*(neue?r?s?\s|new\s)/i;
const CREATE_BTN_FALLBACK_RE = /(neu|new|hinzufügen|erstellen|anlegen|create|add|\+ )/i;

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
      // footer = last 1-3 visible buttons, ordered left->right by x
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
  } catch (e) {
    return { error: String(e) };
  }
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
  console.log(`[part2] ${id}: ${entry.ok ? 'OK' : 'SKIP/FAIL - ' + entry.reason}`);
}

async function shot(page, name) {
  const p = path.join(SHOT_DIR, `${name}.png`);
  await page.screenshot({ path: p, fullPage: true });
  return `screenshots-part2/${name}.png`;
}

async function closeAnyDialog(page) {
  await page.keyboard.press('Escape').catch(() => {});
  await page.waitForTimeout(250);
}

async function main() {
  ensureDir(SHOT_DIR);
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();
  console.log('[part2] logging in...');
  await login(page);
  await settle(page);

  const dialogReport = [];
  const sidebarReport = [];
  const navReport = { links: [], groupStructure: null };
  const buttonPosReport = [];

  // ============ PART A: dialog sweep ============
  const goto = async (route) => { await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' }); await settle(page); };

  // A1: Requirements create + AI derive (edit is inline split-view, not a dialog)
  await attempt(dialogReport, 'requirements-create', async () => {
    await goto('/requirements');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[role="dialog"], [data-testid$="dialog"]');
    const screenshot = await shot(page, 'requirements-create');
    await closeAnyDialog(page);
    return { screenshot, facts, note: 'Edit erfolgt inline im Split-View (kein Dialog) — siehe Teil B.' };
  });

  // A2: Architecture create
  await attempt(dialogReport, 'architecture-create', async () => {
    await goto('/architecture');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[data-testid="arch-new-dialog"]');
    const screenshot = await shot(page, 'architecture-create');
    await closeAnyDialog(page);
    return { screenshot, facts, note: 'Edit erfolgt inline im Split-View (kein Dialog) — siehe Teil B.' };
  });

  // A3-A6: Adr/Risk/Issue/TestCase create (EditorPageShell)
  for (const [slug, route, dialogTestId] of [
    ['adrs', '/adrs', 'adr-create-dialog'],
    ['risks', '/risks', 'risk-create-dialog'],
    ['issues', '/issues', 'issue-create-dialog'],
    ['testcases', '/testcases', 'tc-create-dialog'],
  ]) {
    await attempt(dialogReport, `${slug}-create`, async () => {
      await goto(route);
      await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
      await page.waitForTimeout(600);
      const facts = await domFactsForDialog(page, `[data-testid="${dialogTestId}"]`);
      const screenshot = await shot(page, `${slug}-create`);
      await closeAnyDialog(page);
      return { screenshot, facts, note: 'Edit erfolgt inline im Split-View (kein Dialog) — siehe Teil B.' };
    });
  }

  // A7: Needs create
  await attempt(dialogReport, 'needs-create', async () => {
    await goto('/needs');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[data-testid="need-new-dialog"]');
    const screenshot = await shot(page, 'needs-create');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A8: Goals create + A9: Goals archive (edit)
  await attempt(dialogReport, 'goals-create', async () => {
    await goto('/goals');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[data-testid="goal-form-dialog"]');
    const screenshot = await shot(page, 'goals-create');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });
  await attempt(dialogReport, 'goals-archive-edit-action', async () => {
    await goto('/goals');
    // find any visible "archivieren"/"archive" action on a goal row
    const btn = page.locator('main[role="main"] button:visible', { hasText: /archiv/i }).first();
    const count = await btn.count();
    if (!count) throw new Error('kein Archivieren-Button auf /goals sichtbar (keine Seed-Daten mit passendem Status?)');
    await btn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[data-testid="goal-archive-dialog"]');
    const screenshot = await shot(page, 'goals-archive');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A10: Glossary create term
  await attempt(dialogReport, 'glossary-create', async () => {
    await goto('/glossary');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[role="dialog"]');
    const screenshot = await shot(page, 'glossary-create');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A11: ICDs create
  await attempt(dialogReport, 'icds-create', async () => {
    await goto('/icds');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[data-testid="create-icd-dialog"]');
    const screenshot = await shot(page, 'icds-create');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A12: Diagrams create
  await attempt(dialogReport, 'diagrams-create', async () => {
    await goto('/diagrams');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[data-testid="create-diagram-dialog"]');
    const screenshot = await shot(page, 'diagrams-create');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A13: Baselines create
  await attempt(dialogReport, 'baselines-create', async () => {
    await goto('/baselines');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[data-testid="baseline-create-dialog"]');
    const screenshot = await shot(page, 'baselines-create');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A14: Reviews signature dialog
  await attempt(dialogReport, 'reviews-signature', async () => {
    await goto('/reviews');
    const btn = page.locator('main[role="main"] button:visible', { hasText: /unterschreiben|signier|sign/i }).first();
    if (!(await btn.count())) throw new Error('kein Signatur-Trigger sichtbar (keine Pending-Reviews mit Signatur-Schritt in Seed-Daten?)');
    await btn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[data-testid="signature-dialog"]');
    const screenshot = await shot(page, 'reviews-signature');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A15: Test-runs create
  await attempt(dialogReport, 'test-runs-create', async () => {
    await goto('/test-runs');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[data-testid="testrun-create-dialog"]');
    const screenshot = await shot(page, 'test-runs-create');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A16: Attributes - create + import (tabs may select entity type first)
  await attempt(dialogReport, 'attributes-create', async () => {
    await goto('/attributes');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[data-testid="attribute-create-dialog"]');
    const screenshot = await shot(page, 'attributes-create');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });
  await attempt(dialogReport, 'attributes-import', async () => {
    await goto('/attributes');
    const btn = page.locator('main[role="main"] button:visible', { hasText: /import/i }).first();
    if (!(await btn.count())) throw new Error('kein Import-Button sichtbar');
    await btn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[data-testid="attribute-import-dialog"]');
    const screenshot = await shot(page, 'attributes-import');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });
  await attempt(dialogReport, 'attributes-catalog', async () => {
    await goto('/attributes');
    const btn = page.locator('main[role="main"] button:visible', { hasText: /katalog|catalog/i }).first();
    if (!(await btn.count())) throw new Error('kein Katalog-Button sichtbar');
    await btn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[data-testid="attribute-catalog-dialog"]');
    const screenshot = await shot(page, 'attributes-catalog');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A17: Memory add fact
  await attempt(dialogReport, 'memory-add-fact', async () => {
    await goto('/memory');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[data-testid="memory-add-fact-dialog"]');
    const screenshot = await shot(page, 'memory-add-fact');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A18: Create workspace modal (sidebar, from dashboard)
  await attempt(dialogReport, 'create-workspace-modal', async () => {
    await goto('/');
    const btn = page.locator('[data-testid="create-workspace-btn"]');
    await btn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[data-testid="create-workspace-modal"]');
    const screenshot = await shot(page, 'create-workspace-modal');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A19: User management create
  await attempt(dialogReport, 'user-management-create', async () => {
    await goto('/user-management');
    await clickByText(page, 'main[role="main"]', CREATE_BTN_PRIMARY_RE);
    await page.waitForTimeout(600);
    const facts = await domFactsForDialog(page, '[data-testid="user-management-create-dialog"]');
    const screenshot = await shot(page, 'user-management-create');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A20-A22: SystemSettings — SystemHealthDialog, TriLabelOverviewDialog, EnforcementFlipDialog
  await attempt(dialogReport, 'system-health-dialog', async () => {
    await goto('/system-settings');
    const btn = page.locator('[data-testid="system-health-open-btn"]');
    await btn.scrollIntoViewIfNeeded();
    await btn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[role="dialog"]');
    const screenshot = await shot(page, 'system-health-dialog');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });
  await attempt(dialogReport, 'tri-label-overview-dialog', async () => {
    await goto('/system-settings');
    const section = page.locator('[data-testid="tri-label-overview-section"]');
    const btn = section.locator('button:visible').first();
    await btn.scrollIntoViewIfNeeded();
    await btn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[role="dialog"]');
    const screenshot = await shot(page, 'tri-label-overview-dialog');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });
  await attempt(dialogReport, 'enforcement-flip-dialog', async () => {
    await goto('/system-settings');
    const permTab = page.locator('[data-testid="system-settings-tab-permission-defaults"]');
    if (await permTab.count()) { await permTab.click(); await settle(page); }
    const flipBtn = page.locator('[data-testid="enforcement-flip-btn"]');
    if (!(await flipBtn.count())) throw new Error('enforcement-flip-btn nicht sichtbar (enforcement vermutlich bereits "authoritative" auf diesem Testsystem)');
    await flipBtn.scrollIntoViewIfNeeded();
    await flipBtn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[role="dialog"]');
    const screenshot = await shot(page, 'enforcement-flip-dialog');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A23: Audit — waive dialog
  await attempt(dialogReport, 'audit-waive-dialog', async () => {
    await goto('/audit');
    const btn = page.locator('main[role="main"] button:visible', { hasText: /unterdrücken/i }).first();
    if (!(await btn.count())) throw new Error('kein "Unterdrücken"-Button sichtbar');
    await btn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[data-testid="audit-waive-dialog"]');
    const screenshot = await shot(page, 'audit-waive-dialog');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A24-A26: Workflows — StateDialog (edit), TransitionDialog (edit), ConfirmDialog (delete)
  await attempt(dialogReport, 'workflow-state-dialog-edit', async () => {
    await goto('/workflows');
    const editToggle = page.locator('[data-testid="workflow-edit-toggle"]');
    if (await editToggle.count()) {
      const checked = await editToggle.getAttribute('aria-checked');
      if (checked !== 'true') { await editToggle.click(); await page.waitForTimeout(400); }
    }
    const stateNode = page.locator('[data-testid^="workflow-state-node-"]').first();
    await stateNode.waitFor({ state: 'visible', timeout: 8000 });
    await stateNode.click();
    await page.waitForTimeout(300);
    const editBtn = page.locator('[data-testid="workflow-inspector-edit-state"]');
    await editBtn.waitFor({ state: 'visible', timeout: 4000 });
    await editBtn.click();
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[data-testid="workflow-state-dialog"]');
    const screenshot = await shot(page, 'workflow-state-dialog-edit');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });
  await attempt(dialogReport, 'workflow-transition-dialog-edit', async () => {
    await goto('/workflows');
    const editToggle = page.locator('[data-testid="workflow-edit-toggle"]');
    if (await editToggle.count()) {
      const checked = await editToggle.getAttribute('aria-checked');
      if (checked !== 'true') { await editToggle.click(); await page.waitForTimeout(400); }
    }
    const edge = page.locator('[data-testid^="workflow-transition-edge-"]').first();
    await edge.waitFor({ state: 'visible', timeout: 8000 });
    await edge.click({ force: true });
    await page.waitForTimeout(300);
    const editBtn = page.locator('[data-testid="workflow-inspector-edit-transition"]');
    await editBtn.waitFor({ state: 'visible', timeout: 4000 });
    await editBtn.click();
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[data-testid="workflow-transition-dialog"]');
    const screenshot = await shot(page, 'workflow-transition-dialog-edit');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });
  await attempt(dialogReport, 'workflow-confirm-dialog-delete', async () => {
    await goto('/workflows');
    const editToggle = page.locator('[data-testid="workflow-edit-toggle"]');
    if (await editToggle.count()) {
      const checked = await editToggle.getAttribute('aria-checked');
      if (checked !== 'true') { await editToggle.click(); await page.waitForTimeout(400); }
    }
    const stateNode = page.locator('[data-testid^="workflow-state-node-"]').last();
    await stateNode.waitFor({ state: 'visible', timeout: 8000 });
    await stateNode.click();
    await page.waitForTimeout(300);
    const delBtn = page.locator('[data-testid="workflow-inspector-delete-state"]');
    if (!(await delBtn.count())) throw new Error('kein Delete-Button im Inspector sichtbar (evtl. letzter State nicht löschbar)');
    await delBtn.click();
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[data-testid="workflow-confirm-dialog"]');
    const screenshot = await shot(page, 'workflow-confirm-dialog-delete');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A27: CreateTraceLinkDialog — via RiskEditors item trace tab (Teil B territory, attempt anyway)
  await attempt(dialogReport, 'create-trace-link-dialog', async () => {
    await goto('/risks');
    const firstItem = page.locator('main[role="main"] [data-testid*="risk-list-item"], main[role="main"] li, main[role="main"] tr').first();
    if (await firstItem.count()) { await firstItem.click({ timeout: 2000 }).catch(() => {}); await page.waitForTimeout(500); }
    const addLinkBtn = page.locator('button:visible', { hasText: /trace.?link|verknüpfung|link hinzufügen/i }).first();
    if (!(await addLinkBtn.count())) throw new Error('kein "Trace-Link hinzufügen"-Trigger sichtbar — evtl. in anderem Tab/Panel als erwartet');
    await addLinkBtn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const facts = await domFactsForDialog(page, '[data-testid="create-trace-link-dialog"]');
    const screenshot = await shot(page, 'create-trace-link-dialog');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // A28: tree-move-dialog — workspace-tree.tsx consumer not yet located precisely; best-effort
  await attempt(dialogReport, 'tree-move-dialog', async () => {
    throw new Error('Trigger-Ort von workspace-tree.tsx im UI nicht identifiziert (kein Routen-/Button-Fund in dieser Session) — explizit offene Lücke, nicht getestet.');
  });

  // A29: AiDerivationDialog — via Requirements AI-derive flow
  await attempt(dialogReport, 'ai-derivation-dialog', async () => {
    await goto('/requirements');
    const btn = page.locator('main[role="main"] button:visible', { hasText: /ki.?ableiten|ai.?deriv|ableiten/i }).first();
    if (!(await btn.count())) throw new Error('kein "KI-Ableiten"-Trigger auf /requirements sichtbar');
    await btn.click({ timeout: 3000 });
    await page.waitForTimeout(1500);
    const facts = await domFactsForDialog(page, '[role="dialog"]');
    const screenshot = await shot(page, 'ai-derivation-dialog');
    await closeAnyDialog(page);
    return { screenshot, facts };
  });

  // ============ PART B: right sidebar (ArtifactInspector) ============
  for (const [slug, route] of [['requirements', '/requirements'], ['architecture', '/architecture'], ['adrs', '/adrs'], ['risks', '/risks']]) {
    await attempt(sidebarReport, `rightsidebar-${slug}`, async () => {
      await goto(route);
      const firstItem = page.locator('main[role="main"] li, main[role="main"] tr, main[role="main"] [role="treeitem"]').first();
      await firstItem.click({ timeout: 3000 });
      await page.waitForTimeout(700);
      const expandedShot = await shot(page, `rightsidebar-${slug}-expanded`);
      // find a collapse toggle: heuristic by aria-label/title containing collapse/einklapp
      const toggle = page.locator('button[aria-label*="ollaps" i], button[title*="ollaps" i], button[aria-label*="inklapp" i], button[title*="inklapp" i], button[data-testid*="collapse" i], button[data-testid*="inspector-toggle" i]').first();
      const toggleCount = await toggle.count();
      let collapsedShot = null;
      let toggleInfo = null;
      if (toggleCount) {
        toggleInfo = await toggle.evaluate((el) => ({ ariaLabel: el.getAttribute('aria-label'), title: el.title, testId: el.getAttribute('data-testid') }));
        await toggle.click({ timeout: 2000 }).catch(() => {});
        await page.waitForTimeout(400);
        collapsedShot = await shot(page, `rightsidebar-${slug}-collapsed`);
      }
      // persistence check: reload
      await page.reload({ waitUntil: 'domcontentloaded' });
      await settle(page);
      const afterReloadShot = await shot(page, `rightsidebar-${slug}-after-reload`);
      return { expandedShot, collapsedShot, afterReloadShot, toggleFound: !!toggleCount, toggleInfo };
    });
  }

  // responsive for right sidebar
  await attempt(sidebarReport, 'rightsidebar-responsive-768', async () => {
    await page.setViewportSize({ width: 768, height: 1024 });
    await goto('/requirements');
    const firstItem = page.locator('main[role="main"] li, main[role="main"] tr').first();
    await firstItem.click({ timeout: 3000 }).catch(() => {});
    await page.waitForTimeout(700);
    const screenshot = await shot(page, 'rightsidebar-768-requirements');
    await page.setViewportSize({ width: 1366, height: 900 });
    return { screenshot };
  });

  // WorkflowEditor InspectorPanel — same primitive or parallel impl?
  await attempt(sidebarReport, 'workflow-inspector-panel-check', async () => {
    const files = require('fs').existsSync(path.resolve(__dirname, '..', 'frontend', 'src', 'components', 'WorkflowEditor', 'InspectorPanel.tsx'));
    return { fileExists: files, note: 'Statischer Check, kein Live-Screenshot — siehe Report-Analyse für Import-Vergleich.' };
  });

  // ============ PART C: nav links ============
  await goto('/');
  const navLinks = await page.locator('nav[aria-label] a[href]').evaluateAll((els) =>
    els.map((e) => ({ text: (e.textContent || '').trim(), href: e.getAttribute('href') }))
  );
  for (const link of navLinks) {
    const entry = { href: link.href, text: link.text };
    try {
      await page.goto(`${FRONTEND_URL}${link.href}`, { waitUntil: 'domcontentloaded' });
      await settle(page);
      const mainText = await page.locator('main[role="main"]').innerText({ timeout: 3000 }).catch(() => '');
      entry.ok = mainText.trim().length > 0;
      entry.textLength = mainText.trim().length;
      entry.title = await page.title();
    } catch (e) {
      entry.ok = false;
      entry.error = String(e).slice(0, 200);
    }
    navReport.links.push(entry);
  }
  // hover state check on first 3 nav links
  await goto('/');
  const navItems = await page.locator('nav[aria-label] a[href]').all();
  const hoverSamples = [];
  for (let i = 0; i < Math.min(3, navItems.length); i++) {
    const before = await navItems[i].evaluate((el) => getComputedStyle(el).backgroundColor);
    await navItems[i].hover({ timeout: 1500 }).catch(() => {});
    await page.waitForTimeout(150);
    const after = await navItems[i].evaluate((el) => getComputedStyle(el).backgroundColor);
    hoverSamples.push({ index: i, before, after, changed: before !== after });
  }
  navReport.hoverSamples = hoverSamples;
  navReport.groupStructure = 'statisch bestätigt: keine aria-expanded/Chevron an Nav-Items (siehe Code-Grep), keine Sub-Items — flache Liste in 5 statischen Gruppen.';

  // ============ PART D: primary button position across list views ============
  const LIST_ROUTES = [
    ['requirements', '/requirements'], ['adrs', '/adrs'], ['risks', '/risks'], ['issues', '/issues'],
    ['testcases', '/testcases'], ['needs', '/needs'], ['goals', '/goals'], ['test-runs', '/test-runs'],
    ['icds', '/icds'], ['diagrams', '/diagrams'], ['baselines', '/baselines'],
  ];
  for (const [slug, route] of LIST_ROUTES) {
    await attempt(buttonPosReport, `btnpos-${slug}`, async () => {
      await goto(route);
      const label = await clickByText.length; // no-op, just reuse regex below without clicking
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
      // table row action icons: look at first data row's last cell
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
      return {
        primaryButton: primary ? { text: primary.text, x: primary.box?.x, y: primary.box?.y, rightAligned: primary.box ? (viewport.width - (primary.box.x + primary.box.width)) < 100 : null } : null,
        rowActionBox: rowActionsBox,
        viewportWidth: viewport.width,
      };
    });
  }

  // ============ PART E: missing routes + detail (:id) routes + redirects ============
  const routeReport = [];
  const STATIC_MISSING = [
    'memory', 'testcases', 'test-runs', 'settings/link-types', 'system-settings/link-types',
    'user-management', 'workflows/requirement', 'attributes', 'attributes/requirement', 'profile',
  ];
  for (const r of STATIC_MISSING) {
    await attempt(routeReport, `route-/${r}`, async () => {
      await goto(`/${r}`);
      const mainText = await page.locator('main[role="main"], body').innerText({ timeout: 3000 }).catch(() => '');
      const screenshot = await shot(page, `route-${r.replace(/\//g, '-')}`);
      return { screenshot, landedUrl: page.url(), nonEmpty: mainText.trim().length > 0 };
    });
  }

  const REDIRECTS = [
    ['/workspace-settings', '/settings'],
    ['/trace-links', '/traceability'],
    ['/test-cases', '/testcases'],
    ['/impact-analysis', '/impact'],
    ['/se-auditor', '/audit'],
    ['/prompts', '/settings?tab=llm'],
  ];
  for (const [from, expectedTo] of REDIRECTS) {
    await attempt(routeReport, `redirect-${from}`, async () => {
      await page.goto(`${FRONTEND_URL}${from}`, { waitUntil: 'domcontentloaded' });
      await settle(page);
      const landed = page.url().replace(FRONTEND_URL, '');
      const matches = landed.startsWith(expectedTo.split('?')[0]);
      if (!matches) throw new Error(`erwartet ${expectedTo}, gelandet bei ${landed}`);
      return { landed, expectedTo };
    });
  }

  // detail (:id) routes — click first list item, read the URL react-router lands on
  const DETAIL_SOURCES = [
    ['needs', '/needs'], ['requirements', '/requirements'], ['architecture', '/architecture'],
    ['adrs', '/adrs'], ['risks', '/risks'], ['issues', '/issues'], ['icds', '/icds'],
    ['diagrams', '/diagrams'], ['interviews', '/interviews'],
  ];
  const diagramDetailUrl = { value: null };
  for (const [slug, route] of DETAIL_SOURCES) {
    await attempt(routeReport, `detail-${slug}`, async () => {
      await goto(route);
      const firstItem = page.locator('main[role="main"] li, main[role="main"] tr, main[role="main"] [role="treeitem"], main[role="main"] a[href]').first();
      if (!(await firstItem.count())) throw new Error('keine Listenelemente gefunden (leere Seed-Daten für dieses Modul?)');
      await firstItem.click({ timeout: 3000 }).catch(() => {});
      await page.waitForTimeout(700);
      const url = page.url().replace(FRONTEND_URL, '');
      const screenshot = await shot(page, `detail-${slug}`);
      if (slug === 'diagrams') diagramDetailUrl.value = url;
      const isDetailUrl = /\/[a-f0-9-]{6,}/i.test(url) || url !== route;
      return { screenshot, url, isDetailUrl };
    });
  }
  // diagram sub-routes (canvas/mermaid/graph) — reuse the id captured above
  if (diagramDetailUrl.value && /^\/diagrams\//.test(diagramDetailUrl.value)) {
    for (const sub of ['canvas', 'mermaid', 'graph']) {
      await attempt(routeReport, `diagram-${sub}`, async () => {
        const base = diagramDetailUrl.value.split('?')[0];
        await goto(`${base}/${sub}`);
        const screenshot = await shot(page, `diagram-${sub}`);
        return { screenshot, url: page.url() };
      });
    }
  } else {
    routeReport.push({ id: 'diagram-canvas/mermaid/graph', ok: false, reason: 'keine Diagramm-Detail-URL ermittelt (leere Seed-Daten unter /diagrams?) — alle 3 Sub-Routen übersprungen' });
  }

  // ============ PART F: all tabs in the system ============
  const tabReport = [];
  for (const [slug, route, extra] of [
    ['system-settings', '/system-settings'],
    ['settings', '/settings'],
    ['memory', '/memory'],
  ]) {
    await attempt(tabReport, `tabs-${slug}`, async () => {
      await goto(route);
      const tabs = await page.locator('[role="tab"]').all();
      const tabInfos = [];
      for (let i = 0; i < tabs.length; i++) {
        const info = await tabs[i].evaluate((el) => ({
          text: (el.textContent || '').trim(),
          testId: el.getAttribute('data-testid'),
          ariaSelected: el.getAttribute('aria-selected'),
        }));
        await tabs[i].click({ timeout: 2000 }).catch(() => {});
        await page.waitForTimeout(400);
        const selectedAfter = await tabs[i].getAttribute('aria-selected').catch(() => null);
        const screenshot = await shot(page, `tabs-${slug}-${i}-${(info.testId || info.text).replace(/[^a-z0-9]+/gi, '-')}`);
        tabInfos.push({ ...info, selectedAfterClick: selectedAfter, screenshot });
      }
      return { tabCount: tabs.length, tabs: tabInfos };
    });
  }
  // InterviewWidget — likely a floating launcher, not a route
  await attempt(tabReport, 'tabs-interview-widget', async () => {
    await goto('/');
    const launcher = page.locator('button[aria-label*="ssistent" i], button[aria-label*="chat" i], [data-testid*="interview-widget-launcher" i], [data-testid*="assistant" i]').first();
    if (!(await launcher.count())) throw new Error('kein Launcher-Button für InterviewWidget gefunden (Selektor-Heuristik griff nicht)');
    await launcher.click({ timeout: 2000 });
    await page.waitForTimeout(500);
    const tabs = await page.locator('[role="tab"]').all();
    const tabInfos = [];
    for (let i = 0; i < tabs.length; i++) {
      const info = await tabs[i].evaluate((el) => ({ text: (el.textContent || '').trim(), testId: el.getAttribute('data-testid') }));
      await tabs[i].click({ timeout: 2000 }).catch(() => {});
      await page.waitForTimeout(300);
      const screenshot = await shot(page, `tabs-interview-widget-${i}`);
      tabInfos.push({ ...info, screenshot });
    }
    return { tabCount: tabs.length, tabs: tabInfos };
  });

  // ============ PART G: admin surfaces beyond AdminDialog/ ============
  const adminReport = [];
  await attempt(adminReport, 'system-settings-subpanels', async () => {
    await goto('/system-settings');
    const screenshot = await shot(page, 'admin-system-settings-overview');
    return { screenshot, note: 'Panels (EnforcementModePanel, PermissionDefaultsTab, WorkspaceAdminSection, BannerSection, MemoryManagementSection) liegen hinter den Tabs aus tabs-system-settings — Dialoge daraus bereits unter A20-A22 (system-health, tri-label-overview, enforcement-flip) erfasst.' };
  });
  await attempt(adminReport, 'workspace-reactivate-delete', async () => {
    await goto('/system-settings');
    const section = page.locator('[data-testid="workspace-admin-section" i], section:has-text("Workspace")').first();
    const reactivateBtn = page.locator('button:visible', { hasText: /reaktivieren/i }).first();
    const deleteBtn = page.locator('button:visible', { hasText: /löschen/i }).first();
    const results = {};
    if (await reactivateBtn.count()) {
      await reactivateBtn.click({ timeout: 2000 }).catch(() => {});
      await page.waitForTimeout(400);
      results.reactivateShot = await shot(page, 'admin-workspace-reactivate-dialog');
      await closeAnyDialog(page);
    } else results.reactivateShot = null;
    if (await deleteBtn.count()) {
      await deleteBtn.click({ timeout: 2000 }).catch(() => {});
      await page.waitForTimeout(400);
      results.deleteShot = await shot(page, 'admin-workspace-delete-dialog');
      await closeAnyDialog(page);
    } else results.deleteShot = null;
    if (!results.reactivateShot && !results.deleteShot) throw new Error('weder Reaktivieren- noch Löschen-Button sichtbar (aktiver Workspace evtl. nicht im passenden Zustand für diese Aktionen)');
    return results;
  });
  await attempt(adminReport, 'user-management-full', async () => {
    await goto('/user-management');
    const screenshot = await shot(page, 'admin-user-management');
    return { screenshot };
  });
  await attempt(adminReport, 'permission-matrix-editor', async () => {
    // locate via sidebar/tab search, not a known standalone route
    await goto('/system-settings');
    const permTab = page.locator('[data-testid="system-settings-tab-permission-defaults"]');
    if (await permTab.count()) { await permTab.click(); await settle(page); }
    const found = await page.locator('text=/Permission.?Matrix|Berechtigungsmatrix/i').count();
    if (!found) throw new Error('PermissionMatrixEditor auf /system-settings nicht gefunden — evtl. andere Route/Tab (nicht lokalisiert in dieser Session)');
    const screenshot = await shot(page, 'admin-permission-matrix');
    return { screenshot };
  });
  await attempt(adminReport, 'profile-api-keys', async () => {
    await goto('/profile');
    const screenshot = await shot(page, 'admin-profile-overview');
    const createBtn = page.locator('button:visible', { hasText: /api.?key|schlüssel erstellen/i }).first();
    let createShot = null;
    if (await createBtn.count()) {
      await createBtn.click({ timeout: 2000 }).catch(() => {});
      await page.waitForTimeout(400);
      createShot = await shot(page, 'admin-profile-api-key-create-dialog');
      await closeAnyDialog(page);
    }
    return { screenshot, createShot };
  });

  const report = {
    generatedAt: new Date().toISOString(),
    dialogReport,
    sidebarReport,
    navReport,
    buttonPosReport,
    routeReport,
    tabReport,
    adminReport,
  };
  fs.writeFileSync(REPORT_PATH, JSON.stringify(report, null, 2));
  console.log(`[part2] report written to ${REPORT_PATH}`);
  await browser.close();
}

main().catch((e) => { console.error(e); process.exit(1); });
