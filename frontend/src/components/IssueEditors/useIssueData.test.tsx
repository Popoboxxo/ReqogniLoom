/**
 * Unit tests for useIssueData (REQ-049 TanStack Query migration).
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
import { useIssueData } from "./useIssueData";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/issues");
vi.mock("../../context/WorkspaceContext");

import * as issuesModule from "../../api/issues";
import * as workspaceContext from "../../context/WorkspaceContext";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = { id: "ws-issue-001", name: "Sprint Planning WS", preset: "standard" };

const MOCK_ISSUE = {
  id: "issue-001",
  workspace_id: "ws-issue-001",
  title: "Authentication token not refreshed after session timeout",
  description: "Users are redirected to login on every API call after 30 min idle.",
  priority: "high",
  status: "In Progress",
  assignee: "eng-team@example.com",
  version: 3,
  created_at: "2026-03-05T11:00:00Z",
  updated_at: "2026-03-08T16:45:00Z",
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

describe("useIssueData (REQ-049)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
  });

  it("[REQ-049] returns isLoading=true initially while list query is in-flight", () => {
    vi.mocked(issuesModule.issuesApi.list).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useIssueData(), { wrapper: createWrapper() });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.items).toEqual([]);
  });

  it("[REQ-049] populates items after list query resolves", async () => {
    vi.mocked(issuesModule.issuesApi.list).mockResolvedValue({
      results: [MOCK_ISSUE],
      count: 1,
    } as any);

    const { result } = renderHook(() => useIssueData(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.items).toHaveLength(1);
    expect(result.current.items[0].id).toBe("issue-001");
    expect(result.current.items[0].title).toBe(
      "Authentication token not refreshed after session timeout"
    );
  });

  it("[REQ-049] populates item after detail query resolves when selectedId is provided", async () => {
    vi.mocked(issuesModule.issuesApi.list).mockResolvedValue({
      results: [MOCK_ISSUE],
      count: 1,
    } as any);
    vi.mocked(issuesModule.issuesApi.get).mockResolvedValue(MOCK_ISSUE as any);

    const { result } = renderHook(() => useIssueData("issue-001"), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.item).not.toBeNull());
    expect(result.current.item?.id).toBe("issue-001");
    expect(result.current.item?.priority).toBe("high");
  });

  it("[REQ-049] surfaces list error via error property", async () => {
    vi.mocked(issuesModule.issuesApi.list).mockRejectedValue(
      { error: { message: "server error: database unavailable" } }
    );

    const { result } = renderHook(() => useIssueData(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error?.message).toBe("server error: database unavailable");
  });
});
