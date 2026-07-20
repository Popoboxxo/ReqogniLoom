/**
 * ARCH-L1-001 ReactFrontend — API error types.
 *
 * req_id: REQ-051 (distinguish 401 logout from 403 permission error)
 */

/**
 * Thrown when the API responds with HTTP 403 Forbidden. Unlike a 401
 * (which clears auth state and redirects to login), a 403 means the user
 * is authenticated but lacks permission for the requested action. Callers
 * should surface the message without logging the user out.
 */
export class ForbiddenError extends Error {
  readonly status = 403;

  constructor(message = "You do not have permission to perform this action.") {
    super(message);
    this.name = "ForbiddenError";
  }
}

/**
 * Thrown when the API responds with HTTP 422 Unprocessable Entity — a
 * request that is well-formed but cannot be applied (e.g. the SE-Auditor
 * remediate endpoint refusing a finding without an unambiguous auto-fix,
 * UMSETZUNGSPLAN_SYSENG_2.0.md §4). Distinct from a generic 400 so callers
 * can switch their UI into a "Modify" / manual-correction state instead of
 * showing a plain validation error.
 */
export class UnprocessableEntityError extends Error {
  readonly status = 422;

  constructor(message = "This action cannot be applied automatically.") {
    super(message);
    this.name = "UnprocessableEntityError";
  }
}
