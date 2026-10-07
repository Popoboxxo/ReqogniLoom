/**
 * Guard branches of the gate-required discovery hook (GitHub #1192).
 *
 * `useGateRequiredFields` is deliberately best-effort: a missing workspace, an
 * API mock that predates `getSchema`, or a failed request must all degrade to
 * an empty set — the form must never fail to render because a discovery request
 * did. The happy path is covered end-to-end by `ArtifactForm.test.tsx`; these
 * tests pin the two defensive branches the review flagged (F1 follow-up):
 *
 *   - `getSchema` absent from the mocked `api/attribute-definitions` (:45-48)
 *   - the schema request rejects (:71-73)
 */

import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { api } = vi.hoisted(() => ({
  api: {} as { getSchema?: (...args: unknown[]) => unknown },
}));

vi.mock("../../../api/attribute-definitions", () => ({
  attributeDefinitionsApi: api,
}));

vi.mock("../../../context/WorkspaceContext", () => ({
  useWorkspace: vi.fn(),
}));

import { useWorkspace } from "../../../context/WorkspaceContext";
import { useGateRequiredFields } from "./useGateRequiredFields";

function withWorkspace(activeWorkspace: { id: string } | null): void {
  vi.mocked(useWorkspace).mockReturnValue({ activeWorkspace } as never);
}

describe("useGateRequiredFields (#1192)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    delete api.getSchema;
  });

  it("collects only the is_required attribute names", async () => {
    withWorkspace({ id: "ws-1" });
    api.getSchema = vi.fn().mockResolvedValue([
      {
        entity_type: "Requirement",
        attribute_name: "title",
        is_visible: true,
        is_required: true,
      },
      {
        entity_type: "Requirement",
        attribute_name: "description",
        is_visible: true,
        is_required: false,
      },
      // A row from a pre-#1192 backend carries no `is_required` at all.
      { entity_type: "Requirement", attribute_name: "uid", is_visible: true },
    ]);

    const { result } = renderHook(() => useGateRequiredFields("Requirement"));

    await waitFor(() => expect(result.current.has("title")).toBe(true));
    expect(result.current.has("description")).toBe(false);
    expect(result.current.has("uid")).toBe(false);
    expect(api.getSchema).toHaveBeenCalledWith("ws-1", "Requirement");
  });

  it("degrades to an empty set when getSchema is absent from the mocked api", () => {
    withWorkspace({ id: "ws-1" });
    expect(api.getSchema).toBeUndefined();

    const { result } = renderHook(() => useGateRequiredFields("Requirement"));

    // No throw, and no discovery is attempted.
    expect(api.getSchema).toBeUndefined();
    expect(result.current.size).toBe(0);
  });

  it("degrades to an empty set when the schema request rejects", async () => {
    withWorkspace({ id: "ws-1" });
    api.getSchema = vi.fn().mockRejectedValue(new Error("schema unavailable"));

    const { result } = renderHook(() => useGateRequiredFields("Requirement"));

    await waitFor(() => expect(api.getSchema).toHaveBeenCalled());
    expect(result.current.size).toBe(0);
  });

  it("returns an empty set without an active workspace and never calls the api", () => {
    withWorkspace(null);
    api.getSchema = vi.fn();

    const { result } = renderHook(() => useGateRequiredFields("Requirement"));

    expect(result.current.size).toBe(0);
    expect(api.getSchema).not.toHaveBeenCalled();
  });
});
