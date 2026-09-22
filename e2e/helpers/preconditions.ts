/**
 * E2E bootstrap preconditions (issue #947, point 1).
 *
 * The suite drives a real stack and assumes four things that no test can
 * meaningfully assert on its own:
 *
 *   1. the frontend dev server is serving,
 *   2. the backend is serving and accepts the E2E admin credentials,
 *   3. the demo tenant/workspace from `manage.py seed_demo` exists,
 *   4. the tenant's global attribute definitions exist
 *      (`manage.py bootstrap_attribute_definitions`).
 *
 * When any of them is missing, every downstream spec fails with an error that
 * names the *symptom* rather than the cause: a missing frontend looks like a
 * `page.goto` navigation timeout, a missing seed looks like "workspace not
 * found", and — the case that cost a full-suite triage in issue #947 — missing
 * attribute definitions make every editor render
 * "No global attribute definition for '<ItemType>/<preset>'" and cascade into
 * dozens of unrelated red specs.
 *
 * This module verifies those preconditions up front (wired as Playwright
 * `globalSetup`, see `playwright.config.ts`) and throws ONE error naming the
 * missing precondition plus the exact command that fixes it.
 *
 * It deliberately does *not* seed anything itself: CI
 * (`.github/workflows/playwright.yml`) runs `migrate` + `seed_demo` +
 * `seed_toothbrush` + `bootstrap_attribute_definitions` before the tests, and
 * the dev stack self-initialises the base tenant (including the attribute
 * definitions, see `backend/application/self_init.py`) on `migrate` — a second,
 * hidden seeding path here would only mask a broken setup.
 */
import { request } from '@playwright/test';
import { SEEDED_WORKSPACE_ID, TEST_USER } from './auth';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';
const FRONTEND_URL = process.env.FRONTEND_URL || 'http://localhost:5173';

/** Per-request cap so an unreachable/hung service fails with our message. */
const PROBE_TIMEOUT_MS = 15000;

/**
 * `seed_toothbrush`'s WORKSPACE_NAME (see tests/toothbrush-syseng.spec.ts).
 * Matched leniently because the literal contains a non-ASCII character that
 * does not survive every console/CI encoding round-trip.
 */
const TOOTHBRUSH_WORKSPACE_PATTERN = /Zahnb.rste SysEng Demo/i;

const SEED_DEMO_HINT =
  'docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml ' +
  '--project-directory . exec backend python manage.py seed_demo';

const SEED_TOOTHBRUSH_HINT =
  'docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml ' +
  '--project-directory . exec backend python manage.py seed_toothbrush';

/**
 * Verify the stack/seed preconditions for a run.
 *
 * @throws Error with an actionable, multi-line message naming the missing
 *   precondition and the command that fixes it — never a bare status code.
 */
export async function verifyE2eBootstrapPreconditions(): Promise<void> {
  const ctx = await request.newContext({ baseURL: BACKEND_URL });
  try {
    await requireReachable(ctx, FRONTEND_URL, 'frontend', [
      `The Playwright baseURL ${FRONTEND_URL} is not answering.`,
      'Start (or restart) the dev stack first: `make up` — or point the run at a',
      'running stack with FRONTEND_URL=<url>.',
    ]);

    // `/health/` (the container readiness probe) rather than `/api/v1/schema/`:
    // the schema endpoint regenerates the whole OpenAPI document on demand
    // (drf-spectacular) and can exceed a liveness-probe budget under load,
    // which would report a healthy backend as unreachable.
    await requireReachable(ctx, '/health/', 'backend', [
      `The backend ${BACKEND_URL} is not answering.`,
      'Start (or restart) the dev stack first: `make up` — or point the run at a',
      'running stack with BACKEND_URL=<url> (the dev compose default is 8001).',
    ]);

    const token = await loginOrThrow(ctx);

    // seed_demo: the demo tenant's workspace must exist. Without it every
    // workspace-scoped spec fails against a phantom workspace id.
    const workspace = await ctx.get(`/api/v1/workspaces/${SEEDED_WORKSPACE_ID}/`, {
      headers: { Authorization: `Bearer ${token}` },
      timeout: PROBE_TIMEOUT_MS,
    });
    if (!workspace.ok()) {
      throw new Error(
        [
          'E2E precondition failed: the seeded demo workspace is missing.',
          `GET /api/v1/workspaces/${SEEDED_WORKSPACE_ID}/ returned ${workspace.status()}.`,
          '',
          'The suite is pinned to the workspace created by `seed_demo`. Seed it with:',
          `  ${SEED_DEMO_HINT}`,
          '',
          '(`seed_demo` is idempotent — re-running it is safe.)',
        ].join('\n')
      );
    }

    // bootstrap_attribute_definitions: without the tenant's global attribute
    // definitions every artifact editor renders
    //   "No global attribute definition for '<ItemType>/<preset>'"
    // instead of its fields (issue #947).
    await requireGlobalAttributeDefinitions(ctx, token);

    // seed_toothbrush: optional — only tests/toothbrush-syseng.spec.ts needs
    // the ~880-artifact fixture, and that spec deliberately skips with an
    // actionable message when it is absent. Hard-failing the whole run here
    // would make an intentionally-skipped heavy fixture block every other
    // spec, so this stays a warning that names the command.
    await warnIfToothbrushMissing(ctx, token);
  } finally {
    await ctx.dispose();
  }
}

async function requireReachable(
  ctx: Awaited<ReturnType<typeof request.newContext>>,
  url: string,
  label: string,
  message: string[]
): Promise<void> {
  let response: Awaited<ReturnType<typeof ctx.get>>;
  try {
    response = await ctx.get(url, { timeout: PROBE_TIMEOUT_MS });
  } catch (err) {
    throw new Error(
      [
        `E2E precondition failed: ${label} is not reachable.`,
        ...message,
        '',
        `Probe: GET ${url}`,
        `Error: ${(err as Error).message}`,
      ].join('\n')
    );
  }
  if (!response.ok()) {
    throw new Error(
      [
        `E2E precondition failed: ${label} answered, but is not healthy.`,
        ...message,
        '',
        `Probe: GET ${url} -> ${response.status()}`,
        `Body: ${(await response.text()).slice(0, 500)}`,
      ].join('\n')
    );
  }
}

async function loginOrThrow(
  ctx: Awaited<ReturnType<typeof request.newContext>>
): Promise<string> {
  const response = await ctx.post('/api/v1/auth/login/', {
    data: { username: TEST_USER.username, password: TEST_USER.password },
    timeout: PROBE_TIMEOUT_MS,
  });
  if (response.status() === 401) {
    throw new Error(
      [
        'E2E precondition failed: the E2E admin credentials were rejected (401).',
        `Tried: ${TEST_USER.username} / ${process.env.E2E_ADMIN_PASSWORD ? '<E2E_ADMIN_PASSWORD>' : '<seed_demo default>'}.`,
        '',
        'A local .env with its own SYSTEM_ADMIN_PASSWORD makes every login fail here',
        'and the failure then surfaces as an unrelated per-spec error (see the README',
        'section "End-to-End Tests (Playwright)", pitfall 1). Either re-seed with the',
        'E2E default:',
        '  docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml ' +
          '--project-directory . exec -e SYSTEM_ADMIN_PASSWORD=admin12345 backend python manage.py seed_demo --reset-password',
        'or run Playwright with E2E_ADMIN_PASSWORD=<your .env password>.',
      ].join('\n')
    );
  }
  if (!response.ok()) {
    throw new Error(
      `E2E precondition failed: POST /api/v1/auth/login/ returned ${response.status()} ${await response.text()}`
    );
  }
  const body = await response.json();
  const token = body.token || body.access || body.access_token;
  if (!token) {
    throw new Error(
      `E2E precondition failed: login succeeded but returned no token: ${JSON.stringify(body)}`
    );
  }
  return token as string;
}

async function requireGlobalAttributeDefinitions(
  ctx: Awaited<ReturnType<typeof request.newContext>>,
  token: string
): Promise<void> {
  const response = await ctx.get('/api/v1/attribute-defaults/', {
    headers: { Authorization: `Bearer ${token}` },
    timeout: PROBE_TIMEOUT_MS,
  });
  if (!response.ok()) {
    throw new Error(
      `E2E precondition failed: GET /api/v1/attribute-defaults/ returned ${response.status()} ${await response.text()}`
    );
  }
  const body = await response.json();
  const definitions: Array<{ item_type?: string; initialized?: boolean }> =
    body.definitions ?? [];
  const requirementReady = definitions.some(
    (d) => d.item_type === 'Requirement' && d.initialized !== false
  );
  if (!requirementReady) {
    throw new Error(
      [
        "E2E precondition failed: the tenant has no global attribute definitions for 'Requirement'.",
        'Every artifact editor would render "No global attribute definition for',
        "<ItemType>/<preset>' instead of its fields (issue #947).",
        '',
        'Run the bootstrap command:',
        '  docker compose -f deploy/docker-compose.yml -f deploy/docker-compose.override.yml ' +
          '--project-directory . exec backend python manage.py bootstrap_attribute_definitions',
        '',
        'It is idempotent. On most stacks `manage.py migrate` already seeds them via',
        'the REQ-188 post_migrate self-init (self_init.py calls',
        'bootstrap_attribute_definitions for the tenant it provisions). A miss here',
        'therefore means one of: migrate never ran, the stack has no',
        'SYSTEM_ADMIN_PASSWORD so the self-init returned early on a fresh database,',
        'or the self-init bootstrap threw — self_init only logs that, it cannot raise',
        'inside post_migrate.',
      ].join('\n')
    );
  }
}

async function warnIfToothbrushMissing(
  ctx: Awaited<ReturnType<typeof request.newContext>>,
  token: string
): Promise<void> {
  const headers = { Authorization: `Bearer ${token}` };
  // page_size is honored by the workspace list endpoint; keep following `next`
  // regardless, because a local dev DB accumulates hundreds of throwaway
  // workspaces (every visual-regression run creates one) and the fixture can
  // end up on a later page.
  let url: string | null = '/api/v1/workspaces/?page_size=200';
  let attempts = 0;
  try {
    while (url && attempts < 10) {
      attempts += 1;
      const response: Awaited<ReturnType<typeof ctx.get>> = await ctx.get(url, {
        headers,
        timeout: PROBE_TIMEOUT_MS,
      });
      if (!response.ok()) {
        return; // listing failed — not this guard's job to report
      }
      const body = await response.json();
      const items: Array<{ name?: string }> = Array.isArray(body)
        ? body
        : body.results ?? [];
      if (items.some((w) => TOOTHBRUSH_WORKSPACE_PATTERN.test(w.name ?? ''))) {
        return;
      }
      url = Array.isArray(body) ? null : body.next ?? null;
    }
  } catch {
    return; // warning only — never block a run on the optional fixture probe
  }
  console.warn(
    [
      'E2E precondition warning: the seed_toothbrush fixture workspace is missing.',
      'tests/toothbrush-syseng.spec.ts will SKIP (all other specs are unaffected).',
      `To include it, run: ${SEED_TOOTHBRUSH_HINT}  # idempotent`,
    ].join('\n')
  );
}
