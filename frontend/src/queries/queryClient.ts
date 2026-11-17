/**
 * ARCH-L1-001 ReactFrontend — TanStack Query client.
 *
 * Central QueryClient instance shared by all query/mutation hooks.
 * Retries use exponential backoff capped at 30s. The policy is
 * *status-aware*: 4xx responses are deterministic client errors and are
 * never retried, except 408 (Request Timeout) and 429 (Too Many Requests),
 * which are transient. Network failures and 5xx responses are retried up to
 * three attempts. (A naive "auth errors are already excluded" assumption is
 * wrong: a 403 Forbidden is not an auth failure and used to be retried.)
 */

import { QueryClient } from "@tanstack/react-query";
import { ApiRequestError } from "../api/errors";
import type { ApiError } from "../types";

function isAuthError(err: unknown): boolean {
  // Prefer the typed envelope of R2A-006's ApiRequestError; keep the legacy
  // shape as a fallback for hand-built objects/mocks that bypass apiClient.
  const code =
    err instanceof ApiRequestError
      ? err.code
      : (err as Partial<ApiError> | null)?.error?.code;
  return code === "AUTHENTICATION_REQUIRED";
}

/** Retry predicate for queries: transient failures only, capped at 3 attempts. */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (error instanceof ApiRequestError) {
    const { status } = error;
    if (status >= 400 && status < 500 && status !== 408 && status !== 429) {
      return false;
    }
  } else if (isAuthError(error)) {
    return false;
  }
  return failureCount < 3;
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: shouldRetryQuery,
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
    },
    mutations: {
      retry: false,
    },
  },
});
