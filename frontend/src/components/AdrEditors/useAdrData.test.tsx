/**
 * Unit tests for useAdrData (REQ-049 TanStack Query migration).
 *
 * req_id: REQ-049, REQ-053
 *
 * Verifies:
 *   - isLoading=true initially while the list query is in-flight
 *   - items populated after list query resolves
 *   - item populated after detail query resolves (selectedId provided)
 *   - error property set when list query rejects
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useAdrData } from "./useAdrData";

// ---------------------------------------------------------------------------
// Module mocks (hoisted by vitest)
// ---------------------------------------------------------------------------

vi.mock("../../api/adrs");
vi.mock("../../context/WorkspaceContext");

import * as adrsModule from "../../api/adrs";
import * as workspaceContext from "../../context/WorkspaceContext";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = { id: "ws-adr-001", name: "Systems Engineering WS", preset: "standard" };

const MOCK_ADR = {
  id: "adr-001",
  workspace_id: "ws-adr-001",
  title: "Adopt event sourcing for domain commands",
  description: "Use an append-only event log as the system of record.",
  context: "High write throughput and full audit trail required.",
  consequences: "Replay complexity; eventual consistency in read models.",
  status: "Accepted",
  version: 1,
  created_at: "2026-01-10T09:00:00Z",
  updated_at: "2026-01-10T09:00:00Z",
};

// ---------------------------------------------------------------------------
// Wrapper factory — fresh QueryClient per test to avoid cross-test cache
// ---------------------------------------------------------------------------

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
};

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useAdrData (REQ-049)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
  });

  it("[REQ-049] returns isLoading=true initially while list query is in-flight", () => {
    // Never-resolving promise keeps the query pending
    vi.mocked(adrsModule.adrsApi.list).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useAdrData(), { wrapper: createWrapper() });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.items).toEqual([]);
  });

  it("[REQ-049] populates items after list query resolves", async () => {
    vi.mocked(adrsModule.adrsApi.list).mockResolvedValue({
      results: [MOCK_ADR],
      count: 1,
    } as any);

    const { result } = renderHook(() => useAdrData(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].id).toBe("adr-001");
    expect(result.current.items[0].title).toBe("Adopt event sourcing for domain commands");
  });

  it("[REQ-049] populates item after detail query resolves when selectedId is provided", async () => {
    vi.mocked(adrsModule.adrsApi.list).mockResolvedValue({
      results: [MOCK_ADR],
      count: 1,
    } as any);
    vi.mocked(adrsModule.adrsApi.get).mockResolvedValue(MOCK_ADR as any);

    const { result } = renderHook(() => useAdrData("adr-001"), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.item).not.toBeNull());
    expect(result.current.item?.id).toBe("adr-001");
    expect(result.current.item?.status).toBe("Accepted");
  });

  it("[REQ-049] surfaces list error via error property", async () => {
    vi.mocked(adrsModule.adrsApi.list).mockRejectedValue(
      { error: { message: "Forbidden: missing workspace access" } }
    );

    const { result } = renderHook(() => useAdrData(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe("Forbidden: missing workspace access");
    expect(result.current.isLoading).toBe(false);
  });

  it("[REQ-049] returns empty items when no workspace is active", () => {
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: null,
    } as any);
    vi.mocked(adrsModule.adrsApi.list).mockResolvedValue({
      results: [],
      count: 0,
    } as any);

    const { result } = renderHook(() => useAdrData(), { wrapper: createWrapper() });

    // query is disabled — isLoading stays false, items stays empty
    expect(result.current.isLoading).toBe(false);
    expect(result.current.items).toEqual([]);
  });
});
