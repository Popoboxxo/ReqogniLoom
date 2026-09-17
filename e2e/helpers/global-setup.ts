/**
 * Playwright global setup (issue #947, point 1).
 *
 * Runs once per `playwright test` invocation, before any spec: verifies that
 * the frontend/backend are up, the demo seed exists and the tenant's global
 * attribute definitions are bootstrapped. A missing precondition aborts the
 * run with one actionable message instead of letting every spec fail with an
 * unrelated-looking error.
 *
 * See `helpers/preconditions.ts` for the checks and the rationale for not
 * seeding anything here.
 */
import { verifyE2eBootstrapPreconditions } from './preconditions';

export default async function globalSetup(): Promise<void> {
  console.log('E2E preconditions: verifying stack, demo seed and attribute definitions ...');
  await verifyE2eBootstrapPreconditions();
  console.log('E2E preconditions: OK');
}
