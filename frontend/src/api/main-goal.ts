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

import { apiClient, getList } from "./client";
import type { ArtifactVersion, MainGoal, UUID } from "../types";

/**
 * Recommendation 3 (issue #221 review round 2): `MainGoalService.list_all`
 * already sorts `-sequence_number` (newest first), so a pending draft — if
 * any — is practically always on page 1. Fetching every page via
 * `getAllPages` was needless work for a chain that, in the vast majority of
 * workspaces, holds far fewer than this many versions anyway; a handful is
 * enough headroom for `MainGoalPanel`'s "newest row above the approved
 * sequence_number" scan.
 */
const RECENT_VERSIONS_LIMIT = 10;

export const mainGoalApi = {
  /** GET /main-goals/current/?workspace_id= — newest Freigegeben MainGoal (or null). */
  current(workspaceId: UUID): Promise<MainGoal | null> {
    return apiClient.get<MainGoal | null>(
      `/main-goals/current/?workspace_id=${encodeURIComponent(workspaceId)}`
    );
  },

  /**
   * GET /main-goals/?workspace_id= — the most recent versions in the
   * workspace's chain (newest first). Issue #221 finding 6: `MainGoalPanel`
   * uses this to find a draft that was generated/authored in an earlier
   * session but never approved, so the Approve control survives a page
   * refresh.
   */
  async list(workspaceId: UUID): Promise<MainGoal[]> {
    const resp = await getList<MainGoal>("/main-goals/", {
      workspace_id: workspaceId,
      page_size: String(RECENT_VERSIONS_LIMIT),
    });
    return resp.results;
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
