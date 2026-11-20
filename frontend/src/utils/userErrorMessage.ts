/**
 * One user-facing error message for every failed request.
 *
 * Before this helper every surface had its own one-liner (`err.message ??
 * String(err)`), so a raw transport failure leaked into alerts as
 * "TypeError: Failed to fetch" or "Load failed", while a 403 looked exactly
 * like a validation error. The helper classifies first, then falls back to the
 * server's structured message, and only then to a localised generic text.
 *
 * It is intentionally side-effect free, translator-injected and **does not
 * import the API client**: component tests routinely `vi.mock` that module with
 * only the functions the component itself used, and a module-level import here
 * would turn those partial doubles into "No export defined" failures. The
 * error shapes are read structurally instead.
 */
import type { TFunction } from "i18next";

export type UserErrorCode =
  | "network"
  | "timeout"
  | "rate_limited"
  | "unauthorized"
  | "not_found"
  | "server"
  | "generic";

/** Raw browser transport strings that must never reach a user-facing alert. */
const TRANSPORT_MESSAGES = new Set([
  "failed to fetch",
  "load failed",
  "networkerror when attempting to fetch resource.",
  "network request failed",
  "the network connection was lost.",
]);

function isTransportFailure(err: unknown): boolean {
  if (err instanceof TypeError) return true;
  if (err instanceof Error) {
    return TRANSPORT_MESSAGES.has(err.message.trim().toLowerCase());
  }
  return false;
}

interface ErrorDetail {
  field?: unknown;
  errors?: unknown;
}

interface ErrorMeta {
  status?: number;
  message?: string;
  details: ErrorDetail[];
}

/**
 * Read the typed `ApiRequestError` fields (and the legacy plain envelope)
 * structurally, so a mocked client cannot break the helpers downstream.
 */
function readErrorMeta(err: unknown): ErrorMeta {
  const candidate = err as
    | {
        status?: unknown;
        message?: unknown;
        details?: unknown;
        error?: { message?: unknown; details?: unknown };
      }
    | null
    | undefined;
  const body = candidate?.error;
  const status =
    typeof candidate?.status === "number" ? candidate.status : undefined;
  const rawMessage =
    typeof body?.message === "string"
      ? body.message
      : typeof candidate?.message === "string"
        ? candidate.message
        : undefined;
  const rawDetails = Array.isArray(candidate?.details)
    ? candidate.details
    : Array.isArray(body?.details)
      ? body.details
      : [];
  return {
    status,
    message: rawMessage,
    details: rawDetails.filter(
      (detail): detail is ErrorDetail =>
        detail !== null && typeof detail === "object"
    ),
  };
}

/** First field-level message, qualified with the field the server named. */
function firstDetailMessage(details: ErrorDetail[]): string | null {
  const detail = details[0];
  if (!detail) return null;
  const errors = Array.isArray(detail.errors) ? detail.errors : [];
  const first = errors.find((value): value is string => typeof value === "string");
  if (!first) return null;
  return typeof detail.field === "string" && detail.field
    ? `${detail.field}: ${first}`
    : first;
}

/** Classify a thrown value into the five cases the UI actually distinguishes. */
export function classifyUserError(err: unknown): UserErrorCode {
  // The client's timeout error carries this name; checking the name instead of
  // the class keeps the helper working with mocked api/client modules.
  if (err instanceof Error && err.name === "RequestTimeoutError") return "timeout";
  if (isTransportFailure(err)) return "network";

  const { status } = readErrorMeta(err);
  if (status === 429) return "rate_limited";
  if (status === 401 || status === 403) return "unauthorized";
  if (status === 404) return "not_found";
  if (typeof status === "number" && status >= 500) return "server";
  return "generic";
}

const KEY_BY_CODE: Record<UserErrorCode, string> = {
  network: "errors.network",
  timeout: "errors.timeout",
  rate_limited: "errors.rate_limited",
  unauthorized: "errors.unauthorized",
  not_found: "errors.not_found",
  server: "errors.server",
  generic: "errors.generic",
};

/**
 * Return the message to render for *err*.
 *
 * ``context`` is an optional already-localised prefix (e.g. "Speichern
 * fehlgeschlagen.") kept for callers whose existing UX names the operation;
 * the classified cause follows it.
 */
export function toUserErrorMessage(
  err: unknown,
  t: TFunction,
  context?: string
): string {
  const code = classifyUserError(err);
  const meta = readErrorMeta(err);
  const classified = t(KEY_BY_CODE[code]);
  const detail = firstDetailMessage(meta.details) ?? meta.message ?? null;

  // A server-provided message is more useful than the generic bucket only when
  // it is not one of the raw transport strings the classifier already caught.
  const usableDetail =
    detail && !TRANSPORT_MESSAGES.has(detail.trim().toLowerCase()) ? detail : null;

  const message =
    (code === "generic" || code === "unauthorized") && usableDetail
      ? usableDetail
      : classified;

  return context ? `${context} ${message}` : message;
}
