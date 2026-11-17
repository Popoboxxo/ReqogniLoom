/**
 * ARCH-L1-001 ReactFrontend — API error types.
 *
 * req_id: REQ-051 (distinguish 401 logout from 403 permission error)
 *
 * Every non-2xx response is surfaced as an {@link ApiRequestError} carrying the
 * stable fields of the backend error envelope (`code`, `details`, `request_id`)
 * plus the HTTP `status`. The two pre-existing subclasses stay in place so
 * callers' `instanceof` checks and constructor calls keep working unchanged.
 */

import type { ApiErrorDetail } from "../types";

/** Fields used to construct an {@link ApiRequestError}. */
export interface ApiRequestErrorFields {
  status: number;
  message?: string;
  code?: string;
  details?: ApiErrorDetail[];
  requestId?: string;
}

/**
 * Common base for every error thrown by the API client on a non-2xx response.
 *
 * `error` mirrors the raw `{ error: { code, message, details } }` envelope so
 * the many existing consumers that read `err.error.code` directly keep working
 * — the structured fields below are additive, not a replacement.
 */
export class ApiRequestError extends Error {
  readonly status: number;
  readonly code?: string;
  readonly details: ApiErrorDetail[];
  readonly requestId?: string;
  readonly error: { code: string; message: string; details: ApiErrorDetail[] };

  constructor(fields: ApiRequestErrorFields) {
    super(fields.message ?? "");
    this.name = "ApiRequestError";
    this.status = fields.status;
    this.code = fields.code;
    this.details = fields.details ?? [];
    this.requestId = fields.requestId;
    this.error = {
      code: fields.code ?? "UNKNOWN_ERROR",
      message: fields.message ?? "",
      details: this.details,
    };
  }
}

/**
 * Thrown when the API responds with HTTP 403 Forbidden. Unlike a 401
 * (which clears auth state and redirects to login), a 403 means the user
 * is authenticated but lacks permission for the requested action. Callers
 * should surface the message without logging the user out.
 */
export class ForbiddenError extends ApiRequestError {
  constructor(
    message = "You do not have permission to perform this action.",
    code?: string,
    details?: ApiErrorDetail[],
    requestId?: string
  ) {
    super({
      status: 403,
      message,
      code: code ?? "PERMISSION_DENIED",
      details,
      requestId,
    });
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
export class UnprocessableEntityError extends ApiRequestError {
  /**
   * UI-40: structured per-violation detail, when the backend supplied one
   * (e.g. `DecompositionAuditError.findings` — the SE-Auditor/invariant
   * findings that caused an architecture-decompose commit to roll back).
   * Previously dropped entirely by the generic 422 handler in
   * `client.ts`, forcing callers to render the flat `message` string as an
   * unstructured wall of text instead of a per-finding list.
   */
  readonly findings?: ReadonlyArray<Record<string, unknown>>;

  constructor(
    message = "This action cannot be applied automatically.",
    findings?: ReadonlyArray<Record<string, unknown>>,
    code?: string,
    details?: ApiErrorDetail[],
    requestId?: string
  ) {
    super({ status: 422, message, code, details, requestId });
    this.name = "UnprocessableEntityError";
    this.findings = findings;
  }
}

/** Normalised view of an error response body, independent of its exact shape. */
export interface ParsedApiErrorBody {
  message?: string;
  detail?: string;
  code?: string;
  details: ApiErrorDetail[];
  requestId?: string;
  findings?: Array<Record<string, unknown>>;
}

/**
 * Read the backend error envelope (and DRF's flat `detail`, plus the
 * `request_id` correlation id added in S1.1a) without ever throwing on a
 * non-JSON or empty body.
 */
export function parseApiErrorBody(body: unknown): ParsedApiErrorBody {
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    return { details: [] };
  }
  const record = body as Record<string, unknown>;
  const envelope =
    record.error !== null &&
    typeof record.error === "object" &&
    !Array.isArray(record.error)
      ? (record.error as Record<string, unknown>)
      : undefined;

  const message =
    typeof envelope?.message === "string" ? envelope.message : undefined;
  const detail = typeof record.detail === "string" ? record.detail : undefined;
  const code = typeof envelope?.code === "string" ? envelope.code : undefined;
  const details = Array.isArray(envelope?.details)
    ? (envelope.details as ApiErrorDetail[])
    : [];
  const requestId =
    typeof record.request_id === "string" ? record.request_id : undefined;
  const findings = Array.isArray(record.findings)
    ? (record.findings as Array<Record<string, unknown>>)
    : undefined;

  return { message, detail, code, details, requestId, findings };
}
