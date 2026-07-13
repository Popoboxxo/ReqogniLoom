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
import type {
  CyclesResponse,
  ImpactNode,
  ImpactParams,
  TracePath,
} from "./tracelinks";

export type {
  CyclesResponse,
  ImpactDirection,
  ImpactNode,
  ImpactParams,
  TracePath,
} from "./tracelinks";

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
};
