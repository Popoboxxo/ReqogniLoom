// @mobile — mobile smoke suite (plan M0, REQ-215).
//
// This suite is deliberately shallow: it does not verify feature behaviour,
// only that the shell renders and the document does not scroll sideways on a
// phone. It is tagged `@mobile` so the four desktop shards skip it; the
// dedicated fifth CI shard runs the two device projects against it.
import { test } from '@playwright/test';
import { loginAsAdmin } from '../helpers/auth';
import { expectNoHorizontalDocumentScroll, openFirstListItem } from '../helpers/mobile';

const ROUTES: Array<[string, string]> = [
  ['dashboard', '/'],
  ['requirements', '/requirements'],
  ['documents', '/documents'],
  ['traceability', '/traceability'],
  ['connections', '/connections'],
];

test.describe('@mobile shell smoke', () => {
  test('all routes fit the viewport and list/detail is usable', async ({ page }) => {
    await loginAsAdmin(page);

    for (const [name, path] of ROUTES) {
      await test.step(`route ${path}`, async () => {
        await page.goto(path);
        // Wait for the route's async data instead of screenshotting the
        // loading skeleton (React Query fetches after the first paint).
        await page.locator('main').first().waitFor({ state: 'visible' });
        await expectNoHorizontalDocumentScroll(page);

        if (test.info().project.name === 'mobile-safari') {
          // Only one project writes baselines; two device snapshots of the
          // same route would double the review surface without new signal.
          await page.screenshot({
            // e2e/test-results/ is gitignored; the CI report artifact keeps
            // these for the M0 audit without committing a baseline we cannot
            // generate until the stack is available.
            path: `test-results/mobile-baseline/mobile-${name}.png`,
            animations: 'disabled',
          });
        }
      });
    }

    // The core mobile flow from Spec §4.1 / REQ-209: a list item opens the
    // detail as a replacement for the list, not as a second narrow column.
    await page.goto('/requirements');
    await openFirstListItem(page);
    await expectNoHorizontalDocumentScroll(page);
  });
});
