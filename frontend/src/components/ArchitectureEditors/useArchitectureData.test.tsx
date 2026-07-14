/**
 * Unit tests for useArchitectureData (REQ-049 TanStack Query migration).
 *
 * req_id: REQ-049, REQ-053
 *
 * Verifies:
 *   - isLoading=true initially while the list query is in-flight
 *   - elements populated after list query resolves
 *   - element + linkedTraceLinks populated after detail query resolves
 *   - error property set (only from detail query, not list)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";
import { useArchitectureData } from "./useArchitectureData";

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock("../../api/architecture");
vi.mock("../../api/tracelinks");
vi.mock("../../api/client", () => ({
  extractErrorMessage: vi.fn((err: unknown) => {
    const e = err as { error?: { message?: string } };
    return e?.error?.message ?? String(err);
  }),
  setAuthToken: vi.fn(),
  setUnauthorizedHandler: vi.fn(),
}));
vi.mock("../../context/WorkspaceContext");

import * as archModule from "../../api/architecture";
import * as tracelinksModule from "../../api/tracelinks";
import * as workspaceContext from "../../context/WorkspaceContext";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MOCK_WORKSPACE = { id: "ws-arch-001", name: "System Architecture WS", preset: "extended" };

const MOCK_ELEMENT = {
  id: "arch-001",
  workspace_id: "ws-arch-001",
  name: "Navigation Subsystem",
  description: "Handles GPS position, velocity estimation and waypoint sequencing.",
  element_type: "subsystem",
  parent_id: null,
  version: 2,
  created_at: "2026-02-01T09:00:00Z",
  updated_at: "2026-02-15T11:30:00Z",
};

const MOCK_TRACE_LINK = {
  id: "tl-001",
  workspace_id: "ws-arch-001",
  source_id: "req-nav-001",
  target_id: "arch-001",
  link_type: "implements",
  created_at: "2026-02-10T10:00:00Z",
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

describe("useArchitectureData (REQ-049)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(workspaceContext.useWorkspace).mockReturnValue({
      activeWorkspace: MOCK_WORKSPACE,
    } as any);
  });

  it("[REQ-049] returns isLoading=true initially while list query is in-flight", () => {
    vi.mocked(archModule.architectureApi.listAll).mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useArchitectureData(), { wrapper: createWrapper() });

    expect(result.current.isLoading).toBe(true);
    expect(result.current.elements).toEqual([]);
  });

  it("[REQ-049] populates elements after list query resolves", async () => {
    vi.mocked(archModule.architectureApi.listAll).mockResolvedValue([MOCK_ELEMENT] as any);

    const { result } = renderHook(() => useArchitectureData(), { wrapper: createWrapper() });

    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.elements).toHaveLength(1);
    expect(result.current.elements[0].id).toBe("arch-001");
    expect(result.current.elements[0].name).toBe("Navigation Subsystem");
  });

  it("[REQ-049] populates element and linkedTraceLinks when selectedId is provided", async () => {
    vi.mocked(archModule.architectureApi.listAll).mockResolvedValue([MOCK_ELEMENT] as any);
    vi.mocked(archModule.architectureApi.get).mockResolvedValue(MOCK_ELEMENT as any);
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [MOCK_TRACE_LINK],
    } as any);

    const { result } = renderHook(() => useArchitectureData("arch-001"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.element).not.toBeNull());
    expect(result.current.element?.id).toBe("arch-001");
    expect(result.current.linkedTraceLinks).toHaveLength(1);
    expect(result.current.linkedTraceLinks[0].link_type).toBe("implements");
  });

  it("[REQ-049] surfaces detail error via error property when detail query fails", async () => {
    vi.mocked(archModule.architectureApi.listAll).mockResolvedValue([MOCK_ELEMENT] as any);
    vi.mocked(archModule.architectureApi.get).mockRejectedValue(
      { error: { message: "architecture element not found" } }
    );
    vi.mocked(tracelinksModule.tracelinksApi.listForArtifact).mockResolvedValue({
      results: [],
    } as any);

    const { result } = renderHook(() => useArchitectureData("arch-missing"), {
      wrapper: createWrapper(),
    });

    await waitFor(() => expect(result.current.error).not.toBeNull());
    expect(result.current.error).toBe("architecture element not found");
  });
});
