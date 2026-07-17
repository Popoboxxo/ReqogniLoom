/**
 * ARCH-L1-001 ReactFrontend — TraceLinks API.
 *
 * leaf_id: COMP-RF-003, COMP-RF-004
 * req_id:  REQ-L2-RF-006 (Traceability-Anzeige)
 *
 * Wraps /api/v1/tracelinks/ endpoints.
 */

import { apiClient, getAllPages, getList } from "./client";
import type {
  TraceLink,
  PaginatedResponse,
  SimilarTraceLink,
  UUID,
} from "../types";

/** A single artifact reachable in an impact analysis (REQ-L2-TE-019). */
export interface ImpactNode {
  artifact_id: UUID;
  artifact_type: string;
  title: string;
  uid: string | null;
  link_type: string;
  depth: number;
  path: UUID[];
}

/** A single trace path between two artifacts (REQ-L2-TE-019). */
export interface TracePath {
  nodes: UUID[];
  length: number;
}

/** Cycle-detection result for a workspace (REQ-L2-TE-019). */
export interface CyclesResponse {
  cycles: UUID[][];
  count: number;
}

export type ImpactDirection = "outgoing" | "incoming" | "both";

export interface ImpactParams {
  direction?: ImpactDirection;
  maxDepth?: number;
  linkTypes?: string[];
  limit?: number;
}

export const tracelinksApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<TraceLink>> {
    return getList<TraceLink>("/tracelinks/", {
      workspace_id: workspaceId,
    });
  },

  /**
   * Fetch all TraceLinks for a workspace, following pagination links until
   * exhaustion (issue C — list() only returned the first page, capped at
   * PAGE_SIZE=25).
   */
  async listAll(workspaceId: UUID): Promise<TraceLink[]> {
    return getAllPages<TraceLink>("/tracelinks/", { workspace_id: workspaceId });
  },

  listForArtifact(
    workspaceId: UUID,
    artifactId: UUID
  ): Promise<PaginatedResponse<TraceLink>> {
    return getList<TraceLink>("/tracelinks/", {
      workspace_id: workspaceId,
      artifact_id: artifactId,
    });
  },

  create(data: {
    source_id: UUID;
    target_id: UUID;
    link_type: string;
  }): Promise<TraceLink> {
    return apiClient.post<TraceLink>("/tracelinks/", data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/tracelinks/${id}/`);
  },

  /** Impact analysis: all artifacts reachable from an artifact (REQ-L2-TE-019). */
  impact(artifactId: UUID, params: ImpactParams = {}): Promise<ImpactNode[]> {
    const query = new URLSearchParams({ artifact_id: artifactId });
    if (params.direction) query.set("direction", params.direction);
    if (params.maxDepth != null) query.set("max_depth", String(params.maxDepth));
    if (params.limit != null) query.set("limit", String(params.limit));
    if (params.linkTypes && params.linkTypes.length > 0) {
      query.set("link_types", params.linkTypes.join(","));
    }
    return apiClient.get<ImpactNode[]>(`/tracelinks/impact/?${query.toString()}`);
  },

  /** Shortest path(s) between two artifacts (REQ-L2-TE-019). */
  path(sourceId: UUID, targetId: UUID, maxDepth?: number): Promise<TracePath[]> {
    const query = new URLSearchParams({
      source_id: sourceId,
      target_id: targetId,
    });
    if (maxDepth != null) query.set("max_depth", String(maxDepth));
    return apiClient.get<TracePath[]>(`/tracelinks/path/?${query.toString()}`);
  },

  /** Cycles detected in a workspace trace graph (REQ-L2-TE-019). */
  cycles(workspaceId: UUID): Promise<CyclesResponse> {
    return apiClient.get<CyclesResponse>(
      `/tracelinks/cycles/?workspace_id=${workspaceId}`
    );
  },

  /**
   * REQ-L2-VS-004: fetch the top-N trace links most similar to the given one
   * by semantic (cosine) similarity over pgvector embeddings. The backend
   * returns 400 when the link has no embedding yet and 503 when pgvector is
   * unavailable — callers should surface these.
   */
  getSimilar(tracelinkId: UUID, limit = 10): Promise<SimilarTraceLink[]> {
    return apiClient.get<SimilarTraceLink[]>(
      `/tracelinks/similar/?tracelink_id=${tracelinkId}&limit=${limit}`
    );
  },
};
