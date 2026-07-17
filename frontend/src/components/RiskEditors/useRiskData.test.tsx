/**
 * Unit tests for useRiskData (REQ-049 TanStack Query migration).
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
import { useRiskData } from "./useRiskData";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/risks");
vi.mock("../../context/WorkspaceContext");

import * as risksModule from "../../api/risks";
import * as workspaceContext from "../../context/WorkspaceContext";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = { id: "ws-risk-001", name: "Safety Engineering WS", preset: "extended" };

const MOCK_RISK = {
  id: "risk-001",
  workspace_id: "ws-risk-001",
  title: "Data loss on primary database failover",
  description: "Unplanned failover may lose up to 5 minutes of transactions.",
  probability: "medium",
  impact: "high",
  mitigation: "Synchronous replication to hot standby with automated monitoring.",
  status: "Open",
  version: 2,
  created_at: "2026-02-15T08:30:00Z",
  updated_at: "2026-03-01T14:00:00Z",
};

// ---------------------------------------------------------------------------
// Wrapper factory
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

describe("useRiskData (REQ-049)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
  });

  it("[REQ-049] returns isLoading=true initially while list query is in-flight", () => {
    vi.mocked(risksModule.risksApi.listAll).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useRiskData(), { wrapper: createWrapper() });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.items).toEqual([]);
  });

  it("[REQ-049] populates items after list query resolves", async () => {
    vi.mocked(risksModule.risksApi.listAll).mockResolvedValue([MOCK_RISK] as any);

    const { result } = renderHook(() => useRiskData(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].id).toBe("risk-001");
    expect(result.current.items[0].title).toBe("Data loss on primary database failover");
  });

  it("[REQ-049] populates item after detail query resolves when selectedId is provided", async () => {
    vi.mocked(risksModule.risksApi.listAll).mockResolvedValue([MOCK_RISK] as any);
    vi.mocked(risksModule.risksApi.get).mockResolvedValue(MOCK_RISK as any);

    const { result } = renderHook(() => useRiskData("risk-001"), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.item).not.toBeNull());
    expect(result.current.item?.id).toBe("risk-001");
    expect(result.current.item?.status).toBe("Open");
  });

  it("[REQ-049] surfaces list error via error property", async () => {
    vi.mocked(risksModule.risksApi.listAll).mockRejectedValue(
      { error: { message: "workspace not found" } }
    );

    const { result } = renderHook(() => useRiskData(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe("workspace not found");
    expect(result.current.isLoading).toBe(false);
  });
});
