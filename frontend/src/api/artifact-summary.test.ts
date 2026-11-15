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
    post: vi.fn(),
  },
}));

import {
  fetchArtifactSummary,
  fetchTypeSummary,
  fetchWorkspaceSummaries,
  refreshTypeSummary,
} from "./artifact-summary";
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

const WORKSPACE_ID = "0b6a1a52-2f0b-4a6e-9a3c-7f1f3d2c8e11";

const STORED_WIRE = {
  workspace_id: WORKSPACE_ID,
  summary_kind: "type_roster",
  artifact_type: "Requirement",
  artifact_id: null,
  text: "Twelve requirements cover export and import.",
  reason: null,
  stale: false,
  item_count: 12,
  status: "ok",
  provider: "anthropic",
  model: "claude",
  token_usage: 900,
  trigger: "periodic",
  generated_at: "2026-11-15T09:30:00Z",
  updated_at: "2026-11-15T09:30:00Z",
};

describe("stored workspace/type summaries (S6 read paths, surfaced in S8)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("lists the workspace stands from the list route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      workspace_id: WORKSPACE_ID,
      summaries: [STORED_WIRE],
      count: 1,
      truncated: false,
      limit: 50,
    });

    const result = await fetchWorkspaceSummaries(WORKSPACE_ID);

    expect(apiClient.get).toHaveBeenCalledWith(`/workspaces/${WORKSPACE_ID}/summaries/`);
    expect(result.count).toBe(1);
    expect(result.truncated).toBe(false);
    expect(result.summaries[0]).toMatchObject({
      workspaceId: WORKSPACE_ID,
      summaryKind: "type_roster",
      artifactType: "Requirement",
      artifactId: null,
      text: "Twelve requirements cover export and import.",
      reason: null,
      stale: false,
      itemCount: 12,
      tokenUsage: 900,
      generatedAt: "2026-11-15T09:30:00Z",
    });
  });

  it("reads one type stand and encodes the type in the path", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      ...STORED_WIRE,
      artifact_type: "Architecture Element",
    });

    await fetchTypeSummary(WORKSPACE_ID, "Architecture Element");

    expect(apiClient.get).toHaveBeenCalledWith(
      `/workspaces/${WORKSPACE_ID}/summaries/Architecture%20Element/`,
    );
  });

  it("keeps a stale stand and its E11 reason", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      ...STORED_WIRE,
      stale: true,
      reason: "stale",
    });

    const result = await fetchTypeSummary(WORKSPACE_ID, "Requirement");

    expect(result.stale).toBe(true);
    expect(result.reason).toBe("stale");
  });

  it("maps an unknown reason to null while keeping the stand", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      ...STORED_WIRE,
      reason: "a_reason_from_the_future",
    });

    const result = await fetchTypeSummary(WORKSPACE_ID, "Requirement");

    expect(result.reason).toBeNull();
    expect(result.text).not.toBeNull();
  });

  it("posts the manual refresh and returns the verdict", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      ...STORED_WIRE,
      outcome: "summarized",
    });

    const result = await refreshTypeSummary(WORKSPACE_ID, "Requirement");

    expect(apiClient.post).toHaveBeenCalledWith(
      `/workspaces/${WORKSPACE_ID}/summaries/Requirement/refresh/`,
      {},
    );
    expect(result.outcome).toBe("summarized");
    expect(result.summaryKind).toBe("type_roster");
  });

  it("passes a skipped verdict through unchanged", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      ...STORED_WIRE,
      outcome: "skipped:budget_exhausted",
      reason: "budget_exhausted",
    });

    const result = await refreshTypeSummary(WORKSPACE_ID, "Requirement");

    expect(result.outcome).toBe("skipped:budget_exhausted");
    expect(result.reason).toBe("budget_exhausted");
  });
});
