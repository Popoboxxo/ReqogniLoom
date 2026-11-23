/**
 * P5 Task 5.2 — first-load gate for the allocation-graph card fields.
 *
 * The graph is a direct-linkable route, so it can mount while activeWorkspace
 * is still the placeholder workspace (isLoadingWorkspace is already
 * false during auth restore — FR-01). The preference-backed load must not fire
 * against the fake id, and must start normally once a real workspace arrives.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useWorkspace } from "../../context/WorkspaceContext";
import { PLACEHOLDER_WORKSPACE_ID } from "../../utils/workspaceId";
import { cardFieldsApi, type CardFieldConfigMap } from "./cardFields";
import { useCardFields } from "./useCardFields";

const PLACEHOLDER_ID = PLACEHOLDER_WORKSPACE_ID;
const REAL_ID = "ws-real";
const mockUseWorkspace = vi.fn();

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => mockUseWorkspace(),
}));

vi.mock("./cardFields", () => ({
  cardFieldsApi: { load: vi.fn() },
  defaultCardFieldConfigMap: () => ({}),
}));

describe("useCardFields — workspace identity gate", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(cardFieldsApi.load).mockResolvedValue({} as CardFieldConfigMap);
  });

  it("does not load against the placeholder", async () => {
    mockUseWorkspace.mockReturnValue({ activeWorkspace: { id: PLACEHOLDER_WORKSPACE_ID } });

    renderHook(() => useCardFields(PLACEHOLDER_ID));

    await act(async () => {});
    expect(cardFieldsApi.load).not.toHaveBeenCalled();
  });

  it("starts the load with the real id once the workspace resolves", async () => {
    // Stable object references: the hook's effect keys on activeWorkspace, so
    // a fresh object per render would loop instead of resolving.
    const realWorkspace = { id: REAL_ID };
    mockUseWorkspace.mockImplementation(() => ({
      activeWorkspace: { id: PLACEHOLDER_WORKSPACE_ID },
    }));

    const { rerender } = renderHook(
      ({ id }: { id: string }) => useCardFields(id),
      { initialProps: { id: PLACEHOLDER_ID } }
    );

    await act(async () => {});
    expect(cardFieldsApi.load).not.toHaveBeenCalled();

    mockUseWorkspace.mockImplementation(() => ({
      activeWorkspace: realWorkspace,
    }));
    rerender({ id: REAL_ID });

    await waitFor(() =>
      expect(cardFieldsApi.load).toHaveBeenCalledWith(REAL_ID)
    );
    expect(cardFieldsApi.load).not.toHaveBeenCalledWith(PLACEHOLDER_ID);
  });
});
