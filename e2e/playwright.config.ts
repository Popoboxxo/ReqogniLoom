import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  timeout: 60000,
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
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    video: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
});
