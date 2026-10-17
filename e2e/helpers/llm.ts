/**
 * Provider-aware guard for specs that exercise LLM-backed endpoints.
 *
 * Triage of issues #1343 / #1344 / #1345 (W16, 2026-10-17). All three failed in
 * a *local* full run with:
 *
 *   TimeoutError: apiRequestContext.post: Timeout 15000ms exceeded.
 *
 * The cause is environment drift, not a product defect:
 *
 *  - CI runs the stack with `LLM_PROVIDER=mock` (see
 *    `.github/workflows/playwright.yml`), so a derive-requirements request
 *    answers in ~0.1 s. The same specs passed in 72-133 ms in the committed
 *    local run logs (`e2e/run-c.log`, `e2e/run-f.log`).
 *  - A developer stack may instead be pointed at a real provider (this one:
 *    `LLM_PROVIDER=opencode_go`, model `mimo-v2.5`). A single
 *    derive-requirements call was measured at 45.9 s and 73.8 s on
 *    2026-10-17 and answered correctly (HTTP 200 with real drafts) - it is
 *    model latency, not a hang.
 *  - Playwright's `request` fixture inherits `use.actionTimeout` (15 s in
 *    `playwright.config.ts`) through `playwright._defaultContextTimeout`
 *    (playwright/lib/index.js), which is exactly where the "15000ms" in the
 *    error text comes from.
 *
 * Do NOT raise the global `actionTimeout`: that would hide real hangs in every
 * other spec. Instead:
 *
 *  - provider == "mock" (CI)     -> unchanged, tight 15 s request budget.
 *  - provider != "mock" (local)  -> skip with an actionable hint: the
 *    assertions ("drafts contain title/description") can only be evaluated
 *    after a real model completion, which is minutes of extra wall clock in a
 *    full run. Opt in to that slow run with `E2E_REAL_LLM=1`; the request then
 *    gets `REAL_LLM_REQUEST_TIMEOUT_MS` and the test is marked slow (180 s).
 *
 * See `e2e/TESTING.md` ("LLM-backed specs") for the operator-facing note.
 */
import type { APIRequestContext } from '@playwright/test';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

/**
 * Budget for one real-provider completion, in ms.
 *
 * Aligned with the backend's own long-running LLM budget
 * (`LLM_LONG_RUNNING_TIMEOUT`, default 180 s, `llm_adapter/timeouts.py`). The
 * observed local latency was 46-74 s per call; 180 s leaves headroom for a
 * slower provider without turning a genuine hang into a pass.
 */
export const REAL_LLM_REQUEST_TIMEOUT_MS = 180_000;

/**
 * Read the provider the *running* stack is configured with.
 *
 * `GET /api/v1/llm-settings/` is the admin-facing, tenant-scoped singleton
 * (REQ-L2-LLM-001); the E2E admin can read it. Returns `null` when the probe
 * itself fails (old backend, endpoint unavailable), in which case callers keep
 * the tight default budget instead of guessing.
 */
export async function getLlmProvider(
  request: APIRequestContext,
  token: string
): Promise<string | null> {
  try {
    const response = await request.get(`${BACKEND_URL}/api/v1/llm-settings/`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!response.ok()) return null;
    const body = (await response.json()) as { provider?: unknown };
    return typeof body.provider === 'string' ? body.provider : null;
  } catch {
    return null;
  }
}

/**
 * Reason to skip an LLM-backed test, or `null` when it should run.
 *
 * A `null` provider (probe unavailable) does not skip: the endpoint then most
 * likely runs the credential-free mock provider, which is fast.
 */
export function llmSkipHint(provider: string | null): string | null {
  if (provider === null || provider === 'mock') return null;
  if (process.env.E2E_REAL_LLM === '1') return null;
  return (
    `This stack runs LLM_PROVIDER='${provider}', not 'mock'. The test asserts on ` +
    'a real model completion (measured 46-74 s per derive-requirements call on ' +
    '2026-10-17) instead of the ~0.1 s mock answer, so it stays skipped in the ' +
    'default budget. Re-run with E2E_REAL_LLM=1 to exercise it with a 180 s ' +
    'request budget, or point the stack at LLM_PROVIDER=mock (CI does).'
  );
}

/**
 * Explicit per-request timeout for a real provider, `undefined` for mock
 * (inherit the config default so a slow mock call still fails fast).
 */
export function llmRequestTimeoutMs(provider: string | null): number | undefined {
  return provider !== null && provider !== 'mock'
    ? REAL_LLM_REQUEST_TIMEOUT_MS
    : undefined;
}
