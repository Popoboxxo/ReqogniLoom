import { apiClient, getAllPages } from "./client";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  StakeholderNeed,
  PaginatedResponse,
} from "../types";

export interface DerivedRequirementDraft {
  title: string;
  description: string;
  rationale: string;
  suggested_parent_id: string;
}

export const stakeholderNeedApi = {
  listByWorkspace: async (workspaceId: string, params?: Record<string, string>): Promise<PaginatedResponse<StakeholderNeed>> => {
    const qs = params ? `?${new URLSearchParams(params).toString()}` : '';
    return apiClient.get<PaginatedResponse<StakeholderNeed>>(`/workspaces/${workspaceId}/needs/${qs}`);
  },

  /**
   * Fetch all Stakeholder Needs for a workspace, following pagination links
   * until exhaustion (issue C — listByWorkspace() only returned page 1).
   */
  listAll: async (workspaceId: string): Promise<StakeholderNeed[]> => {
    return getAllPages<StakeholderNeed>(`/workspaces/${workspaceId}/needs/`);
  },

  get: async (id: string): Promise<StakeholderNeed> => {
    return apiClient.get<StakeholderNeed>(`/needs/${id}/`);
  },

  create: async (workspaceId: string, data: Partial<StakeholderNeed>): Promise<StakeholderNeed> => {
    return apiClient.post<StakeholderNeed>(`/workspaces/${workspaceId}/needs/`, data);
  },

  /**
   * REQ-162: `change_reason` is mandatory when the workspace preset requires
   * it (Extended preset — see backend/application/preset_policy_service.py,
   * `is_change_reason_required`).
   *
   * Task 23 (rollout wave 2c): widened from a fixed `Partial<Pick<StakeholderNeed,
   * ...>>` to `Record<string, unknown>`, same deviation as `risksApi.update`/
   * `issuesApi.update` (Tasks 19/20). The payload now comes from `ArtifactForm`
   * (`NeedArtifactForm`'s `formValuesToNeedPatch`), a generic definition-driven
   * value bag whose keys are whatever the resolved attribute definition
   * currently lists, not a fixed compile-time-known set — the backend's own
   * per-field 400s remain the actual validation authority (see
   * StakeholderNeedViewSet.partial_update / field_validation.py).
   */
  update: async (id: string, data: Record<string, unknown>): Promise<StakeholderNeed> => {
    return apiClient.patch<StakeholderNeed>(`/needs/${id}/`, data);
  },

  delete: async (id: string, change_reason?: string): Promise<void> => {
    return apiClient.delete(`/needs/${id}/`, { data: { change_reason } });
  },

  /** Async fire-and-forget Celery dispatch. Result not persisted/read by UI. */
  derive: async (id: string): Promise<{ task_id: string; message: string }> => {
    return apiClient.post<{ task_id: string; message: string }>(`/needs/${id}/derive/`, {});
  },

  /** Draft/Accept (REQ-L2-AI-001/002): returns proposed requirements without persisting. */
  deriveRequirements: async (
    id: string,
    n = 3
  ): Promise<{ drafts: DerivedRequirementDraft[] }> => {
    return apiClient.post<{ drafts: DerivedRequirementDraft[] }>(
      `/needs/${id}/derive-requirements/`,
      { n }
    );
  },

  // -----------------------------------------------------------------------
  // Diff / Versions — backend-backed (GET /api/v1/needs/{id}/{diff,versions}/)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two Stakeholder Need versions. Signature
   * mirrors `requirementsApi.diff` / `architectureApi.diff` so the
   * DiffPanel can swap fetchers per kind without changing the call site.
   */
  diff: async (id: string, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> => {
    return apiClient.get<ArtifactDiffResult>(
      `/needs/${id}/diff/?from_version=${fromVersion}&to_version=${toVersion}`
    );
  },

  /** Version list for a Stakeholder Need. */
  versions: async (id: string): Promise<ArtifactVersion[]> => {
    return apiClient.get<ArtifactVersion[]>(`/needs/${id}/versions/`);
  },
};
