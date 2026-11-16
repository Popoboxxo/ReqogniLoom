// @mobile — list → detail → back across the artifact routes (plan M5, REQ-209).
// The regression: on a phone, opening a detail rendered the two-column
// desktop branch instead of replacing the list.
import { test, expect, type Page } from '@playwright/test';
import { loginAsAdmin } from '../helpers/auth';
import { openFirstListItem } from '../helpers/mobile';

const ROUTES = [
  '/requirements',
  '/needs',
  '/risks',
  '/issues',
  '/adrs',
  '/testcases',
  '/glossary',
  '/baselines',
];

test.describe('@mobile list/detail flow', () => {
  test('detail replaces the list and the back step returns', async ({ page }: { page: Page }) => {
    await loginAsAdmin(page);

    for (const route of ROUTES) {
      await test.step(route, async () => {
        await page.goto(route);
        const rows = page.locator('[aria-selected], [aria-pressed]');
        if ((await rows.count()) === 0) {
          test.skip(true, `${route}: no selectable row in the seeded data`);
          return;
        }

        await openFirstListItem(page);
        await expect(page.getByTestId('splitview-back')).toBeVisible();
        await expect(page.getByTestId('splitview-list')).toBeHidden();
        await expect(page.getByTestId('splitview-detail')).toBeVisible();

        await page.getByTestId('splitview-back').click();
        await expect(page.getByTestId('splitview-list')).toBeVisible();
      });
    }
  });
});
