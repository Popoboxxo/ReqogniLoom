import { beforeEach, describe, expect, it, vi } from "vitest";
import { workflowDefaultsApi } from "./workflow-defaults";
import type { GlobalWorkflowDefinitionGraph } from "./workflow-defaults";
import type { WorkflowPresetKey } from "./workflows";

const mockGet = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
  },
}));

function rawGraph(
  itemType: string,
  preset: WorkflowPresetKey
): GlobalWorkflowDefinitionGraph {
  return {
    scope: "global",
    tenant_id: "11111111-1111-1111-1111-111111111111",
    item_type: itemType,
    preset,
    initialized: true,
    initial_state: "draft",
    states: ["draft"],
    transitions: [],
  };
}

describe("workflowDefaultsApi canonical preset routes", () => {
  beforeEach(() => vi.clearAllMocks());

  it.each([
    ["Document", "document_default"],
    ["Requirement", "extended"],
    ["WorkItem", "work_item_standard"],
  ] as const)("reads %s from %s", async (entityType, preset) => {
    mockGet.mockResolvedValue(rawGraph(entityType, preset));

    const graph = await workflowDefaultsApi.getGraph(entityType, preset);

    expect(mockGet).toHaveBeenCalledWith(
      `/workflow-defaults/${entityType}/${preset}/`
    );
    expect(graph.entityType).toBe(entityType);
    expect(graph.preset).toBe(preset);
  });
});
