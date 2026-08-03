/**
 * ARCH-L1-001 ReactFrontend — useDerivationChain unit test (Task 3.2b).
 *
 * req_id: REQ-L2-TE-019 (Traceability graph queries)
 *
 * Covers the Task 3.2b addition: batch-resolving chain artifact ids via
 * `GET /traceability/resolve/` and exposing `isOpenable`/`resolveEntry`.
 * Does NOT re-test station bucketing (ch. 5.1/5.2) — that predates this
 * task and is unchanged by it.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";

vi.mock("../api/client", () => ({
  extractErrorMessage: vi.fn().mockReturnValue("Error"),
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("../api/tracelinks", () => ({
  tracelinksApi: {
    impact: vi.fn(),
  },
}));

vi.mock("../api/traceability", () => ({
  traceabilityApi: {
    resolve: vi.fn(),
  },
}));

// Must import AFTER vi.mock
import { useDerivationChain } from "../components/shared/TraceSpine/useDerivationChain";
import { tracelinksApi } from "../api/tracelinks";
import { traceabilityApi } from "../api/traceability";

const CURRENT_ID = "11111111-1111-1111-1111-111111111111";
const DERIVED_ID = "22222222-2222-2222-2222-222222222222";

function mockImpact(): void {
  vi.mocked(tracelinksApi.impact).mockImplementation((_id, { direction } = {}) => {
    if (direction === "outgoing") {
      return Promise.resolve([
        {
          artifact_id: DERIVED_ID,
          artifact_type: "ArchitectureElement",
          title: "Derived Element",
          uid: "ARCH-1",
          link_type: "derived_from",
          depth: 1,
          path: [CURRENT_ID, DERIVED_ID],
        },
      ]);
    }
    return Promise.resolve([]);
  });
}

describe("useDerivationChain — route resolution (Task 3.2b)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockImpact();
  });

  it("resolves chain artifacts via the batch endpoint and reports them openable", async () => {
    vi.mocked(traceabilityApi.resolve).mockResolvedValue([
      { artifact_id: CURRENT_ID, resolved: true, entity_type: "Requirement", entity_id: "req-1" },
      {
        artifact_id: DERIVED_ID,
        resolved: true,
        entity_type: "ArchitectureElement",
        entity_id: "arch-1",
      },
    ]);

    const { result } = renderHook(() =>
      useDerivationChain(CURRENT_ID, "Requirement", null),
    );

    await waitFor(() => expect(result.current.isResolving).toBe(false));

    // The batch call must be one round trip for the whole chain, not N+1.
    expect(traceabilityApi.resolve).toHaveBeenCalledTimes(1);
    const calledIds = vi.mocked(traceabilityApi.resolve).mock.calls[0][0];
    expect(calledIds).toEqual(expect.arrayContaining([CURRENT_ID, DERIVED_ID]));

    const derivedArtifact = { id: DERIVED_ID, title: "Derived Element", uid: "ARCH-1", artifactType: "ArchitectureElement", linkType: "derived_from" };
    expect(result.current.isOpenable(derivedArtifact)).toBe(true);
    expect(result.current.resolveEntry(derivedArtifact)).toEqual({
      entityType: "ArchitectureElement",
      entityId: "arch-1",
    });
  });

  it("falls back to not-openable when the backend reports resolved: false", async () => {
    vi.mocked(traceabilityApi.resolve).mockResolvedValue([
      { artifact_id: CURRENT_ID, resolved: true, entity_type: "Requirement", entity_id: "req-1" },
      { artifact_id: DERIVED_ID, resolved: false, entity_type: null, entity_id: null },
    ]);

    const { result } = renderHook(() =>
      useDerivationChain(CURRENT_ID, "Requirement", null),
    );

    await waitFor(() => expect(result.current.isResolving).toBe(false));

    const derivedArtifact = { id: DERIVED_ID, title: "Derived Element", uid: "ARCH-1", artifactType: "ArchitectureElement", linkType: "derived_from" };
    expect(result.current.isOpenable(derivedArtifact)).toBe(false);
    expect(result.current.resolveEntry(derivedArtifact)).toBeNull();
  });

  it("falls back to not-openable (not a crash) when the resolve call fails", async () => {
    vi.mocked(traceabilityApi.resolve).mockRejectedValue(new Error("network down"));

    const { result } = renderHook(() =>
      useDerivationChain(CURRENT_ID, "Requirement", null),
    );

    await waitFor(() => expect(result.current.isResolving).toBe(false));

    const derivedArtifact = { id: DERIVED_ID, title: "Derived Element", uid: "ARCH-1", artifactType: "ArchitectureElement", linkType: "derived_from" };
    expect(result.current.isOpenable(derivedArtifact)).toBe(false);
    expect(result.current.resolveEntry(derivedArtifact)).toBeNull();
    // The chain itself must still have rendered — a resolve failure is
    // independent of the impact-query error state.
    expect(result.current.error).toBeNull();
    expect(result.current.stations.length).toBeGreaterThan(0);
  });

  it("skips the resolve call entirely when there is no artifact", async () => {
    const { result } = renderHook(() => useDerivationChain(null, "Requirement", null));

    await waitFor(() => expect(result.current.isResolving).toBe(false));
    expect(traceabilityApi.resolve).not.toHaveBeenCalled();
    expect(result.current.stations).toEqual([]);
  });
});
