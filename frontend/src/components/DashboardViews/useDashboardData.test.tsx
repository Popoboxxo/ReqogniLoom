/**
 * Unit tests for useDashboardData (REQ-119 TanStack Query migration).
 *
 * req_id: REQ-119, REQ-049
 *
 * Verifies:
 *   - isLoading=true while workspace/requirement bootstrap is in-flight
 *   - workspaces enriched with requirement_count/open_item_count after load
 *   - per-workspace fetch failure degrades to zero metrics, not a global error
 *   - dashboard counts re-fetch when the shared requirementKeys.list cache
 *     entry is invalidated (the same key useCreateRequirement/
 *     useUpdateRequirement/useDeleteRequirement invalidate on success)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useDashboardData } from "./useDashboardData";
import { requirementKeys } from "../../queries/requirements";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/requirements");
vi.mock("../../context/WorkspaceContext");

import * as requirementsModule from "../../api/requirements";
import * as workspaceContext from "../../context/WorkspaceContext";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = {
  id: "ws-dash-001",
  name: "Dashboard WS",
  preset: "standard",
  terminology_profile: "dev_mode",
  language: "en",
  is_active: true,
  closed_at: null,
  closed_by: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const MOCK_REQ = (id: string, status: string) => ({
  id,
  workspace_id: MOCK_WORKSPACE.id,
  title: `Requirement ${id}`,
  description: "",
  category: "functional",
  status,
  version: 1,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
});

// ---------------------------------------------------------------------------
// Wrapper factory
// ---------------------------------------------------------------------------

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

function newQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useDashboardData (REQ-119)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      workspaces: [MOCK_WORKSPACE],
      activeWorkspace: MOCK_WORKSPACE,
      isLoadingWorkspace: false,
    } as any);
  });

  it("[REQ-119] returns isLoading=true while the requirement query is in-flight", () => {
    vi.mocked(requirementsModule.requirementsApi.listAll).mockReturnValue(
      new Promise(() => {})
    );

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(newQueryClient()),
    });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.workspaces).toEqual([]);
  });

  it("[REQ-119] enriches workspaces with requirement_count/open_item_count after load", async () => {
    vi.mocked(requirementsModule.requirementsApi.listAll).mockResolvedValue([
      MOCK_REQ("req-1", "draft"),
      MOCK_REQ("req-2", "approved"),
      MOCK_REQ("req-3", "draft"),
    ] as any);

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(newQueryClient()),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.workspaces).toHaveLength(1);
    expect(result.current.workspaces[0].requirement_count).toBe(3);
    expect(result.current.workspaces[0].open_item_count).toBe(2);
    expect(result.current.error).toBeNull();
  });

  it("[REQ-119] degrades to zero metrics on a per-workspace fetch failure without a global error", async () => {
    vi.mocked(requirementsModule.requirementsApi.listAll).mockRejectedValue(
      new Error("workspace unreachable")
    );

    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(newQueryClient()),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.workspaces[0].requirement_count).toBe(0);
    expect(result.current.workspaces[0].open_item_count).toBe(0);
    expect(result.current.error).toBeNull();
  });

  it("[REQ-119] re-fetches counts when requirementKeys.list cache is invalidated (mutation sync)", async () => {
    const listAllMock = vi.mocked(requirementsModule.requirementsApi.listAll);
    listAllMock.mockResolvedValueOnce([MOCK_REQ("req-1", "draft")] as any);

    const queryClient = newQueryClient();
    const { result } = renderHook(() => useDashboardData(), {
      wrapper: createWrapper(queryClient),
    });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.workspaces[0].requirement_count).toBe(1);

    // Simulate what useCreateRequirement/useUpdateRequirement/
    // useDeleteRequirement do on success: invalidate the shared list key.
    listAllMock.mockResolvedValueOnce([
      MOCK_REQ("req-1", "draft"),
      MOCK_REQ("req-2", "approved"),
    ] as any);
    await queryClient.invalidateQueries({
      queryKey: requirementKeys.list(MOCK_WORKSPACE.id),
    });

    await waitFor(() =>
      expect(result.current.workspaces[0].requirement_count).toBe(2)
    );
  });
});
