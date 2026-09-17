/**
 * ARCH-L1-001 ReactFrontend — Traceability read-model API.
 *
 * leaf_id: COMP-RF-005
 * req_id:  REQ-L2-RF-006 (Traceability-Anzeige), REQ-L2-TE-019 (graph queries)
 *
 * Wraps the read-only /api/v1/traceability/ graph endpoints (impact, path,
 * cycles). The CRUD operations for trace links remain in ``tracelinks.ts``
 * under /api/v1/tracelinks/ for backward compatibility.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";
import {
  RESOLVE_BATCH_LIMIT,
  type CyclesResponse,
  type ImpactNode,
  type ImpactParams,
  type ResolvedArtifact,
  type TracePath,
} from "./tracelinks";

export type {
  CyclesResponse,
  ImpactDirection,
  ImpactNode,
  ImpactParams,
  ResolvedArtifact,
  TracePath,
} from "./tracelinks";
export { RESOLVE_BATCH_LIMIT } from "./tracelinks";

export const traceabilityApi = {
  /** Impact analysis: all artifacts reachable from an artifact (REQ-L2-TE-019). */
  impact(artifactId: UUID, params: ImpactParams = {}): Promise<ImpactNode[]> {
    const query = new URLSearchParams({ artifact_id: artifactId });
    if (params.direction) query.set("direction", params.direction);
    if (params.maxDepth != null) query.set("max_depth", String(params.maxDepth));
    if (params.limit != null) query.set("limit", String(params.limit));
    if (params.linkTypes && params.linkTypes.length > 0) {
      query.set("link_types", params.linkTypes.join(","));
    }
    return apiClient.get<ImpactNode[]>(
      `/traceability/impact/?${query.toString()}`
    );
  },

  /** Shortest path(s) between two artifacts (REQ-L2-TE-019). */
  path(sourceId: UUID, targetId: UUID, maxDepth?: number): Promise<TracePath[]> {
    const query = new URLSearchParams({
      source_id: sourceId,
      target_id: targetId,
    });
    if (maxDepth != null) query.set("max_depth", String(maxDepth));
    return apiClient.get<TracePath[]>(
      `/traceability/path/?${query.toString()}`
    );
  },

  /** Cycles detected in a workspace trace graph (REQ-L2-TE-019). */
  cycles(workspaceId: UUID): Promise<CyclesResponse> {
    return apiClient.get<CyclesResponse>(
      `/traceability/cycles/?workspace_id=${workspaceId}`
    );
  },

  /**
   * Batch-resolve Artifact ids to their backing domain entity (Task 3.2b,
   * REQ-L2-TE-019). One call for the whole set, not one per entry — mirrors
   * the backend's own batch design (`resolve_artifacts`, capped at
   * `RESOLVE_BATCH_LIMIT`). Duplicate/empty ids are dropped before the
   * request; an empty input short-circuits without a network call. Results
   * are NOT guaranteed to preserve input order-to-index correspondence for
   * callers that dedupe — match on `artifact_id` in the response.
   */
  resolve(artifactIds: UUID[]): Promise<ResolvedArtifact[]> {
    const unique = [...new Set(artifactIds.filter((id): id is UUID => Boolean(id)))];
    if (unique.length === 0) return Promise.resolve([]);
    const capped = unique.slice(0, RESOLVE_BATCH_LIMIT);
    const query = new URLSearchParams({ artifact_ids: capped.join(",") });
    return apiClient.get<ResolvedArtifact[]>(
      `/traceability/resolve/?${query.toString()}`
    );
  },
};
