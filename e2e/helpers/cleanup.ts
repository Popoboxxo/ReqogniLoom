/**
 * Shared API-cleanup helpers for E2E specs (issue #947).
 *
 * Why this module exists
 * ----------------------
 * Several specs create their own Requirement fixtures and delete them again at
 * the end of the test. That cleanup was written as a bare
 *
 *     await request.delete(`${BACKEND_URL}/api/v1/requirements/${id}/`, { headers });
 *
 * in more than one place, which fails in two ways that are both invisible:
 *
 *  1. **No `change_reason`.** `RequirementService.delete_requirement` enforces
 *     the workspace's change_reason preset policy (#604) whenever that preset
 *     makes the reason mandatory — `extended` does (`mandatory`), `standard`
 *     does not (`optional`, the backend default). Against the seeded demo
 *     workspace, which runs `extended`, a body-less DELETE is answered with
 *     `400 VALIDATION_ERROR: change_reason is required by preset policy.`
 *  2. **The response was never inspected.** Playwright does not throw on a
 *     non-2xx `request.delete()`, so both the 400 above and any other failure
 *     were silently discarded and the fixture simply stayed behind. Re-runs then
 *     accumulate artifacts, and a later run's assertions start depending on what
 *     an earlier one left in the database — the state-pollution class #947 is
 *     about.
 *
 * Send the reason AND surface the failure: a broken cleanup is a test defect,
 * and it has to be visible.
 */
import { expect, type APIRequestContext } from '@playwright/test';

export const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

/** Default reason recorded on a cleanup delete, so the audit trail is explicit. */
export const CLEANUP_CHANGE_REASON = 'E2E fixture cleanup (see e2e/helpers/cleanup.ts)';

/**
 * Soft-delete a Requirement fixture via the API.
 *
 * @param request Playwright API context (or `page.request`).
 * @param token   Bearer token for the E2E admin.
 * @param id      Requirement id.
 * @param changeReason Override for the recorded reason (optional).
 *
 * @throws if the backend answers with anything but 2xx/404. A 404 counts as
 *   success: it means the fixture is already gone (an earlier phase removed it,
 *   or a previous run cleaned it up), which is the desired end state.
 */
export async function deleteRequirement(
  request: APIRequestContext,
  token: string,
  id: string,
  changeReason: string = CLEANUP_CHANGE_REASON
): Promise<void> {
  const response = await request.delete(
    `${BACKEND_URL}/api/v1/requirements/${id}/`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { change_reason: changeReason },
    }
  );
  if (!response.ok() && response.status() !== 404) {
    // expect() rather than a bare throw: it reports through Playwright so the
    // failure shows up with the response body attached to the test result.
    expect(
      response.status(),
      `deleteRequirement(${id}) failed — the fixture stays behind in the workspace`
    ).toBeLessThan(400);
  }
}
