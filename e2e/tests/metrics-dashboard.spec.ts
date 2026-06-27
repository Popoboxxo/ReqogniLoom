// REQ-L0-020 / REQ-L2-SM-001: SE Process Metrics Dashboard — UI smoke tests
// Validates the /metrics route renders the tile grid and the refresh affordance.
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[REQ-L0-020 / REQ-L2-SM-001] MetricsDashboard UI', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L0-020] test_metrics_dashboard_renders', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/metrics`);

    // Root container becomes visible once the route mounts
    const root = page.locator('[data-testid="metrics-dashboard"]');
    await expect(root).toBeVisible({ timeout: 15000 });

    // Wait for the initial loading text to disappear (or tiles to render)
    await expect(page.getByText('Loading...')).not.toBeVisible({ timeout: 10000 });

    // At least one metric tile is visible — coverage is always present
    const coverageTile = page.locator('[data-testid="metric-tile-coverage"]');
    await expect(coverageTile).toBeVisible({ timeout: 10000 });
    await expect(page.locator('[data-testid="metric-tile-volatility"]')).toBeVisible();
    await expect(page.locator('[data-testid="metric-tile-workflowGap"]')).toBeVisible();
  });

  test('[REQ-L0-020] test_metrics_refresh_button_visible', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/metrics`);

    const root = page.locator('[data-testid="metrics-dashboard"]');
    await expect(root).toBeVisible({ timeout: 15000 });
    await expect(page.getByText('Loading...')).not.toBeVisible({ timeout: 10000 });

    const refreshBtn = page.locator('[data-testid="metrics-refresh-btn"]');
    await expect(refreshBtn).toBeVisible({ timeout: 10000 });
    await expect(refreshBtn).toBeEnabled();
  });
});
