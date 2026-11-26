/**
 * P2.3 — one canonical transition result.
 *
 * The WorkflowEngine exposes two different state-change payloads and they used
 * to share the name `WorkflowTransitionResult`:
 *
 *   POST /{resource}/{id}/transitions/   → {id, previous_state, new_state, version?}
 *   PATCH /workflows/{id}/               → {id, target_state}
 *
 * The item transition is now the canonical type and extends the shared
 * `WorkflowTransitionStateChange` base; the workspace-definition PATCH keeps its
 * own name (`WorkflowDefinitionTransitionResult`). This file pins both the type
 * relationship and the wire shape, so a future "unification" that merges the
 * two semantics fails here.
 */

import { beforeEach, describe, expect, it, vi, expectTypeOf } from "vitest";

const mockPost = vi.fn();
const mockPatch = vi.fn();

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: (...args: unknown[]) => mockPost(...args),
    patch: (...args: unknown[]) => mockPatch(...args),
    delete: vi.fn(),
  },
  getList: vi.fn(),
  getAllPages: vi.fn(),
}));

import { workflowsApi } from "./workflows";
import type { WorkflowDefinitionTransitionResult } from "./workflows";
import { workflowTransitionsApi } from "./workflow-transitions";
import type { WorkflowTransitionResult } from "./workflow-transitions";
import type { DocumentTransitionResult } from "./documents";
import type {
  WorkItemTransitionResult,
  WorkflowTransitionStateChange,
} from "../types";

describe("canonical transition result types (P2.3)", () => {
  it("pins the shared base contract", () => {
    expectTypeOf<WorkflowTransitionStateChange>().toEqualTypeOf<{
      id: string;
      previous_state: string;
      new_state: string;
    }>();
  });

  it("has every specialised result extend the base", () => {
    expectTypeOf<WorkflowTransitionResult>().toExtend<WorkflowTransitionStateChange>();
    expectTypeOf<DocumentTransitionResult>().toExtend<WorkflowTransitionStateChange>();
    expectTypeOf<WorkItemTransitionResult>().toExtend<WorkflowTransitionStateChange>();

    // The entity revision is optional on the generic result and required on the
    // document/work-item routes, as before.
    expectTypeOf<WorkflowTransitionResult["version"]>().toEqualTypeOf<
      number | undefined
    >();
    expectTypeOf<DocumentTransitionResult["version"]>().toEqualTypeOf<number>();
    expectTypeOf<WorkItemTransitionResult["version"]>().toEqualTypeOf<number>();
  });

  it("keeps the definition PATCH out of the item-transition contract", () => {
    // `{id, target_state}` carries no state change — it must never be
    // assignable to the canonical result.
    expectTypeOf<WorkflowDefinitionTransitionResult>().not.toExtend<WorkflowTransitionStateChange>();
  });

  it("keeps the two endpoints' wire shapes apart at runtime", async () => {
    mockPatch.mockResolvedValue({ id: "wf-1", target_state: "Freigegeben" });
    const definition = await workflowsApi.transition(
      "wf-1",
      "Freigegeben",
      "released"
    );
    expect(mockPatch).toHaveBeenCalledWith("/workflows/wf-1/", {
      target_state: "Freigegeben",
      change_reason: "released",
    });
    expect(definition).toEqual({ id: "wf-1", target_state: "Freigegeben" });

    mockPost.mockResolvedValue({
      id: "req-1",
      previous_state: "draft",
      new_state: "in_review",
    });
    const item = await workflowTransitionsApi.transition(
      "requirement",
      "req-1",
      "in_review",
      "review me"
    );
    expect(mockPost).toHaveBeenCalledWith(
      "/requirements/req-1/transitions/",
      {
        target_state: "in_review",
        change_reason: "review me",
        credential: "",
      }
    );
    expect(item.previous_state).toBe("draft");
    expect(item.new_state).toBe("in_review");
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });
});
