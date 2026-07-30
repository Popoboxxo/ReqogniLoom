/**
 * ARCH-L1-001 ReactFrontend — Goals API.
 *
 * leaf_id: COMP-RF-XXX (Goals panel)
 * req_id:  REQ-L2-TE-020 (Ziele / Goal artifact)
 *
 * Wraps /api/v1/goals/ endpoints (backend/rest_api/views.py GoalViewSet).
 * Goal versioning is lineage-based (Variante A): every edit creates a new
 * row sharing the same `lineage_id`.
 */

import { apiClient, getList } from "./client";
import type { ArtifactVersion, Goal, UUID } from "../types";

export const goalsApi = {
  /** GET /goals/?workspace_id= — the latest version of every Goal lineage. */
  async list(workspaceId: UUID): Promise<Goal[]> {
    const page = await getList<Goal>("/goals/", { workspace_id: workspaceId });
    return page.results;
  },

  /** POST /goals/ — start a new Goal lineage. */
  create(
    workspaceId: UUID,
    payload: { title: string; description: string }
  ): Promise<Goal> {
    return apiClient.post<Goal>("/goals/", { workspace_id: workspaceId, ...payload });
  },

  /** POST /goals/ with `lineage_id` — append a new version to an existing lineage. */
  createVersion(
    lineageId: UUID,
    payload: { workspace_id: UUID; title: string; description: string }
  ): Promise<Goal> {
    return apiClient.post<Goal>("/goals/", { ...payload, lineage_id: lineageId });
  },

  /** GET /goals/{id}/versions/ — all versions of this Goal's lineage. */
  versions(goalId: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/goals/${goalId}/versions/`);
  },
};
