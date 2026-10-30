// Plan B / B5-T5 (#378): advisory quality badge + assessment panel.
// Mock provider verdict is 0.5 → the badge must show "50%".
import { test, expect, type Page } from '@playwright/test';
import { createIsolatedWorkspace, getAuthToken, loginAsAdmin, setWorkspaceId } from '../helpers/auth';
import { getLlmProvider, llmRequestTimeoutMs, llmSkipHint } from '../helpers/llm';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

async function createRequirement(page: Page, title: string): Promise<void> {
  await page.locator('[data-testid="create-req-btn"]').click();
  await page.locator('[data-testid="req-new-title-input"]').fill(title);
  await page.locator('[data-testid="req-new-save-btn"]').click();
  await expect(page.locator('[data-testid="artifact-field-title"]')).toBeVisible({ timeout: 10000 });
}

test.describe('[COMP-RF-003] quality assessment badge', () => {
  test('assessing a requirement shows the score as a percentage', async ({ page, request }) => {
    // LLM-backed: only the mock path yields the deterministic 50% verdict.
    const provider = await getLlmProvider(request, await getAuthToken());
    test.skip(llmSkipHint(provider) !== null, llmSkipHint(provider) ?? '');
    if (llmRequestTimeoutMs(provider) !== undefined) test.slow();

    const token = await getAuthToken();
    await setWorkspaceId(page, await createIsolatedWorkspace(token));
    await loginAsAdmin(page);
    await page.goto(`${FRONTEND_URL}/requirements`);
    await createRequirement(page, `Quality E2E ${Date.now()}`);

    const badge = page.locator('[data-testid="quality-badge"]');
    await expect(badge).toBeVisible();
    await badge.click();
    await expect(page.locator('[data-testid="quality-panel"]')).toBeVisible();
    await page.locator('[data-testid="quality-assess-button"]').click();
    // Only the mock verdict is deterministic; a real model returns any score.
    const isMockProvider = provider === null || provider === 'mock';
    const budget = llmRequestTimeoutMs(provider) ?? 15000;
    await expect(page.locator('[data-testid="quality-badge-score"]')).toHaveText(
      isMockProvider ? '50%' : /\d+%/,
      { timeout: budget }
    );
    await expect(page.locator('[data-testid="quality-history-row-0"]')).toBeVisible();
  });
});
