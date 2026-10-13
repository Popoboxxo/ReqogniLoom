// Issue #1239 — measurement spec (A/B verdict, not a regression gate).
//
// Claim under test: clicking "Save" on the Requirement detail page
// (`/requirements/<id>`) does NOT send a PATCH (issue #1239).
//
// Plan claim: the save chain DOES send one PATCH
// (`ArtifactForm.tsx` handleSave -> adapter `onSave` ->
//  `requirementsApi.update` -> `apiClient.patch`).
//
// This spec does not assert a product requirement — it records the RAW
// `/api/v1/` network trace around the Save click for the `standard` and
// `extended` rigor presets and derives an A/B verdict from it:
//   B = exactly one PATCH to /api/v1/requirements/<id>/  (not reproduced)
//   A = zero (or otherwise != 1)                          (reproduced)
//
// The whole trace (method / URL path / status) is printed to stdout and
// attached to the HTML report as JSON evidence.
import { test, expect, type Response } from '@playwright/test';
import {
  loginAsAdmin,
  setWorkspaceId,
  setWorkspacePreset,
  getWorkspacePreset,
  getAuthToken,
  SEEDED_WORKSPACE_ID,
  type WorkspacePresetName,
} from '../helpers/auth';

const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';
// Seeded demo requirement (workspace 6d20f0b9-…), overridable for other runs.
const REQUIREMENT_ID =
  process.env.ISSUE1239_REQ_ID || '58062354-78e9-4511-a32c-68a59978f877';

interface TraceEntry {
  method: string;
  path: string;
  status: number;
}

function isApiV1(url: string): boolean {
  try {
    return new URL(url).pathname.startsWith('/api/v1/');
  } catch {
    return false;
  }
}

// The preset is tenant-wide shared state on the seeded workspace; run the two
// preset cases sequentially so neither observes the other mid-switch.
test.describe.configure({ mode: 'serial' });

test.describe('[ISSUE-1239] Requirement detail Save — Playwright network trace', () => {
  // The workspace was found in `extended`; restore it so this measurement does
  // not leave the shared dev environment on a different preset.
  test.afterAll(async () => {
    await setWorkspacePreset('extended');
  });

  for (const preset of ['standard', 'extended'] as WorkspacePresetName[]) {
    test(`Save sends PATCH on /requirements/<id> (preset=${preset})`, async ({
      page,
    }, testInfo) => {
      // --- 1. Put the workspace on the requested preset, prove backend took it
      await setWorkspacePreset(preset);
      const token = await getAuthToken();
      expect(
        await getWorkspacePreset(token, SEEDED_WORKSPACE_ID),
        `backend preset after setWorkspacePreset(${preset})`
      ).toBe(preset);

      // --- 2. Load the app as admin in the seeded workspace
      await setWorkspaceId(page, SEEDED_WORKSPACE_ID);
      await loginAsAdmin(page);

      // --- 3. Capture EVERY /api/v1/ response from here on
      const trace: TraceEntry[] = [];
      const record = (resp: Response): void => {
        if (!isApiV1(resp.url())) return;
        const u = new URL(resp.url());
        trace.push({
          method: resp.request().method(),
          path: u.pathname + u.search,
          status: resp.status(),
        });
      };
      page.on('response', record);

      // --- 4. Navigate to the requirement detail editor
      await page.goto(`${FRONTEND_URL}/requirements/${REQUIREMENT_ID}`);
      await expect(
        page.locator('[data-testid="artifact-field-title"]')
      ).toBeVisible({ timeout: 15000 });

      // Client-side proof the preset actually reached the form: `extended`
      // renders (and requires) the change-reason field, `standard` must not.
      const changeReason = page.locator(
        '[data-testid="artifact-form-change-reason"]'
      );
      if (preset === 'extended') {
        await expect(changeReason).toBeVisible({ timeout: 10000 });
      } else {
        await expect(changeReason).toHaveCount(0);
      }

      // --- 5. Edit TITLE and DESCRIPTION
      const marker = `${preset}-${Date.now()}`;
      await page
        .locator('[data-testid="artifact-field-title"]')
        .fill(`[1239 ${marker}]`);
      await page
        .locator(
          '[data-testid="artifact-widget-description_editor"] textarea'
        )
        .fill(`description edited by issue-1239 trace (${marker})`);

      // `extended` gates the PATCH behind a mandatory change reason; without it
      // the form refuses the save client-side and no request is emitted — which
      // would be a false negative for the wrong reason.
      if (preset === 'extended') {
        await changeReason.fill(`issue-1239 trace ${marker}`);
      }

      // --- 6. Click Save, wait (bounded) for the PATCH, then let requests settle
      const patchPredicate = (resp: Response): boolean => {
        if (resp.request().method() !== 'PATCH') return false;
        try {
          return (
            new URL(resp.url()).pathname ===
            `/api/v1/requirements/${REQUIREMENT_ID}/`
          );
        } catch {
          return false;
        }
      };
      const patchSeen = page
        .waitForResponse(patchPredicate, { timeout: 8000 })
        .then((r) => r.status())
        .catch(() => null);

      await page.locator('[data-testid="artifact-form-save"]').click();
      const patchStatus = await patchSeen;
      await page.waitForTimeout(1500); // drain any trailing requests
      page.off('response', record);

      // --- 7. Derive the A/B verdict from the raw trace
      const requirementPatches = trace.filter(
        (e) =>
          e.method === 'PATCH' &&
          e.path.startsWith(`/api/v1/requirements/${REQUIREMENT_ID}/`)
      );
      const transitionsGets = trace.filter(
        (e) =>
          e.method === 'GET' &&
          e.path.startsWith(
            `/api/v1/requirements/${REQUIREMENT_ID}/transitions/`
          )
      );
      const verdict =
        requirementPatches.length === 1
          ? 'B (not reproduced: exactly one PATCH)'
          : `A (reproduced: ${requirementPatches.length} PATCH)`;

      // --- 8. Emit RAW trace + verdict as evidence
      /* eslint-disable no-console */
      console.log(`\n===== RAW /api/v1/ TRACE (preset=${preset}) =====`);
      for (const e of trace) {
        console.log(`${e.method}\t${e.path}\t${e.status}`);
      }
      console.log(`----- PATCH requests (any /api/v1/): ${trace.filter((e) => e.method === 'PATCH').length}`);
      console.log(`----- requirement PATCHes: ${requirementPatches.length}`);
      console.log(`----- transitions/ GETs: ${transitionsGets.length} | ${JSON.stringify(transitionsGets)}`);
      console.log(`===== VERDICT (preset=${preset}): ${verdict} =====\n`);
      /* eslint-enable no-console */

      const report = {
        issue: 1239,
        preset,
        requirementId: REQUIREMENT_ID,
        verdict,
        patchStatus,
        requirementPatches,
        transitionsGets,
        trace,
      };
      await testInfo.attach(`issue-1239-trace-${preset}.json`, {
        body: JSON.stringify(report, null, 2),
        contentType: 'application/json',
      });

      // The measurement IS the assertion: issue #1239 claims 0 PATCHes, the
      // plan claims exactly 1. A non-1 count fails the test and the raw trace
      // above shows which requests were actually emitted.
      expect(
        requirementPatches.length,
        `PATCH count to /api/v1/requirements/${REQUIREMENT_ID}/ (preset=${preset})`
      ).toBe(1);
      if (patchStatus !== null) {
        expect(patchStatus, `PATCH status (preset=${preset})`).toBeLessThan(300);
      }
    });
  }
});
