// Final targeted wrap-up: RightSidebar (ArtifactInspector) collapse + panels,
// the 3 remaining dialog triggers found via code (not UI guessing), the 3
// detail-route selector fixes, and the write-access seed-data cases.
const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://172.20.5.64:5173';
const ADMIN_PASSWORD = process.env.ADMIN_PASSWORD || 'admin';
const OUT_DIR = path.resolve(__dirname, '..', 'docs', 'test-reports', 'live-ui-audit-2026-10-19');
const SHOT_DIR = path.join(OUT_DIR, 'screenshots-part3');
const REPORT_PATH = path.join(OUT_DIR, 'report-part3.json');

function ensureDir(p) { fs.mkdirSync(p, { recursive: true }); }
async function login(page) {
  await page.goto(`${FRONTEND_URL}/login`);
  await page.fill('#username-input', 'admin');
  await page.fill('#password-input', ADMIN_PASSWORD);
  await page.click('button[type="submit"]');
  await page.waitForURL((url) => !url.pathname.includes('/login'), { timeout: 15000 });
}
async function settle(page) { try { await page.waitForLoadState('networkidle', { timeout: 8000 }); } catch {} await page.waitForTimeout(400); }
async function attempt(report, id, fn) {
  const entry = { id, ok: false };
  try { const r = await fn(); entry.ok = true; Object.assign(entry, r || {}); }
  catch (e) { entry.ok = false; entry.reason = String(e).slice(0, 350); }
  report.push(entry);
  console.log(`[part3] ${id}: ${entry.ok ? 'OK' : 'SKIP/FAIL - ' + entry.reason}`);
}
async function shot(page, name) {
  const p = path.join(SHOT_DIR, `${name}.png`);
  await page.screenshot({ path: p, fullPage: true });
  return `screenshots-part3/${name}.png`;
}
async function closeAnyDialog(page) { await page.keyboard.press('Escape').catch(() => {}); await page.waitForTimeout(250); }

async function main() {
  ensureDir(SHOT_DIR);
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();
  console.log('[part3] logging in...');
  await login(page);
  await settle(page);
  const goto = async (route) => { await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' }); await settle(page); };

  const report = [];

  // ===== 1. RightSidebar (ArtifactInspector) — real toggle this time =====
  for (const [slug, route] of [['requirements', '/requirements'], ['architecture', '/architecture'], ['adrs', '/adrs']]) {
    await attempt(report, `inspector-${slug}`, async () => {
      await goto(route);
      const firstItem = page.locator('main[role="main"] [data-testid][role="button"], main[role="main"] [role="treeitem"]').first();
      await firstItem.click({ timeout: 3000 });
      await page.waitForTimeout(700);
      const inspector = page.locator('[data-testid="artifact-inspector"]');
      const hasInspector = await inspector.count();
      if (!hasInspector) throw new Error('[data-testid="artifact-inspector"] nicht im DOM gefunden');
      const expandedShot = await shot(page, `inspector-${slug}-expanded`);
      const collapseBtn = page.locator('[data-testid="artifact-inspector-collapse"]');
      const collapseCount = await collapseBtn.count();
      let collapsedShot = null, miniIcons = null, reExpandedAfterNav = null;
      if (collapseCount) {
        await collapseBtn.click({ timeout: 2000 });
        await page.waitForTimeout(400);
        collapsedShot = await shot(page, `inspector-${slug}-collapsed`);
        miniIcons = await page.locator('[data-testid="artifact-inspector-collapsed"] [aria-label]').evaluateAll(
          (els) => els.map((e) => e.getAttribute('aria-label'))
        );
        // persistence check: navigate to a different item, see if still collapsed
        const secondItem = page.locator('main[role="main"] [data-testid][role="button"], main[role="main"] [role="treeitem"]').nth(1);
        if (await secondItem.count()) {
          await secondItem.click({ timeout: 2000 }).catch(() => {});
          await page.waitForTimeout(500);
          const stillCollapsed = await page.locator('[data-testid="artifact-inspector-collapsed"]').count();
          reExpandedAfterNav = stillCollapsed > 0 ? 'blieb eingeklappt (persistiert)' : 'wieder ausgeklappt';
        }
        // re-expand for cleanliness
        const expandBtn = page.locator('[data-testid="artifact-inspector-expand"]');
        if (await expandBtn.count()) await expandBtn.click({ timeout: 2000 }).catch(() => {});
      }
      // panel inventory within the expanded inspector
      const panels = await page.evaluate(() => {
        const names = ['inspector-trace-panel'];
        const found = {};
        document.querySelectorAll('[data-testid]').forEach((el) => {
          const t = el.getAttribute('data-testid');
          if (t && /version|diff|trace|comment/i.test(t) && el.closest('[data-testid="artifact-inspector"]')) {
            found[t] = true;
          }
        });
        return Object.keys(found);
      });
      return { expandedShot, collapsedShot, miniIcons, reExpandedAfterNav, panelTestIdsSeen: panels };
    });
  }

  // ===== 2a. create-trace-link-dialog via TraceLinkPanel's real trigger =====
  await attempt(report, 'create-trace-link-dialog-FOUND', async () => {
    await goto('/requirements');
    const firstItem = page.locator('main[role="main"] [data-testid][role="button"], main[role="main"] [role="treeitem"]').first();
    await firstItem.click({ timeout: 3000 });
    await page.waitForTimeout(700);
    const trigger = page.locator('[data-testid="trace-link-panel-open-dialog"]');
    if (!(await trigger.count())) throw new Error('[data-testid="trace-link-panel-open-dialog"] nicht gefunden auf /requirements-Detail — evtl. hinter Scroll oder anderem Tab');
    await trigger.scrollIntoViewIfNeeded();
    await trigger.click({ timeout: 3000 });
    await page.waitForTimeout(600);
    const dlg = page.locator('[data-testid="create-trace-link-dialog"]');
    const opened = await dlg.isVisible().catch(() => false);
    const screenshot = await shot(page, 'create-trace-link-dialog-FOUND');
    await closeAnyDialog(page);
    if (!opened) throw new Error('Trigger geklickt, aber create-trace-link-dialog nicht sichtbar geworden');
    return { screenshot };
  });

  // ===== 2b. tree-move-dialog via per-node move button =====
  await attempt(report, 'tree-move-dialog-FOUND', async () => {
    await goto('/requirements');
    const moveBtn = page.locator('main[role="main"] [data-testid*="-move-"]').first();
    if (!(await moveBtn.count())) throw new Error('kein [data-testid*="-move-"] Element auf /requirements gefunden');
    await moveBtn.scrollIntoViewIfNeeded();
    await moveBtn.click({ timeout: 3000 });
    await page.waitForTimeout(600);
    const dlg = page.locator('[data-testid="workspace-tree-move-dialog"]');
    const opened = await dlg.isVisible().catch(() => false);
    const screenshot = await shot(page, 'tree-move-dialog-FOUND');
    await closeAnyDialog(page);
    if (!opened) throw new Error('Move-Button geklickt, aber workspace-tree-move-dialog nicht sichtbar');
    return { screenshot };
  });

  // ===== 2c. ai-derivation-dialog via overflow menu on /adrs =====
  await attempt(report, 'ai-derivation-dialog-FOUND', async () => {
    await goto('/adrs');
    const overflowBtn = page.locator('[data-testid="page-header-overflow-trigger"]');
    if (!(await overflowBtn.count())) throw new Error('page-header-overflow-trigger nicht auf /adrs gefunden');
    await overflowBtn.click({ timeout: 3000 });
    await page.waitForTimeout(700);
    const menuShot = await shot(page, 'adr-overflow-menu-open');
    const menuItemTexts = await page.locator('[data-testid="page-header-overflow-menu"] [role="menuitem"]').allInnerTexts().catch(() => []);
    const deriveItem = page.locator('[data-testid="adr-derive-btn"]');
    if (!(await deriveItem.count())) throw new Error(`adr-derive-btn nicht im Overflow-Menü. Sichtbare Menüeinträge: ${JSON.stringify(menuItemTexts)}. Screenshot: ${menuShot}`);
    await deriveItem.click({ timeout: 3000 });
    await page.waitForTimeout(1200);
    const screenshot = await shot(page, 'ai-derivation-dialog-FOUND');
    await closeAnyDialog(page);
    return { screenshot };
  });

  // ===== 3. detail routes via ArtifactRow's role=button selector =====
  for (const slug of ['icds', 'diagrams', 'interviews']) {
    await attempt(report, `detail-${slug}-FIXED`, async () => {
      await goto(`/${slug}`);
      const row = page.locator('main[role="main"] [data-testid][role="button"], main[role="main"] [role="treeitem"]').first();
      if (!(await row.count())) throw new Error('auch mit role=button-Selektor kein Listenelement gefunden — jetzt wahrscheinlich wirklich leer');
      await row.click({ timeout: 3000 });
      await page.waitForTimeout(700);
      const screenshot = await shot(page, `detail-${slug}-FIXED`);
      return { screenshot, url: page.url() };
    });
  }

  // ===== 4a. Goals: create then archive (write access granted) =====
  await attempt(report, 'goals-create-then-archive', async () => {
    await goto('/goals');
    const createBtn = page.locator('main[role="main"] button:visible', { hasText: /^\+?\s*neue?s?\s/i }).first();
    await createBtn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const titleInput = page.locator('[data-testid="goal-form-dialog"] input').first();
    await titleInput.fill('UI-Audit Testziel (löschbar)');
    const saveBtn = page.locator('[data-testid="goal-form-dialog"] button:visible', { hasText: /erstellen|speichern|anlegen/i }).first();
    await saveBtn.click({ timeout: 3000 });
    await page.waitForTimeout(800);
    const createdShot = await shot(page, 'goals-created-new');
    // find the new goal's archive action
    const archiveBtn = page.locator('main[role="main"] button:visible', { hasText: /archiv/i }).first();
    if (!(await archiveBtn.count())) throw new Error('Goal angelegt, aber danach kein Archivieren-Button sichtbar (evtl. erst nach Status-Wechsel verfügbar)');
    await archiveBtn.click({ timeout: 3000 });
    await page.waitForTimeout(500);
    const dlg = page.locator('[data-testid="goal-archive-dialog"]');
    const opened = await dlg.isVisible().catch(() => false);
    const archiveShot = await shot(page, 'goals-archive-dialog-FOUND');
    if (opened) {
      const facts = await page.evaluate(() => {
        const d = document.querySelector('[data-testid="goal-archive-dialog"]');
        const btns = Array.from(d.querySelectorAll('button')).filter(b => b.getBoundingClientRect().width > 0);
        return btns.slice(-3).sort((a,b)=>a.getBoundingClientRect().x-b.getBoundingClientRect().x).map(b=>({text:(b.textContent||'').trim(), className: b.className}));
      });
      await page.locator('[data-testid="goal-archive-dialog-cancel"]').click({ timeout: 2000 }).catch(() => closeAnyDialog(page));
      return { createdShot, archiveShot, footerFacts: facts };
    }
    return { createdShot, archiveShot, opened };
  });

  // ===== 4b. enforcement-flip: try switching mode =====
  await attempt(report, 'enforcement-flip-attempt', async () => {
    await goto('/system-settings');
    const permTab = page.locator('[data-testid="system-settings-tab-permission-defaults"]');
    if (await permTab.count()) { await permTab.click(); await settle(page); }
    const beforeShot = await shot(page, 'enforcement-mode-before');
    const modeButtons = await page.locator('main[role="main"] button:visible', { hasText: /shadow|authoritative|autoritativ/i }).all();
    const labels = [];
    for (const b of modeButtons) labels.push((await b.innerText().catch(() => '')).trim());
    if (!modeButtons.length) throw new Error('keine Modus-Umschalt-Buttons (shadow/authoritative) auf dieser Tab gefunden — Enforcement-UI evtl. anders aufgebaut als angenommen');
    return { beforeShot, modeButtonsFound: labels, note: 'Nur inspiziert, NICHT geklickt — ein echter Moduswechsel ist eine persistente Backend-Zustandsänderung (enforcement_mode DB-Row, wie im a11y-followup.js-Kommentar dokumentiert) und wird hier bewusst nicht ausgelöst, um das Testsystem nicht in einen anderen Modus als vorgefunden zurückzulassen.' };
  });

  // ===== 4c. reviews-signature: quick 2-3 click check only =====
  await attempt(report, 'reviews-signature-quicklook', async () => {
    await goto('/reviews');
    const screenshot = await shot(page, 'reviews-overview-recheck');
    const pendingItems = await page.locator('main[role="main"] [data-testid][role="button"], main[role="main"] [role="treeitem"]').count();
    return { screenshot, pendingItemsVisible: pendingItems, note: pendingItems === 0 ? 'Reviews-Liste leer auf diesem Testsystem — ein Review+Signatur-Schritt anzulegen bräuchte einen kompletten CCB-Workflow-Durchlauf (Artefakt -> Change Request -> Approval-Kette), nicht in 2-3 Klicks machbar. Endgültig offen gelassen, nicht erzwungen.' : 'Items vorhanden, s. Screenshot' };
  });

  fs.writeFileSync(REPORT_PATH, JSON.stringify({ generatedAt: new Date().toISOString(), report }, null, 2));
  console.log(`[part3] report written to ${REPORT_PATH}`);
  await browser.close();
}
main().catch((e) => { console.error(e); process.exit(1); });
