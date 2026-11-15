/**
 * artifact-summary API wrapper (Issue #1792, S2).
 *
 * Pins the endpoint path, the two query parameters and the wire→camel
 * mapping. The endpoint answers 200 for every degradation, so a rejection here
 * must survive unchanged (no swallow, no retry) — the panel turns it into its
 * only error state.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
  },
}));

import { fetchArtifactSummary } from "./artifact-summary";
import { apiClient } from "./client";
import { ForbiddenError } from "./errors";

const ARTIFACT_ID = "8f14e45f-ceea-467a-9e4b-3a1c1f0d9b77";

const WIRE = {
  artifact_id: ARTIFACT_ID,
  artifact_type: "Requirement",
  summary: "The requirement keeps the export deterministic.",
  degraded: false,
  degraded_reason: null,
  cache_hit: true,
  trace_depth: 2,
  neighbour_count: 7,
  omitted_neighbours: 1,
  generated_at: "2026-11-15T09:30:00Z",
};

describe("fetchArtifactSummary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("calls the S1 endpoint without query parameters by default", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(WIRE);

    await fetchArtifactSummary(ARTIFACT_ID);

    expect(apiClient.get).toHaveBeenCalledTimes(1);
    expect(apiClient.get).toHaveBeenCalledWith(`/artifacts/${ARTIFACT_ID}/summary/`);
  });

  it("sends refresh=true when a regeneration is requested", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(WIRE);

    await fetchArtifactSummary(ARTIFACT_ID, { refresh: true });

    expect(apiClient.get).toHaveBeenCalledWith(
      `/artifacts/${ARTIFACT_ID}/summary/?refresh=true`,
    );
  });

  it("sends the trace depth, including a clamped-looking 0", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(WIRE);

    await fetchArtifactSummary(ARTIFACT_ID, { depth: 2 });
    expect(apiClient.get).toHaveBeenLastCalledWith(
      `/artifacts/${ARTIFACT_ID}/summary/?depth=2`,
    );

    await fetchArtifactSummary(ARTIFACT_ID, { depth: 0 });
    expect(apiClient.get).toHaveBeenLastCalledWith(
      `/artifacts/${ARTIFACT_ID}/summary/?depth=0`,
    );
  });

  it("combines refresh and depth in one query string", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(WIRE);

    await fetchArtifactSummary(ARTIFACT_ID, { refresh: true, depth: 1 });

    expect(apiClient.get).toHaveBeenCalledWith(
      `/artifacts/${ARTIFACT_ID}/summary/?refresh=true&depth=1`,
    );
  });

  it("maps every wire field onto the camelCase contract", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(WIRE);

    await expect(fetchArtifactSummary(ARTIFACT_ID)).resolves.toEqual({
      artifactId: ARTIFACT_ID,
      artifactType: "Requirement",
      summary: "The requirement keeps the export deterministic.",
      degraded: false,
      degradedReason: null,
      cacheHit: true,
      traceDepth: 2,
      neighbourCount: 7,
      omittedNeighbours: 1,
      generatedAt: "2026-11-15T09:30:00Z",
    });
  });

  it.each([
    "budget_exhausted",
    "provider_unavailable",
    "stale",
    "disabled",
  ] as const)("keeps the closed degraded reason %s", async (reason) => {
    vi.mocked(apiClient.get).mockResolvedValue({
      ...WIRE,
      summary: null,
      degraded: true,
      degraded_reason: reason,
    });

    const result = await fetchArtifactSummary(ARTIFACT_ID);

    expect(result.degraded).toBe(true);
    expect(result.degradedReason).toBe(reason);
    expect(result.summary).toBeNull();
  });

  it("maps an unknown degraded reason to null instead of leaking a raw string", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      ...WIRE,
      summary: null,
      degraded: true,
      degraded_reason: "something_newer_than_this_client",
    });

    const result = await fetchArtifactSummary(ARTIFACT_ID);

    expect(result.degraded).toBe(true);
    expect(result.degradedReason).toBeNull();
  });

  it("propagates a rejection unchanged and never retries", async () => {
    const forbidden = new ForbiddenError("no read permission");
    vi.mocked(apiClient.get).mockRejectedValue(forbidden);

    await expect(fetchArtifactSummary(ARTIFACT_ID)).rejects.toBe(forbidden);
    expect(apiClient.get).toHaveBeenCalledTimes(1);
  });
});
