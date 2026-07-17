/**
 * Unit tests for useNeedData (REQ-049 TanStack Query migration).
 *
 * req_id: REQ-049, REQ-053
 *
 * Verifies:
 *   - isLoading=true initially while the list query is in-flight
 *   - needs populated after list query resolves
 *   - need populated after detail query resolves (selectedId provided)
 *   - error property set when list query rejects
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useNeedData } from "./useNeedData";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/stakeholder-need");
vi.mock("../../context/WorkspaceContext");

import * as needsModule from "../../api/stakeholder-need";
import * as workspaceContext from "../../context/WorkspaceContext";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = { id: "ws-need-001", name: "SE Programme Alpha", preset: "extended" };

const MOCK_NEED = {
  id: "need-001",
  workspace_id: "ws-need-001",
  title: "System shall provide real-time telemetry to ground control",
  description: "Ground operators require sub-second latency for safety-critical telemetry.",
  source: "Mission Operations Team",
  priority: "critical",
  status: "Approved",
  version: 1,
  created_at: "2026-01-20T07:00:00Z",
  updated_at: "2026-01-20T07:00:00Z",
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

describe("useNeedData (REQ-049)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
  });

  it("[REQ-049] returns isLoading=true initially while list query is in-flight", () => {
    vi.mocked(needsModule.stakeholderNeedApi.listAll).mockReturnValue(
      new Promise(() => {})
    );

    const { result } = renderHook(() => useNeedData(), { wrapper: createWrapper() });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.needs).toEqual([]);
  });

  it("[REQ-049] populates needs after list query resolves", async () => {
    vi.mocked(needsModule.stakeholderNeedApi.listAll).mockResolvedValue([MOCK_NEED] as any);

    const { result } = renderHook(() => useNeedData(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.needs).toHaveLength(1);
    expect(result.current.needs[0].id).toBe("need-001");
    expect(result.current.needs[0].title).toBe(
      "System shall provide real-time telemetry to ground control"
    );
  });

  it("[REQ-049] populates need after detail query resolves when selectedId is provided", async () => {
    vi.mocked(needsModule.stakeholderNeedApi.listAll).mockResolvedValue([MOCK_NEED] as any);
    vi.mocked(needsModule.stakeholderNeedApi.get).mockResolvedValue(MOCK_NEED as any);

    const { result } = renderHook(() => useNeedData("need-001"), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.need).not.toBeNull());
    expect(result.current.need?.id).toBe("need-001");
    expect(result.current.need?.priority).toBe("critical");
  });

  it("[REQ-049] surfaces list error via error property", async () => {
    vi.mocked(needsModule.stakeholderNeedApi.listAll).mockRejectedValue(
      { error: { message: "permission denied for this workspace" } }
    );

    const { result } = renderHook(() => useNeedData(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe("permission denied for this workspace");
  });
});
