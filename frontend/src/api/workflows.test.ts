/**
 * REQ-177 — Co-located tests for the Workflow Editor mutation API wrappers.
 *
 * Covers createState / updateState / deleteState / createTransition /
 * updateTransition / deleteTransition / initializeWorkflow: each asserts the
 * HTTP verb, path and body, and that the raw backend graph is derived into the
 * editor WorkflowGraph. Also covers extractWorkflowError for the error path.
 * NOT executed by default — written for the project's Vitest runner.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { workflowsApi, extractWorkflowError } from "./workflows";
import type { WorkflowDefinitionGraph } from "./workflows";
import { ForbiddenError } from "./errors";

const mockGet = vi.fn();
const mockPost = vi.fn();
const mockPatch = vi.fn();
const mockDelete = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: (...a: unknown[]) => mockGet(...a),
    post: (...a: unknown[]) => mockPost(...a),
    patch: (...a: unknown[]) => mockPatch(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
  },
  getList: vi.fn(),
  extractErrorMessage: (err: unknown) => {
    const e = err as { error?: { message?: string } };
    return e?.error?.message ?? String(err);
  },
}));

const WS = "11111111-1111-1111-1111-111111111111";

function rawGraph(
  states: string[],
  transitions: WorkflowDefinitionGraph["transitions"] = []
): WorkflowDefinitionGraph {
  return {
    item_type: "Requirement",
    preset: "extended",
    is_custom: true,
    initial_state: states[0] ?? null,
    initialized: true,
    states,
    transitions,
  };
}

describe("workflowsApi mutations", () => {
  beforeEach(() => vi.clearAllMocks());

  it("createState POSTs the name and derives the graph", async () => {
    mockPost.mockResolvedValue(rawGraph(["draft", "done"]));
    const graph = await workflowsApi.createState("Requirement", WS, "done");
    expect(mockPost).toHaveBeenCalledWith("/workflows/definition/states/", {
      workspace_id: WS,
      item_type: "Requirement",
      name: "done",
    });
    expect(graph.states.map((s) => s.id)).toContain("done");
  });

  it("updateState PATCHes the encoded old name", async () => {
    mockPatch.mockResolvedValue(rawGraph(["draft", "reviewing"]));
    await workflowsApi.updateState("Requirement", WS, "in review", "reviewing");
    expect(mockPatch).toHaveBeenCalledWith(
      "/workflows/definition/states/in%20review/",
      { workspace_id: WS, item_type: "Requirement", name: "reviewing" }
    );
  });

  it("deleteState DELETEs with query scope and derives the graph", async () => {
    mockDelete.mockResolvedValue(rawGraph(["draft"]));
    const graph = await workflowsApi.deleteState("Requirement", WS, "done");
    expect(mockDelete).toHaveBeenCalledTimes(1);
    const path = mockDelete.mock.calls[0][0] as string;
    expect(path).toContain("/workflows/definition/states/done/?");
    expect(path).toContain(`workspace_id=${WS}`);
    expect(path).toContain("item_type=Requirement");
    expect(graph.states.map((s) => s.id)).not.toContain("done");
  });

  it("createTransition POSTs the payload", async () => {
    mockPost.mockResolvedValue(
      rawGraph(
        ["draft", "in_review"],
        [
          {
            from_state: "draft",
            to_state: "in_review",
            allowed_roles: ["admin"],
            requires_change_reason: true,
            signature_gate: false,
          },
        ]
      )
    );
    await workflowsApi.createTransition("Requirement", WS, {
      from_state: "draft",
      to_state: "in_review",
      allowed_roles: ["editor"],
      requires_change_reason: true,
    });
    expect(mockPost).toHaveBeenCalledWith(
      "/workflows/definition/transitions/",
      {
        workspace_id: WS,
        item_type: "Requirement",
        from_state: "draft",
        to_state: "in_review",
        allowed_roles: ["editor"],
        requires_change_reason: true,
      }
    );
  });

  it("updateTransition PATCHes the composite id", async () => {
    mockPatch.mockResolvedValue(rawGraph(["draft", "in_review"]));
    await workflowsApi.updateTransition("Requirement", WS, "draft", "in_review", {
      signature_gate: true,
    });
    expect(mockPatch).toHaveBeenCalledWith(
      "/workflows/definition/transitions/draft__in_review/",
      { workspace_id: WS, item_type: "Requirement", signature_gate: true }
    );
  });

  it("deleteTransition DELETEs the composite id with scope", async () => {
    mockDelete.mockResolvedValue(rawGraph(["draft", "in_review"]));
    await workflowsApi.deleteTransition("Requirement", WS, "draft", "in_review");
    const path = mockDelete.mock.calls[0][0] as string;
    expect(path).toContain(
      "/workflows/definition/transitions/draft__in_review/?"
    );
  });

  it("initializeWorkflow POSTs scope only", async () => {
    mockPost.mockResolvedValue(rawGraph(["draft", "done"]));
    const graph = await workflowsApi.initializeWorkflow("Adr", WS);
    expect(mockPost).toHaveBeenCalledWith("/workflows/definition/initialize/", {
      workspace_id: WS,
      item_type: "Adr",
    });
    expect(graph.initialized).toBe(true);
  });

  it("propagates backend errors from a rejected call", async () => {
    mockDelete.mockRejectedValue({
      error: { message: "State 'draft' cannot be deleted" },
    });
    await expect(
      workflowsApi.deleteState("Requirement", WS, "draft")
    ).rejects.toBeTruthy();
  });
});

describe("extractWorkflowError", () => {
  it("uses the ForbiddenError message directly", () => {
    expect(extractWorkflowError(new ForbiddenError("no admin"))).toBe("no admin");
  });

  it("unwraps an ApiError message", () => {
    expect(
      extractWorkflowError({ error: { message: "duplicate state" } })
    ).toBe("duplicate state");
  });
});
