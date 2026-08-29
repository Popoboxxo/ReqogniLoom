/**
 * Unit tests for the shared trace-endpoint helpers (#413, #415, #416).
 *
 * The central invariant under test: a TraceLink endpoint is an **Artifact**
 * id, so resolution must never assume the caller's entity id appears in the
 * link — and must never fall back to "the source" when nothing matches, which
 * is how the requirement editor ended up rendering the artifact itself.
 */

import { describe, expect, it } from "vitest";
import {
  buildArtifactTitleIndex,
  collectVerifiedArtifactIds,
  endpointLabel,
  endpointOf,
  formatShortId,
  hierarchyRelation,
  inferSelfArtifactId,
  neighborOf,
} from "./traceEndpoints";
import type { TraceEndpoint } from "./traceEndpoints";
import type { TraceLink } from "../types";

const ART_L1 = "11111111-1111-1111-1111-111111111111";
const ART_L2 = "22222222-2222-2222-2222-222222222222";
const ART_TC = "33333333-3333-3333-3333-333333333333";
const ENTITY_L1 = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

function link(overrides: Partial<TraceLink> = {}): TraceLink {
  return {
    id: "link-1",
    source_id: ART_L1,
    target_id: ART_L2,
    link_type: "decomposes",
    version: 1,
    created_at: "2026-02-01T00:00:00Z",
    source_title: "L1 requirement",
    source_type: "Requirement",
    target_title: "L2 requirement",
    target_type: "Requirement",
    ...overrides,
  };
}

describe("endpointOf", () => {
  it("reads title and type of the requested side", () => {
    expect(endpointOf(link(), "source")).toEqual({
      id: ART_L1,
      title: "L1 requirement",
      artifactType: "Requirement",
      isOutdated: false,
    });
    expect(endpointOf(link(), "target").id).toBe(ART_L2);
  });

  it("degrades to empty strings for pre-REQ-002 payloads", () => {
    const bare = link({ source_title: undefined, source_type: undefined });
    expect(endpointOf(bare, "source")).toEqual({
      id: ART_L1,
      title: "",
      artifactType: "",
      isOutdated: false,
    });
  });

  /**
   * UI-P3: a soft-deleted endpoint keeps its TraceLink (audit trail), so the
   * link keeps arriving from the API. Without the flag every surface rendered
   * it as a live neighbour — that is the bug this field exists to close.
   */
  it("propagates the per-side outdated flag", () => {
    const partiallyDead = link({ source_is_outdated: false, target_is_outdated: true });
    expect(endpointOf(partiallyDead, "source").isOutdated).toBe(false);
    expect(endpointOf(partiallyDead, "target").isOutdated).toBe(true);
  });

  it("treats a pre-UI-P3 payload without the flag as live", () => {
    const bare = link({ source_is_outdated: undefined, target_is_outdated: undefined });
    expect(endpointOf(bare, "source").isOutdated).toBe(false);
    expect(endpointOf(bare, "target").isOutdated).toBe(false);
  });
});

describe("neighborOf outdated propagation (UI-P3)", () => {
  it("reports the far endpoint as dead, not the near one", () => {
    // The requirement being viewed is ART_L1 and is alive; its neighbour
    // ART_L2 was soft-deleted.
    const dead = link({ source_is_outdated: false, target_is_outdated: true });
    const neighbor = neighborOf(dead, new Set([ART_L1]));
    expect(neighbor?.endpoint.id).toBe(ART_L2);
    expect(neighbor?.endpoint.isOutdated).toBe(true);
  });

  it("keeps a live neighbour live when the near side is the dead one", () => {
    const dead = link({ source_is_outdated: true, target_is_outdated: false });
    const neighbor = neighborOf(dead, new Set([ART_L1]));
    expect(neighbor?.endpoint.id).toBe(ART_L2);
    expect(neighbor?.endpoint.isOutdated).toBe(false);
  });
});

describe("neighborOf", () => {
  it("returns the far endpoint when the node is the source", () => {
    const neighbor = neighborOf(link(), new Set([ART_L1]));
    expect(neighbor?.direction).toBe("outgoing");
    expect(neighbor?.endpoint.id).toBe(ART_L2);
  });

  it("returns the far endpoint when the node is the target", () => {
    const neighbor = neighborOf(link(), new Set([ART_L2]));
    expect(neighbor?.direction).toBe("incoming");
    expect(neighbor?.endpoint.id).toBe(ART_L1);
  });

  it("matches on any known id of the node (entity id + artifact id)", () => {
    // #416: the component holds the Requirement id; only the Artifact id is
    // in the link. Both are passed, so resolution still succeeds.
    const neighbor = neighborOf(link(), new Set([ENTITY_L1, ART_L1]));
    expect(neighbor?.endpoint.id).toBe(ART_L2);
  });

  it("returns null instead of guessing when no id matches", () => {
    // The old inline logic returned the source here — i.e. the artifact the
    // caller was already looking at (#416).
    expect(neighborOf(link(), new Set([ENTITY_L1]))).toBeNull();
  });

  it("returns null for a self-link", () => {
    expect(neighborOf(link({ target_id: ART_L1 }), new Set([ART_L1]))).toBeNull();
  });
});

describe("hierarchyRelation", () => {
  it("treats the target of `decomposes` as a child", () => {
    const result = hierarchyRelation(link({ link_type: "decomposes" }), new Set([ART_L1]));
    expect(result?.relation).toBe("child");
    expect(result?.neighbor.endpoint.id).toBe(ART_L2);
  });

  it("treats the source of `decomposes` as a parent", () => {
    const result = hierarchyRelation(link({ link_type: "decomposes" }), new Set([ART_L2]));
    expect(result?.relation).toBe("parent");
  });

  it("treats the target of `derives-from` as a parent", () => {
    const result = hierarchyRelation(link({ link_type: "derives-from" }), new Set([ART_L1]));
    expect(result?.relation).toBe("parent");
  });

  it("treats the target of `parent-child` as a child", () => {
    const result = hierarchyRelation(link({ link_type: "parent-child" }), new Set([ART_L1]));
    expect(result?.relation).toBe("child");
  });

  it("ignores non-hierarchy link types", () => {
    expect(hierarchyRelation(link({ link_type: "verifies" }), new Set([ART_L1]))).toBeNull();
  });

  it("no longer honours the non-existent `derived-by` type", () => {
    // `derived-by` was in the old filter list but not in the backend enum;
    // relying on it silently hid every real hierarchy link.
    expect(hierarchyRelation(link({ link_type: "derived-by" }), new Set([ART_L1]))).toBeNull();
  });
});

describe("collectVerifiedArtifactIds", () => {
  it("marks the verified artifact of a `verifies` link", () => {
    const verified = collectVerifiedArtifactIds([
      link({ link_type: "verifies", source_id: ART_TC, source_type: "TestCase", target_id: ART_L1 }),
    ]);
    expect([...verified]).toEqual([ART_L1]);
  });

  it("tolerates links authored in the opposite direction", () => {
    const verified = collectVerifiedArtifactIds([
      link({ link_type: "verifies", source_id: ART_L1, source_type: "Requirement", target_id: ART_TC, target_type: "TestCase" }),
    ]);
    expect([...verified]).toEqual([ART_L1]);
  });

  it("ignores every other link type", () => {
    expect(collectVerifiedArtifactIds([link({ link_type: "allocated-to" })]).size).toBe(0);
  });
});

describe("inferSelfArtifactId", () => {
  it("finds the endpoint shared by every link", () => {
    const links = [
      link({ id: "l1", source_id: ART_L1, target_id: ART_L2 }),
      link({ id: "l2", source_id: ART_TC, target_id: ART_L1 }),
    ];
    expect(inferSelfArtifactId(links)).toBe(ART_L1);
  });

  it("refuses to guess from a single link", () => {
    expect(inferSelfArtifactId([link()])).toBeNull();
  });

  it("returns null when no endpoint is common to all links", () => {
    const links = [
      link({ id: "l1", source_id: ART_L1, target_id: ART_L2 }),
      link({ id: "l2", source_id: ART_TC, target_id: "44444444-4444-4444-4444-444444444444" }),
    ];
    expect(inferSelfArtifactId(links)).toBeNull();
  });
});

describe("title helpers", () => {
  it("indexes titles by artifact id", () => {
    expect(buildArtifactTitleIndex([link()])).toEqual({
      [ART_L1]: "L1 requirement",
      [ART_L2]: "L2 requirement",
    });
  });

  it("falls back from title to local title to shortened id", () => {
    const endpoint: TraceEndpoint = {
      id: ART_L1,
      title: "",
      artifactType: "Requirement",
      isOutdated: false,
    };
    expect(endpointLabel({ ...endpoint, title: "Backend title" })).toBe("Backend title");
    expect(endpointLabel(endpoint, "Local title")).toBe("Local title");
    expect(endpointLabel(endpoint)).toBe(formatShortId(ART_L1));
    expect(formatShortId(ART_L1)).toBe("11111111…");
  });
});
