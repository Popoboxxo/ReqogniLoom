import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { WorkspacePreset } from "../../types";
import type { WorkflowGraph } from "../../api/workflows";
import { workflowsApi } from "../../api/workflows";
import { workflowDefaultsApi } from "../../api/workflow-defaults";
import { useWorkflowData, workflowKeys } from "./useWorkflowData";

const workspaceState = vi.hoisted(() => ({
  activeWorkspace: {
    id: "11111111-1111-1111-1111-111111111111",
    preset: "minimal" as WorkspacePreset,
  },
  isLoadingWorkspace: false,
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => workspaceState,
}));

vi.mock("../../api/workflows", () => ({
  workflowsApi: { getGraph: vi.fn() },
}));

vi.mock("../../api/workflow-defaults", () => ({
  workflowDefaultsApi: { getGraph: vi.fn() },
}));

function graph(preset: string): WorkflowGraph {
  return {
    entityType: "Requirement",
    preset,
    isCustom: false,
    initialized: true,
    states: [],
    transitions: [],
  };
}

function createWrapper(client: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }): JSX.Element {
    return (
      <QueryClientProvider client={client}>{children}</QueryClientProvider>
    );
  };
}

describe("useWorkflowData scope caching", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    workspaceState.activeWorkspace.preset = "minimal";
    workspaceState.isLoadingWorkspace = false;
  });

  it("uses a fresh workspace query key after the active preset changes", async () => {
    vi.mocked(workflowsApi.getGraph)
      .mockResolvedValueOnce(graph("minimal"))
      .mockResolvedValueOnce(graph("extended"))
      .mockResolvedValueOnce(graph("minimal"));
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false, staleTime: 30_000 } },
    });
    const { result, rerender } = renderHook(
      () =>
        useWorkflowData("Requirement", {
          kind: "workspace",
          workspaceId: workspaceState.activeWorkspace.id,
          preset: workspaceState.activeWorkspace.preset,
        }),
      { wrapper: createWrapper(client) }
    );

    await waitFor(() => expect(result.current.graph?.preset).toBe("minimal"));
    expect(workflowsApi.getGraph).toHaveBeenCalledTimes(1);

    act(() => {
      workspaceState.activeWorkspace.preset = "extended";
    });
    rerender();

    await waitFor(() => expect(result.current.graph?.preset).toBe("extended"));
    expect(workflowsApi.getGraph).toHaveBeenCalledTimes(2);
    expect(
      client.getQueryData(
        workflowKeys.graph(
          {
            kind: "workspace",
            workspaceId: workspaceState.activeWorkspace.id,
            preset: "minimal",
          },
          "Requirement"
        )
      )
    ).toEqual(graph("minimal"));
    expect(
      client.getQueryData(
        workflowKeys.graph(
          {
            kind: "workspace",
            workspaceId: workspaceState.activeWorkspace.id,
            preset: "extended",
          },
          "Requirement"
        )
      )
    ).toEqual(graph("extended"));

    act(() => {
      workspaceState.activeWorkspace.preset = "minimal";
    });
    rerender();

    await waitFor(() => expect(result.current.graph?.preset).toBe("minimal"));
    expect(workflowsApi.getGraph).toHaveBeenCalledTimes(3);
  });

  it("reads Document globals only from document_default", async () => {
    vi.mocked(workflowDefaultsApi.getGraph).mockResolvedValue(graph("document_default"));
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { result } = renderHook(
      () =>
        useWorkflowData("Document", {
          kind: "global",
          preset: "document_default",
        }),
      { wrapper: createWrapper(client) }
    );

    await waitFor(() => expect(result.current.graph?.preset).toBe("document_default"));
    expect(workflowDefaultsApi.getGraph).toHaveBeenCalledWith(
      "Document",
      "document_default"
    );
    expect(workflowsApi.getGraph).not.toHaveBeenCalled();
  });

  it("reads WorkItem globals from the prefixed tier key", async () => {
    vi.mocked(workflowDefaultsApi.getGraph).mockResolvedValue(
      graph("work_item_extended")
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { result } = renderHook(
      () =>
        useWorkflowData("WorkItem", {
          kind: "global",
          preset: "work_item_extended",
        }),
      { wrapper: createWrapper(client) }
    );

    await waitFor(() =>
      expect(result.current.graph?.preset).toBe("work_item_extended")
    );
    expect(workflowDefaultsApi.getGraph).toHaveBeenCalledWith(
      "WorkItem",
      "work_item_extended"
    );
  });
});
