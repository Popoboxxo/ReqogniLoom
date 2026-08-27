import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  timeout: 60000,
  // GH-682: hard ceiling for the whole shard run.
  //
  // The `e2e` job in .github/workflows/playwright.yml has a job-level
  // `timeout-minutes` budget. When the test run overruns it, GitHub *cancels*
  // the job — which kills the `if: always()` "Upload Playwright report" step
  // too, so the run produces no HTML report, no traces and no screenshots.
  // That is what turned a handful of broken tests into "no E2E visibility on
  // main at all" (run 32472920554: shard 2 cancelled after 20m, and the run's
  // artifact list contains reports 1/3/4 but nothing for shard 2).
  //
  // `globalTimeout` makes Playwright stop itself *before* the job cap, so the
  // reporter still finalises and the artifact still uploads. Sizing: the
  // pre-test setup steps (pip install + migrate + seed + playwright install +
  // docker build) cost ~5-8 min, the slowest shard's test phase is currently
  // ~4 min, and the job cap is 25 min — 10 min leaves headroom on both sides.
  globalTimeout: process.env.CI ? 10 * 60 * 1000 : undefined,
  expect: {
    timeout: 15000,
    // Visual regression (visual-regression.spec.ts): tolerate minor
    // font-rendering/anti-aliasing noise across machines/CI runners instead
    // of failing on single-pixel differences. `animations: 'disabled'` is
    // already Playwright's default for toHaveScreenshot (finishes/cancels
    // CSS animations+transitions before capture).
    toHaveScreenshot: { maxDiffPixelRatio: 0.02 },
  },
  testDir: './tests',
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1,
  reporter: [['html', { outputFolder: 'playwright-report' }], ['list']],
  use: {
    baseURL: process.env.FRONTEND_URL || 'http://localhost:5173',
    // GH-682: Playwright defaults `actionTimeout`/`navigationTimeout` to 0,
    // i.e. *no* limit — a locator action that can never become actionable
    // (classic case: `.click()` on a button that stays `disabled`) silently
    // burns the entire 60s `timeout` above, then does it twice more via
    // `retries: 2`. Three minutes per test, and the reported error is the
    // useless generic "Test timeout of 60000ms exceeded" instead of naming
    // the element.
    //
    // That is exactly how GH-682 played out: `createRequirementViaQuickForm`
    // clicked `req-new-save-btn` without filling the title, and that button is
    // `disabled={isCreating || !newTitle.trim()}` (RequirementEditors.tsx).
    // All 7 tests in requirement-editor.spec.ts hung 1.0 min x 3 attempts
    // (~21 min) and blew the shard's job budget. The helper was fixed in
    // c7f18d7; these two caps stop the *next* such breakage from escalating
    // from "one red spec" to "one dead shard with no report".
    //
    // 15s matches `expect.timeout` above: one coherent budget for "an
    // interaction must resolve". Navigation gets 30s because
    // `page.goto`/`page.waitForLoadState('networkidle')` (used ~40x in the
    // suite) also inherit it and legitimately wait on a cold Vite dev server.
    // Both are still well under the 60s test timeout, so a breach fails with a
    // precise, actionable message.
    actionTimeout: 15000,
    navigationTimeout: 30000,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
