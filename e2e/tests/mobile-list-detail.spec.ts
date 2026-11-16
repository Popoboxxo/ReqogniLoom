// @mobile — list → detail → back across the artifact routes (plan M5, REQ-209).
// The regression: on a phone, opening a detail rendered the two-column
// desktop branch instead of replacing the list. Each route is its own test so
// an empty/failed route can never hide the others behind a `test.skip()`.
import { test, expect, type Page } from '@playwright/test';
import { loginAsAdmin } from '../helpers/auth';
import { LIST_ROW_SELECTOR, openFirstListItem } from '../helpers/mobile';

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
  for (const route of ROUTES) {
    test(`${route}: detail replaces the list and the back step returns`, { tag: '@mobile' }, async ({ page }: { page: Page }) => {
      await loginAsAdmin(page);
      await page.goto(route);
      await expect(page.getByTestId('splitview-list')).toBeVisible();

      // Some routes (notably /baselines) can have an empty list in a freshly
      // seeded CI database. Skip only that route — never the whole suite.
      const rows = page.locator(LIST_ROW_SELECTOR);
      await rows.first().waitFor({ state: 'visible', timeout: 4000 }).catch(() => undefined);
      if ((await rows.count()) === 0) {
        test.skip(true, `${route}: no seeded rows in this environment`);
      }

      await openFirstListItem(page);
      await expect(page.getByTestId('splitview-list')).toBeHidden();
      await expect(page.getByTestId('splitview-detail')).toBeVisible();

      await page.getByTestId('splitview-back').click();
      await expect(page.getByTestId('splitview-list')).toBeVisible();
      await expect(page.getByTestId('splitview-detail')).toBeHidden();
    });
  }
});
