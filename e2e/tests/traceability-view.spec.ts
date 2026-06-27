// REQ-L2-RF-006: Traceability-Anzeige mit echten API-Daten
import { test, expect } from '@playwright/test';
import { loginAsAdmin, setWorkspaceId, SEEDED_WORKSPACE_ID } from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

test.describe('[COMP-RF-005] TraceabilityView', () => {
  test.beforeEach(async ({ page }) => {
    await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
    await loginAsAdmin(page);
  });

  test('[REQ-L2-RF-006] traceability view renders without error', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    await page.waitForLoadState('networkidle');
    const view = page.locator('[data-testid="traceability-view"]');
    await expect(view).toBeVisible({ timeout: 10000 });
  });

  test('[REQ-L2-RF-006] traceability view does not show stub placeholder', async ({ page }) => {
    await page.goto(`${FRONTEND_URL}/traceability`);
    await page.waitForLoadState('networkidle');
    // Must NOT show the old "in Bearbeitung" stub text
    await expect(page.locator('body')).not.toContainText('in Bearbeitung');
  });
});
