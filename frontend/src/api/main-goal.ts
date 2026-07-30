/**
 * ARCH-L1-001 ReactFrontend — MainGoal API.
 *
 * leaf_id: COMP-RF-XXX (MainGoal panel)
 * req_id:  REQ-L2-TE-020 (Haupt-Ziel / MainGoal artifact)
 *
 * Wraps /api/v1/main-goals/ endpoints (backend/rest_api/views.py
 * MainGoalViewSet). MainGoal is a single workspace-scoped version chain (not
 * lineage-based like Goal); `approve` transitions a draft to `Freigegeben`.
 */

import { apiClient } from "./client";
import type { ArtifactVersion, MainGoal, UUID } from "../types";

export const mainGoalApi = {
  /** GET /main-goals/current/?workspace_id= — newest Freigegeben MainGoal (or null). */
  current(workspaceId: UUID): Promise<MainGoal | null> {
    return apiClient.get<MainGoal | null>(
      `/main-goals/current/?workspace_id=${encodeURIComponent(workspaceId)}`
    );
  },

  /** POST /main-goals/generate/ — aggregate current Goals into a new AI draft. */
  generate(workspaceId: UUID): Promise<MainGoal> {
    return apiClient.post<MainGoal>("/main-goals/generate/", { workspace_id: workspaceId });
  },

  /** POST /main-goals/ — manually author a new MainGoal draft. */
  createManual(workspaceId: UUID, content: string): Promise<MainGoal> {
    return apiClient.post<MainGoal>("/main-goals/", { workspace_id: workspaceId, content });
  },

  /** POST /main-goals/{id}/approve/ — transition a draft to Freigegeben. */
  approve(mainGoalId: UUID): Promise<MainGoal> {
    return apiClient.post<MainGoal>(`/main-goals/${mainGoalId}/approve/`, {});
  },

  /** GET /main-goals/{id}/versions/ — all versions for this MainGoal's workspace. */
  versions(mainGoalId: UUID): Promise<ArtifactVersion[]> {
    return apiClient.get<ArtifactVersion[]>(`/main-goals/${mainGoalId}/versions/`);
  },
};
