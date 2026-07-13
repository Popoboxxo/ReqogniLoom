// REQ-L2-RF-002, REQ-L3-RF002-001/002/003: Dashboard with workspace cards
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[COMP-RF-002] DashboardViews', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L3-RF002-001] dashboard renders workspace cards with name and metrics', async ({ page }) => {
    // Navigate to dashboard root
    await page.goto(`${FRONTEND_URL}/`);

    // Workspace list container must be visible
    const list = page.locator('[data-testid="workspace-list"]');
    await expect(list).toBeVisible({ timeout: 10000 });

    // At least one workspace card must be rendered (seeded demo workspace)
    const cards = page.locator('[data-testid="workspace-card"]');
    await expect(cards.first()).toBeVisible({ timeout: 5000 });

    // First card content checks — it must contain a name (h3), requirement count, open items
    const firstCard = cards.first();
    await expect(firstCard.locator('h3')).toBeVisible();
    // Card text contains numeric metrics for requirements + open items
    const cardText = await firstCard.innerText();
    expect(cardText.length).toBeGreaterThan(0);
    // Two <strong> values: requirement_count + open_item_count
    const strongCount = await firstCard.locator('strong').count();
    expect(strongCount).toBeGreaterThanOrEqual(2);
  });

  test('[REQ-L3-RF002-002] workspace cards render terminology-profile-aware label', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/`);
    const firstCard = page.locator('[data-testid="workspace-card"]').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    // Card shows preset and a terminology profile label (devMode / seMode)
    const text = await firstCard.innerText();
    // Preset name appears (minimal / standard / extended)
    expect(text).toMatch(/minimal|standard|extended/i);
    // Either "Dev" or "SE" mode label is rendered (i18n English/German tolerant)
    expect(text).toMatch(/(dev|developer|systems engineer|se mode|engineer)/i);
  });

  test('[REQ-L3-RF002-003] clicking workspace card navigates away from dashboard', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/`);
    const firstCard = page.locator('[data-testid="workspace-card"]').first();
    await expect(firstCard).toBeVisible({ timeout: 10000 });

    await firstCard.click();
    // After selection, navigate is called -> /requirements
    await page.waitForURL(/\/requirements/, { timeout: 8000 });
    await expect(page).toHaveURL(/\/requirements/);
  });
});
