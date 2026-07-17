import { apiClient, getAllPages } from "./client";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  StakeholderNeed,
  PaginatedResponse,
} from "../types";

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

  update: async (id: string, data: Partial<StakeholderNeed>): Promise<StakeholderNeed> => {
    return apiClient.patch<StakeholderNeed>(`/needs/${id}/`, data);
  },

  delete: async (id: string, change_reason?: string): Promise<void> => {
    return apiClient.delete(`/needs/${id}/`, { data: { change_reason } });
  },

  derive: async (id: string): Promise<{ task_id: string; message: string }> => {
    return apiClient.post<{ task_id: string; message: string }>(`/needs/${id}/derive/`, {});
  },

  deriveRequirements: async (id: string): Promise<{ task_id: string }> => {
    return apiClient.post<{ task_id: string }>(`/needs/${id}/derive/`, {});
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
