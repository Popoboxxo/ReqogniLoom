/**
 * ARCH-L1-001 ReactFrontend — TraceLinks API.
 *
 * leaf_id: COMP-RF-003, COMP-RF-004
 * req_id:  REQ-L2-RF-006 (Traceability-Anzeige)
 *
 * Wraps /api/v1/tracelinks/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { TraceLink, PaginatedResponse, UUID } from "../types";

export const tracelinksApi = {
  list(workspaceId: UUID): Promise<PaginatedResponse<TraceLink>> {
    return getList<TraceLink>("/tracelinks/", {
      workspace_id: workspaceId,
    });
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
};
