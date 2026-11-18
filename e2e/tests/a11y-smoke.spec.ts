/**
 * Automated accessibility gate — Phase 6 step 8 of
 * `docs/plans/Archive/2026-10-15-frontend-audit-fixes.md` (§Phase 6, "Entscheidung 2",
 * §Tooling-Lücken, §Phase 8 step 5), expanded for S3.3 / A11Y-002.
 *
 * Before this spec the repo had axe-core only as a *manual* script
 * (`e2e/a11y-followup.js`, invoked via `node`, deliberately "NOT part of the
 * Playwright test suite") plus the `eslint-plugin-jsx-a11y` lint rules — i.e.
 * no automated axe gate in CI. This spec wires `@axe-core/playwright` into the
 * Playwright runner.
 *
 * A11Y-002 expansion (deep-dive audit 2026-11-16): the original gate scanned
 * only three states (nav shell, one dialog, one ArtifactForm). It now also
 * sweeps the 24 curated top-level routes from `visual-regression.spec.ts:21-46`
 * across all five themes, checks 320px reflow (WCAG 1.4.10) and checks keyboard
 * order / trap / Escape / focus restore (2.1.1, 2.4.3, 2.4.11). The expanded
 * matrix is tagged `@a11y` and runs in its own CI shard, so it never starves
 * the four desktop shards of their 10-minute global budget.
 *
 * Nearest requirement: REQ-056 (Accessibility-Basisabsicherung).
 *
 * Assertion policy (UNCHANGED by A11Y-002)
 * ----------------------------------------
 * The gate fails on `serious` and `critical` violations only; `moderate` and
 * `minor` findings are attached to the test as JSON but do not fail the run.
 * This is deliberate: moderate/minor are triaged as attachments, NOT promoted
 * to blocking (the deep-dive finding A11Y-003..006 stays an attachment trail).
 *
 * `KNOWN_EXEMPT_RULES` is intentionally EMPTY. It is the escape hatch for a
 * legitimate blocking finding that is tracked elsewhere: add
 * `{ rule: '<axe-rule-id>', reason: '<why>', ref: '#NNN' }`. Do not add an entry
 * just to make the gate green — fix the violation or file an issue first.
 *
 * Honesty note on themes
 * ----------------------
 * `ThemeProvider` re-resolves the theme from the *server* preference after an
 * authenticated mount and overwrites localStorage (ThemeContext.tsx:144-179).
 * Writing `localStorage['reqflow-theme']` alone — the a11y-followup.js:151,305
 * precedent — is therefore NOT enough: all five "themes" would silently scan
 * the server default. `setTheme()` below writes the localStorage keys (legacy
 * + split) AND the per-user preference through the real REST endpoint, then
 * ASSERTS the applied `data-theme`. A theme that cannot be applied fails loudly
 * instead of producing a fake green matrix.
 *
 * Manual screen-reader testing is documented in
 * `docs/audit/2026-11-16-a11y-manual-protocol.md` and is explicitly PENDING —
 * an automated axe gate is not a WCAG conformance certificate.
 */
import {
  test,
  expect,
  request as pwRequest,
  type Page,
  type TestInfo,
} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {
  loginAsAdmin,
  setWorkspaceId,
  getAuthToken,
  SEEDED_WORKSPACE_ID,
} from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

/**
 * WCAG tag set: WCAG 2.0 A + AA, WCAG 2.1 AA and WCAG 2.2 AA. Kept exactly as
 * before — `wcag22aa` is already present (it was never the gap A11Y-002 named,
 * the gap was 3 states × 1 theme). `best-practice` is deliberately excluded:
 * this is a WCAG conformance gate, not a style linter.
 */
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'];

/** axe impact levels this gate treats as release-blocking. */
const BLOCKING_IMPACTS = new Set(['serious', 'critical']);

/** Deliberately empty — see the file header. */
const KNOWN_EXEMPT_RULES: Array<{ rule: string; reason: string; ref: string }> = [];

/**
 * The 24 top-level routes from `SidebarNavigation.tsx::NAV_ITEMS`, copied
 * verbatim (same order/slugs) from `visual-regression.spec.ts:21-46` so the
 * a11y sweep and the screenshot baseline cover the identical surface.
 */
const CURATED_ROUTES: Array<[string, string]> = [
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

interface ThemeDef {
  /** Value written into the legacy `reqflow-theme` localStorage key. */
  id: string;
  /** `palette_key` accepted by PUT /api/v1/users/me/theme-preference/. */
  palette: string;
  /** Mode accepted by the same endpoint. */
  mode: 'dark' | 'light';
  /** `document.documentElement.dataset.theme` the app must end up with. */
  dataTheme: string;
}

/**
 * Five themes: the four `a11y-followup.js` variants (dark in Part A, light /
 * bauhaus / nordic / sepia in Part B). Named palettes keep a concrete mode so
 * the correct token set (`dark_tokens` vs `light_tokens`) is applied.
 */
const THEMES: ThemeDef[] = [
  { id: 'dark', palette: 'default', mode: 'dark', dataTheme: 'dark' },
  { id: 'light', palette: 'default', mode: 'light', dataTheme: 'light' },
  { id: 'bauhaus', palette: 'bauhaus', mode: 'dark', dataTheme: 'bauhaus' },
  { id: 'nordic', palette: 'nordic', mode: 'dark', dataTheme: 'nordic' },
  { id: 'sepia', palette: 'sepia', mode: 'light', dataTheme: 'sepia' },
];

/**
 * Write the per-user preference through the real REST endpoint.
 *
 * `palette_key` is NOT NULL in the DB (`admin_ops/models.py:344`) even though
 * GET returns null for "no row yet" and the PUT serializer accepts null — a
 * null write therefore raises IntegrityError -> HTTP 500. The argument is
 * deliberately typed `string` (not `string | null`) so no caller can feed null
 * to the endpoint; callers with no prior value must use the built-in fallback
 * palette ("default"), which is what the frontend resolves to anyway.
 */
async function putThemePreference(
  paletteKey: string,
  mode: 'dark' | 'light'
): Promise<void> {
  const token = await getAuthToken();
  const ctx = await pwRequest.newContext({ baseURL: BACKEND_URL });
  try {
    const resp = await ctx.put('/api/v1/users/me/theme-preference/', {
      headers: { Authorization: `Bearer ${token}` },
      data: { palette_key: paletteKey, mode },
    });
    if (!resp.ok()) {
      throw new Error(
        `theme preference write failed: ${resp.status()} ${await resp.text()}`
      );
    }
  } finally {
    await ctx.dispose();
  }
}

/**
 * Wait for a route to finish its lazy-chunk + network settling, mirroring
 * `visual-regression.spec.ts::gotoAndSettle`. `networkIdleMs` is shortened for
 * the 120-scan sweep so a route holding a websocket open cannot burn 15s × 24
 * × 5; the Suspense-fallback + main-visible waits remain the real gate.
 */
async function settle(page: Page, networkIdleMs = 3000): Promise<void> {
  await expect(page.locator('[data-testid="route-suspense-fallback"]')).toHaveCount(0, {
    timeout: 15000,
  });
  await expect(page.locator('main[role="main"]')).toBeVisible({ timeout: 10000 });
  await page.waitForLoadState('networkidle', { timeout: networkIdleMs }).catch(() => {
    // Some routes keep a long-poll/websocket-ish connection open; the
    // Suspense-fallback + main-visible waits above are the real gate.
  });
}

/** Force a theme and PROVE it actually applied (no silent fallback to default). */
async function setTheme(page: Page, theme: ThemeDef): Promise<void> {
  // (a) The documented/localStorage mechanism (a11y-followup.js:151,305-306),
  //     extended to the current split keys so the pre-auth paint is already
  //     themed. This alone is not sufficient once authenticated — see (b).
  await page.evaluate((t) => {
    const ls = window.localStorage;
    ls.setItem('reqflow-theme', t.id);
    ls.setItem('reqflow-theme-palette', t.palette);
    ls.setItem('reqflow-theme-mode', t.mode);
  }, theme);

  // (b) ThemeProvider overrides localStorage from the server preference after
  //     the authenticated fetch. Force that too, through the real API.
  await putThemePreference(theme.palette, theme.mode);

  // (c) Reload so the app re-resolves, then assert the resolved attribute.
  await page.reload({ waitUntil: 'domcontentloaded' });
  await settle(page);
  await expect(page.locator('html')).toHaveAttribute('data-theme', theme.dataTheme);
}

interface AxeSummary {
  violationCounts: Record<string, number>;
  violations: Array<{
    id: string;
    impact: string | null;
    help: string;
    helpUrl: string;
    nodes: string[];
  }>;
  blocking: string[];
}

function summarize(results: Awaited<ReturnType<AxeBuilder['analyze']>>): AxeSummary {
  const exempt = new Set(KNOWN_EXEMPT_RULES.map((e) => e.rule));
  const violationCounts = results.violations.reduce<Record<string, number>>((acc, v) => {
    const key = v.impact ?? 'unknown';
    acc[key] = (acc[key] ?? 0) + 1;
    return acc;
  }, {});
  const blocking = results.violations
    .filter((v) => BLOCKING_IMPACTS.has(v.impact ?? '') && !exempt.has(v.id))
    .map(
      (v) =>
        `[${v.impact}] ${v.id} — ${v.help} :: ` +
        v.nodes.map((n) => n.target.join(' ')).join(' | ')
    );
  return {
    violationCounts,
    violations: results.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      helpUrl: v.helpUrl,
      nodes: v.nodes.map((n) => n.target.join(' ')),
    })),
    blocking,
  };
}

/**
 * Run axe over the page (optionally scoped to one component), attach the full
 * result as JSON — so moderate/minor stay visible without failing — and assert
 * that no `serious`/`critical` violation remains.
 */
async function expectNoBlockingViolations(
  page: Page,
  testInfo: TestInfo,
  context: string,
  includeSelector?: string
): Promise<void> {
  const builder = new AxeBuilder({ page }).withTags(AXE_TAGS);
  if (includeSelector) builder.include(includeSelector);

  const summary = summarize(await builder.analyze());

  await testInfo.attach(`axe-${context}`, {
    body: JSON.stringify(
      {
        context,
        scope: includeSelector ?? 'document',
        tags: AXE_TAGS,
        blockingImpacts: [...BLOCKING_IMPACTS],
        exemptRules: [...KNOWN_EXEMPT_RULES.map((e) => e.rule)],
        ...summary,
      },
      null,
      2
    ),
    contentType: 'application/json',
  });

  // One readable line per blocking violation: the failing diff names the rule,
  // its impact and the offending node instead of a bare "expected []".
  expect(summary.blocking).toEqual([]);
}

test.describe('[REQ-056] Automated axe gate (Phase 6.8) @a11y', () => {
  /** Restore the admin user's original theme preference after the sweep. */
  let originalPref: { palette_key?: string | null; mode?: string | null } | undefined;

  test.beforeAll(async () => {
    const token = await getAuthToken();
    const ctx = await pwRequest.newContext({ baseURL: BACKEND_URL });
    try {
      const resp = await ctx.get('/api/v1/users/me/theme-preference/', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (resp.ok()) originalPref = await resp.json();
    } finally {
      await ctx.dispose();
    }
  });

  test.afterAll(async () => {
    if (!originalPref) return;
    // `palette_key` is NOT NULL (admin_ops/models.py:344). When no preference
    // row existed before the sweep, GET returned `{palette_key: null, mode:
    // null}` and writing that null back produced HTTP 500 (IntegrityError),
    // which threw here, closed the browser context and cascaded into
    // "Target page, context or browser has been closed" failures across the
    // shard. There is no DELETE endpoint on UserThemePreferenceView (GET/PUT
    // only), so the cleanest achievable restore of a previously-absent row is
    // the built-in fallback "default"/dark — exactly what the frontend
    // resolves to when no preference exists. A real prior preference is
    // restored verbatim.
    const palette =
      typeof originalPref.palette_key === 'string' && originalPref.palette_key.length > 0
        ? originalPref.palette_key
        : 'default';
    await putThemePreference(palette, originalPref.mode === 'light' ? 'light' : 'dark');
  });

  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  // -------------------------------------------------------------------------
  // The original three interactive states (unchanged assertions, A11Y-002 no
  // longer "only 3 states" once the sweep below runs).
  // -------------------------------------------------------------------------
  test('[A11Y] navigation shell has no serious/critical axe violations', async ({
    page,
  }, testInfo) => {
    await page.goto(`${FRONTEND_URL}/`, { waitUntil: 'domcontentloaded' });
    await settle(page);
    const skipLink = page.locator('[data-testid="skip-link"]');
    await expect(skipLink).toBeAttached();
    await expect(page.locator('main#main-content')).toBeVisible();

    // N2/N13 (SC 2.4.11 Focus Not Obscured): focus reveals the skip link; assert
    // it is then genuinely visible and on top, not merely present in the DOM.
    await skipLink.focus();
    await expect(skipLink).toBeVisible();
    const skipLinkBox = await skipLink.boundingBox();
    expect(skipLinkBox).not.toBeNull();
    expect(skipLinkBox!.x).toBeGreaterThanOrEqual(0);
    expect(skipLinkBox!.y).toBeGreaterThanOrEqual(0);
    const skipLinkUnobscured = await skipLink.evaluate((el) => {
      const rect = el.getBoundingClientRect();
      const topmost = document.elementFromPoint(
        rect.left + rect.width / 2,
        rect.top + rect.height / 2
      );
      return topmost === el || (topmost !== null && el.contains(topmost));
    });
    expect(skipLinkUnobscured).toBe(true);

    await expectNoBlockingViolations(page, testInfo, 'navigation-shell');
  });

  test('[A11Y] an open Dialog has no serious/critical axe violations', async ({
    page,
  }, testInfo) => {
    await page.goto(`${FRONTEND_URL}/system-settings`, { waitUntil: 'domcontentloaded' });
    await settle(page);

    await page.locator('[data-testid="system-health-open-btn"]').click();
    const dialog = page.locator('[data-testid="system-health-dialog"]');
    await expect(dialog).toBeVisible();

    await expectNoBlockingViolations(
      page,
      testInfo,
      'dialog',
      '[data-testid="system-health-dialog"]'
    );
  });

  test('[A11Y] an ArtifactForm has no serious/critical axe violations', async ({
    page,
  }, testInfo) => {
    await page.goto(`${FRONTEND_URL}/requirements`, { waitUntil: 'domcontentloaded' });
    await settle(page);

    await page.locator('[data-testid="create-req-btn"]').click();
    await page
      .locator('[data-testid="req-new-title-input"]')
      .fill(`A11Y smoke ${Date.now()}`);
    await page.locator('[data-testid="req-new-save-btn"]').click();

    const form = page.locator('[data-testid="artifact-form"]');
    await expect(form).toBeVisible({ timeout: 15000 });
    await expect(page.locator('[data-testid="artifact-field-title"]')).toBeVisible({
      timeout: 15000,
    });

    await expectNoBlockingViolations(page, testInfo, 'artifact-form', '[data-testid="artifact-form"]');
  });

  // -------------------------------------------------------------------------
  // A11Y-002: curated 24 routes × 5 themes. One test per theme, so a failure
  // names the theme; the 24 scans share one JSON attachment per theme.
  // -------------------------------------------------------------------------
  for (const theme of THEMES) {
    test(`[A11Y] 24-route axe sweep — theme=${theme.id}`, async ({ page }, testInfo) => {
      await setTheme(page, theme);

      const routes: Array<{ slug: string; route: string } & AxeSummary> = [];
      for (const [slug, route] of CURATED_ROUTES) {
        await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' });
        await settle(page);
        const summary = summarize(await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze());
        routes.push({ slug, route, ...summary });
      }

      await testInfo.attach(`axe-route-sweep-${theme.id}`, {
        body: JSON.stringify(
          {
            theme,
            tags: AXE_TAGS,
            blockingImpacts: [...BLOCKING_IMPACTS],
            exemptRules: [...KNOWN_EXEMPT_RULES.map((e) => e.rule)],
            routes,
          },
          null,
          2
        ),
        contentType: 'application/json',
      });

      const blocking = routes.flatMap((r) =>
        r.blocking.map((line) => `${r.route} (${r.slug}): ${line}`)
      );
      expect(blocking).toEqual([]);
    });
  }

  // -------------------------------------------------------------------------
  // WCAG 1.4.10 Reflow: 1280px @ 400% ≈ 320 CSS px. No document-level
  // horizontal scroll on any curated route.
  // -------------------------------------------------------------------------
  test('[A11Y] 320px viewport has no document-level horizontal overflow', async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 720 });
    const measurements: Array<{
      slug: string;
      route: string;
      scrollWidth: number;
      clientWidth: number;
    }> = [];

    for (const [slug, route] of CURATED_ROUTES) {
      await page.goto(`${FRONTEND_URL}${route}`, { waitUntil: 'domcontentloaded' });
      await settle(page, 2000);
      const m = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      measurements.push({ slug, route, ...m });
    }

    await testInfo.attach('reflow-320px', {
      body: JSON.stringify({ viewport: { width: 320, height: 720 }, measurements }, null, 2),
      contentType: 'application/json',
    });

    const overflowing = measurements.filter((m) => m.scrollWidth > m.clientWidth + 1);
    expect(overflowing).toEqual([]);
  });

  // -------------------------------------------------------------------------
  // WCAG 2.1.1 / 2.4.3 / 2.4.11: Tab + Shift-Tab order, focus trap, Escape,
  // and focus restore on the shared Dialog primitive.
  // -------------------------------------------------------------------------
  test('[A11Y] Dialog Tab/Shift-Tab order, trap, Escape and focus restore', async ({
    page,
  }, testInfo) => {
    await page.goto(`${FRONTEND_URL}/system-settings`, { waitUntil: 'domcontentloaded' });
    await settle(page);

    const trigger = page.locator('[data-testid="system-health-open-btn"]');
    await trigger.click();
    const dialog = page.locator('[data-testid="system-health-dialog"]');
    await expect(dialog).toBeVisible();

    const focusables = dialog.locator(
      'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    );
    const count = await focusables.count();
    expect(count).toBeGreaterThanOrEqual(2);

    const activeInfo = () =>
      page.evaluate(() => {
        const el = document.activeElement as HTMLElement | null;
        return {
          testid: el?.getAttribute('data-testid') ?? null,
          tag: el?.tagName ?? null,
          inDialog: !!el?.closest('[data-testid="system-health-dialog"]'),
        };
      });

    await focusables.first().focus();
    const first = await activeInfo();
    expect(first.inDialog).toBe(true);

    await page.keyboard.press('Tab');
    const second = await activeInfo();
    expect(second.inDialog).toBe(true);
    expect(second.testid).not.toBe(first.testid);

    await page.keyboard.press('Shift+Tab');
    const back = await activeInfo();
    expect(back.inDialog).toBe(true);
    expect(back.testid).toBe(first.testid);

    // Trap: cycling one extra Tab beyond the focusable count must not escape.
    const seen: Array<string | null> = [];
    for (let i = 0; i < count + 1; i += 1) {
      await page.keyboard.press('Tab');
      const active = await activeInfo();
      expect(active.inDialog).toBe(true);
      seen.push(active.testid);
    }

    await testInfo.attach('dialog-keyboard', {
      body: JSON.stringify({ count, first, second, back, tabCycle: seen }, null, 2),
      contentType: 'application/json',
    });

    await page.keyboard.press('Escape');
    await expect(dialog).toBeHidden();
    await expect(trigger).toBeFocused();
  });
});
