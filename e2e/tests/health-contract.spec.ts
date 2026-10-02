// W1 / RES-03, RES-04, RES-05: health contract E2E (ADR-010).
//
// The container probes and the admin health surface rely on this HTTP
// contract; before this spec there was no E2E coverage for it (only
// backend unit tests in `reqogniloom/tests/test_health*`). These are pure
// request-level tests: they pin
//
//   * `/health/live`  -> always 200, never probes a dependency (restart-safe),
//   * `/health/ready` -> 200 only while every mandatory dependency is `ok`,
//   * `/health/`      -> deprecated alias that mirrors readiness and carries
//                        the `Deprecation`/`Sunset` headers.
//
// The readiness spec asserts the *healthy* contract (all mandatory checks ok,
// no `dependencies` breaches). A red readiness on a broken stack must fail
// here instead of being papered over: that is precisely what RES-03/04/05
// protect.
import { test, expect } from '@playwright/test';

const BACKEND_URL = process.env.BACKEND_URL || 'http://localhost:8001';

// ADR-010 §2: the mandatory readiness set, in public contract order.
const MANDATORY_CHECKS = [
  'database',
  'memory_backend',
  'cache',
  'celery_worker',
  'celery_beat',
];

test.describe('[RES-03/04/05] Health contract', () => {
  test('[RES-03] /health/live is always 200 and never probes a dependency', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/health/live`);

    expect(response.status()).toBe(200);
    const body = await response.json();
    expect(body.status).toBe('ok');
    // Liveness must not disclose or evaluate dependencies: `checks` stays empty.
    expect(body.checks).toEqual({});
  });

  test('[RES-04] /health/ready is 200 with every mandatory dependency ok', async ({ request }) => {
    const response = await request.get(`${BACKEND_URL}/health/ready`);

    expect(response.status()).toBe(200);
    const body = await response.json();
    // `ok` = fully healthy, `warning` = healthy with advisory notices only.
    expect(['ok', 'warning']).toContain(body.status);
    expect(Object.keys(body.checks).sort()).toEqual([...MANDATORY_CHECKS].sort());
    for (const name of MANDATORY_CHECKS) {
      expect(body.checks[name]).toBe('ok');
    }
    // No mandatory dependency may be listed as down.
    expect(body.dependencies).toEqual([]);
  });

  test('[RES-05] /health/ alias mirrors readiness and advertises deprecation', async ({ request }) => {
    const ready = await request.get(`${BACKEND_URL}/health/ready`);
    const alias = await request.get(`${BACKEND_URL}/health/`);

    expect(alias.status()).toBe(ready.status());

    const readyBody = await ready.json();
    const aliasBody = await alias.json();
    expect(aliasBody.status).toBe(readyBody.status);
    expect(aliasBody.checks).toEqual(readyBody.checks);

    const headers = alias.headers();
    expect(headers['deprecation']).toBe('true');
    expect(headers['sunset']).toBeTruthy();
  });
});
