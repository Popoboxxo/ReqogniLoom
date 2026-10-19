/**
 * Automated accessibility gate — Phase 6 step 8 of
 * `docs/plans/2026-10-15-frontend-audit-fixes.md` (§Phase 6, "Entscheidung 2",
 * §Tooling-Lücken, §Phase 8 step 5).
 *
 * Before this spec the repo had axe-core only as a *manual* script
 * (`e2e/a11y-followup.js`, invoked via `node`, deliberately "NOT part of the
 * Playwright test suite") plus the `eslint-plugin-jsx-a11y` lint rules — i.e.
 * no automated axe gate in CI. This spec wires `@axe-core/playwright` into the
 * Playwright runner and scans the three states the plan names: the navigation
 * shell (authenticated), an open Dialog, and an ArtifactForm.
 *
 * Nearest requirement: REQ-056 (Accessibility-Basisabsicherung). The plan's
 * target is a smoke gate, not a full WCAG audit — the manual
 * `a11y-followup.js` sweeps (5 themes, 41 scans) remain the deeper check.
 *
 * Assertion policy
 * ----------------
 * The gate fails on `serious` and `critical` violations only; `moderate` and
 * `minor` findings are attached to the test output (JSON) but do not fail the
 * run. That keeps the gate honest-but-mergeable: it blocks the classes of
 * violation the audit treated as release-blocking (axe maps e.g.
 * `nested-interactive`, unlabelled form controls and `color-contrast` to
 * serious/critical) without turning every systematic minor/style finding into
 * a red shard.
 *
 * `KNOWN_EXEMPT_RULES` is the escape hatch for a *legitimate* blocking finding
 * that is tracked elsewhere (e.g. a design-system follow-up): add the axe rule
 * id here with a one-line reason and the issue reference. It is intentionally
 * empty right now — the Phase 6 commits that precede this spec remediated the
 * known H-/M-findings, so no exemption is needed yet. Do not add an entry just
 * to make the gate green; fix the violation or file an issue first.
 */
import { test, expect, type Page, type TestInfo } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/**
 * WCAG tag set: WCAG 2.0 A + AA, WCAG 2.1 AA and WCAG 2.2 AA. The first three
 * mirror `e2e/a11y-followup.js` (`AXE_TAGS`) exactly, so automated and manual
 * runs stay comparable; `wcag22aa` is deliberately *wider* than the manual
 * script (N12, Phase 6 review) so the automated gate also covers the WCAG 2.2
 * success criteria the audit reviewed — most notably 2.4.11 Focus Not
 * Obscured, the criterion the skip-link regression (N2) violated — instead of
 * silently staying on the older level.
 * `best-practice` is deliberately excluded — this is a WCAG conformance gate,
 * not a style linter.
 */
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21aa', 'wcag22aa'];

/** axe impact levels this gate treats as release-blocking. */
const BLOCKING_IMPACTS = new Set(['serious', 'critical']);

/**
 * axe rule ids that would otherwise fail the gate. Empty on purpose — see the
 * file header. Add `{ rule: '<axe-rule-id>', reason: '<why>', ref: '#NNN' }`.
 */
const KNOWN_EXEMPT_RULES: Array<{ rule: string; reason: string; ref: string }> = [];

/**
 * Wait for a route to finish its lazy-chunk + network settling, mirroring
 * `visual-regression.spec.ts::gotoAndSettle` (explicit state waits, no fixed
 * sleeps).
 */
async function settle(page: Page): Promise<void> {
  await expect(page.locator('[data-testid="route-suspense-fallback"]')).toHaveCount(0, {
    timeout: 15000,
  });
  await expect(page.locator('main[role="main"]')).toBeVisible({ timeout: 10000 });
  await page.waitForLoadState('networkidle', { timeout: 15000 }).catch(() => {
    // Some routes keep a long-poll/websocket-ish connection open; the
    // Suspense-fallback + main-visible waits above are the real gate.
  });
}

/**
 * Run axe over the page (optionally scoped to one component) and assert that no
 * `serious`/`critical` violation remains.
 *
 * The full violation list is attached to the test as JSON, so moderate/minor
 * findings stay visible in the HTML report instead of being silently dropped.
 *
 * @param context Human-readable name of the scanned state (used for the
 *   attachment name and the failure output).
 * @param includeSelector Optional CSS selector. When given, axe scans only that
 *   subtree — used for the Dialog and ArtifactForm states so the gate reports
 *   on the component under test rather than the surrounding page.
 */
async function expectNoBlockingViolations(
  page: Page,
  testInfo: TestInfo,
  context: string,
  includeSelector?: string
): Promise<void> {
  const builder = new AxeBuilder({ page }).withTags(AXE_TAGS);
  if (includeSelector) builder.include(includeSelector);

  const results = await builder.analyze();
  const exempt = new Set(KNOWN_EXEMPT_RULES.map((e) => e.rule));

  await testInfo.attach(`axe-${context}`, {
    body: JSON.stringify(
      {
        context,
        scope: includeSelector ?? 'document',
        tags: AXE_TAGS,
        blockingImpacts: [...BLOCKING_IMPACTS],
        exemptRules: [...exempt],
        violationCounts: results.violations.reduce<Record<string, number>>((acc, v) => {
          const key = v.impact ?? 'unknown';
          acc[key] = (acc[key] ?? 0) + 1;
          return acc;
        }, {}),
        violations: results.violations.map((v) => ({
          id: v.id,
          impact: v.impact,
          help: v.help,
          helpUrl: v.helpUrl,
          nodes: v.nodes.map((n) => n.target.join(' ')),
        })),
      },
      null,
      2
    ),
    contentType: 'application/json',
  });

  // One readable line per blocking violation: the failing diff then names the
  // rule, its impact and the offending node instead of a bare "expected []".
  const blocking = results.violations
    .filter((v) => BLOCKING_IMPACTS.has(v.impact ?? '') && !exempt.has(v.id))
    .map(
      (v) =>
        `[${v.impact}] ${v.id} — ${v.help} :: ` +
        v.nodes.map((n) => n.target.join(' ')).join(' | ')
    );

  expect(blocking).toEqual([]);
}

test.describe('[REQ-056] Automated axe gate (Phase 6.8)', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[A11Y] navigation shell has no serious/critical axe violations', async ({
    page,
  }, testInfo) => {
    // Whole-document scan on the authenticated landing route: this is the only
    // state that exercises the shell chrome added in Phase 6 (skip link, the
    // `<main id="main-content">` landmark, the sidebar drawer trigger) together
    // with the navigation and the landing content beneath it.
    await page.goto(`${FRONTEND_URL}/`, { waitUntil: 'domcontentloaded' });
    await settle(page);
    const skipLink = page.locator('[data-testid="skip-link"]');
    await expect(skipLink).toBeAttached();
    await expect(page.locator('main#main-content')).toBeVisible();

    // N2/N13 (SC 2.4.11 Focus Not Obscured): focus is what reveals the skip
    // link, so assert it is then genuinely *visible and on top* — not merely
    // present in the DOM. `toBeAttached()` alone passed while the focused link
    // was completely painted over by the 220px sidebar rail (z-index
    // regression, N2); only focusing it can catch that.
    await skipLink.focus();
    await expect(skipLink).toBeVisible();
    const skipLinkBox = await skipLink.boundingBox();
    expect(skipLinkBox).not.toBeNull();
    expect(skipLinkBox!.x).toBeGreaterThanOrEqual(0);
    expect(skipLinkBox!.y).toBeGreaterThanOrEqual(0);
    // `toBeVisible` does not detect occlusion; the topmost element at the
    // link's own centre must be the link itself (or a descendant), otherwise
    // shell chrome such as the rail/burger is still painting over it.
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
    // The shared <Dialog> primitive (role="dialog" + aria-modal +
    // aria-labelledby) via the system-health dialog — the same trigger the
    // existing `dialog-escape-robustness.spec.ts` uses, so this adds no new
    // fixture and mutates no state.
    await page.goto(`${FRONTEND_URL}/system-settings`, { waitUntil: 'domcontentloaded' });
    await settle(page);

    await page.locator('[data-testid="system-health-open-btn"]').click();
    const dialog = page.locator('[data-testid="system-health-dialog"]');
    await expect(dialog).toBeVisible();

    // Scoped to the dialog panel: a modal's own a11y contract is what this
    // state is about, and the background is intentionally not `aria-hidden`
    // by the primitive (axe would otherwise re-report unrelated page content).
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
    // The full ArtifactForm (shared renderer, including the section headings
    // fixed in Phase 6 step 3 / H-2) only mounts on the artifact's detail
    // route, so create a throwaway requirement via the list's quick form and
    // scan the editor it lands on — the same flow `requirement-editor.spec.ts`
    // uses.
    await page.goto(`${FRONTEND_URL}/requirements`, { waitUntil: 'domcontentloaded' });
    await settle(page);

    await page.locator('[data-testid="create-req-btn"]').click();
    await page
      .locator('[data-testid="req-new-title-input"]')
      .fill(`A11Y smoke ${Date.now()}`);
    await page.locator('[data-testid="req-new-save-btn"]').click();

    const form = page.locator('[data-testid="artifact-form"]');
    await expect(form).toBeVisible({ timeout: 15000 });
    // The form only renders its server-driven fields once the tenant's global
    // attribute definitions have loaded; wait for one before scanning so the
    // gate sees the real form, not the loading placeholder.
    await expect(page.locator('[data-testid="artifact-field-title"]')).toBeVisible({
      timeout: 15000,
    });

    await expectNoBlockingViolations(page, testInfo, 'artifact-form', '[data-testid="artifact-form"]');
  });
});
