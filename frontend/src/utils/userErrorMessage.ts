/**
 * One user-facing error message for every failed request.
 *
 * Before this helper every surface had its own one-liner (`err.message ??
 * String(err)`), so a raw transport failure leaked into alerts as
 * "TypeError: Failed to fetch" or "Load failed", while a 403 looked exactly
 * like a validation error. The helper classifies first, then falls back to the
 * server's structured message, and only then to a localised generic text.
 *
 * It is intentionally side-effect free and translator-injected: callers pass
 * the `t` from `useTranslation`, so this module has no i18n singletons and is
 * testable without a component tree.
 */
import type { TFunction } from "i18next";
import {
  RequestTimeoutError,
  extractApiErrorMessage,
  getApiErrorMeta,
} from "../api/client";

export type UserErrorCode =
  | "network"
  | "timeout"
  | "rate_limited"
  | "unauthorized"
  | "not_found"
  | "server"
  | "generic";

/** Raw browser strings that must never reach a user-facing alert. */
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

/** Classify a thrown value into the five cases the UI actually distinguishes. */
export function classifyUserError(err: unknown): UserErrorCode {
  if (err instanceof RequestTimeoutError) return "timeout";
  if (isTransportFailure(err)) return "network";

  const { status } = getApiErrorMeta(err);
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
  const classified = t(KEY_BY_CODE[code]);
  const detail = extractApiErrorMessage(err);

  // A server-provided message is more useful than the generic bucket only when
  // it is not one of the raw transport strings the classifier already caught.
  const usableDetail =
    detail && !TRANSPORT_MESSAGES.has(detail.trim().toLowerCase()) ? detail : null;

  const message =
    code === "generic" && usableDetail
      ? usableDetail
      : code === "unauthorized" && usableDetail
        ? usableDetail
        : classified;

  return context ? `${context} ${message}` : message;
}
