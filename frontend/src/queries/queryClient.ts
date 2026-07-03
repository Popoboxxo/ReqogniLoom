/**
 * ARCH-L1-001 ReactFrontend — TanStack Query client.
 *
 * Central QueryClient instance shared by all query/mutation hooks.
 * Retries use exponential backoff capped at 30s; auth failures
 * (401/403 → AUTHENTICATION_REQUIRED) are not retried since apiClient
 * already redirects to /login on those.
 */

import { QueryClient } from "@tanstack/react-query";
import type { ApiError } from "../types";

function isAuthError(err: unknown): boolean {
  return (err as Partial<ApiError>)?.error?.code === "AUTHENTICATION_REQUIRED";
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: (failureCount, error) => {
        if (isAuthError(error)) return false;
        return failureCount < 3;
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 30_000),
    },
    mutations: {
      retry: false,
    },
  },
});
