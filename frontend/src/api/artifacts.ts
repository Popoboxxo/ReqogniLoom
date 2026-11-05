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
  /**
   * Informational: the `Artifact.version` captured at baseline time — not the
   * entity's own version. A content edit bumps the entity version without
   * bumping `Artifact.version`, so this can equal `current_version` even when
   * the artifact genuinely drifted. `drifted` is authoritative.
   */
  baselined_version: number;
  /** Informational: the `Artifact.version` right now; same caveat as `baselined_version`. */
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

/**
 * Body of `POST /api/v1/artifacts/{id}/move/` (P1 Task 1.4).
 *
 * The two fields encode *three* cases, because the server distinguishes an
 * absent `after_id` from an explicit `null` (spec B8):
 *   - `parent_id` only            → append at the end of the new parent,
 *   - `after_id: null`            → insert as the first child,
 *   - `after_id: '<sibling id>'`  → insert directly behind that sibling.
 *
 * `after_id` is therefore optional and never derived from `parent_id`; a
 * caller that means "first" must pass `null`, not `undefined`.
 */
export interface MoveArtifactOptions {
  parent_id: UUID | null;
  after_id?: UUID | null;
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

  /**
   * Reparent and/or reorder one artifact (`POST /artifacts/{id}/move/`).
   *
   * `id` is the **backing Artifact** id, not the entity id an editor route
   * uses — `Requirement.artifact_id` / `ArchitectureElement.artifact_id` is
   * the value this route keys on. Passing an entity id answers 404.
   */
  move(id: UUID, options: MoveArtifactOptions): Promise<Artifact> {
    const body: { parent_id: UUID | null; after_id?: UUID | null } = {
      parent_id: options.parent_id,
    };
    // Presence, not truthiness: `null` means "insert first" and must survive,
    // while an omitted/undefined key means "append at the end". JSON drops an
    // undefined value either way, so only the key is written when it is set.
    if (options.after_id !== undefined) body.after_id = options.after_id;
    return apiClient.post<Artifact>(`/artifacts/${id}/move/`, body);
  },

  delete(id: UUID): Promise<void> {
    return apiClient.delete(`/artifacts/${id}/`);
  },
};
