/**
 * Shared test helper: mounts a component under a real `QueryClientProvider`.
 *
 * Components that read TanStack Query data (e.g. the artifact forms via
 * `useQualityBadge` / `useQualityHistory`) require a provider; a provider-less
 * component design only to keep tests simple is the wrong trade-off. Tests
 * adapt to the real architecture instead.
 *
 * The client disables retries so a test that never mocks a query still settles
 * in one request instead of backing off.
 */
import type { ReactElement, ReactNode } from "react";
import { render, type RenderResult } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

/** A per-test client with retries disabled (queries and mutations). */
export function createTestQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

/** Provider wrapper for callers that need to compose their own render tree. */
export function QueryClientTestWrapper({
  client,
  children,
}: {
  client: QueryClient;
  children: ReactNode;
}): JSX.Element {
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

/** `render()` under a fresh `QueryClientProvider`. */
export function renderWithQueryClient(
  ui: ReactElement,
  client: QueryClient = createTestQueryClient()
): RenderResult {
  return render(
    <QueryClientProvider client={client}>{ui}</QueryClientProvider>
  );
}
