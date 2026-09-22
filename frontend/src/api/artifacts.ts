/**
 * ARCH-L1-001 ReactFrontend — Artifacts API.
 *
 * leaf_id: COMP-RF-001 (SidebarNavigation / ArtifactTree)
 * req_id:  REQ-L2-RF-005 (Artefakt-Navigation)
 *
 * Wraps /api/v1/artifacts/ endpoints.
 */

import { apiClient, getList } from "./client";
import type { Artifact, ISODateTime, PaginatedResponse, UUID } from "../types";

/**
 * #399: one baseline the artifact is a member of, with its drift verdict.
 * Mirrors `BaselineFacade.ArtifactBaselineMembership` (spec section 6.2).
 */
export interface ArtifactBaselineMembership {
  baseline_id: UUID;
  baseline_name: string;
  /** document | project | global */
  scope: string;
  baselined_at: ISODateTime;
  baselined_version: number;
  current_version: number;
  drifted: boolean;
  /**
   * `false` for legacy delta-index entries captured without a `state` — the
   * version comparison is then the only signal available.
   */
  drift_known: boolean;
}

/** #399: response of `GET /api/v1/artifacts/{id}/baseline-membership/`. */
export interface BaselineMembershipResponse {
  artifact_id: UUID;
  /** `true` when at least one membership is drifted. */
  drifted: boolean;
  memberships: ArtifactBaselineMembership[];
}

export const artifactsApi = {
  list(workspaceId: UUID, parentId?: UUID): Promise<PaginatedResponse<Artifact>> {
    const params: Record<string, string> = { workspace_id: workspaceId };
    if (parentId) params["parent_id"] = parentId;
    return getList<Artifact>("/artifacts/", params);
  },

  get(id: UUID): Promise<Artifact> {
    return apiClient.get<Artifact>(`/artifacts/${id}/`);
  },

  /**
   * #399: baseline membership + drift for one artifact. Called once per open
   * editor header, never per list row (spec D7 — a list badge would be an
   * N+1 without a batch endpoint).
   */
  baselineMembership(id: UUID): Promise<BaselineMembershipResponse> {
    return apiClient.get<BaselineMembershipResponse>(
      `/artifacts/${id}/baseline-membership/`
    );
  },

  create(data: {
    workspace_id: UUID;
    artifact_type: string;
    parent_id?: UUID;
  }): Promise<Artifact> {
    return apiClient.post<Artifact>("/artifacts/", data);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/artifacts/${id}/`);
  },
};
