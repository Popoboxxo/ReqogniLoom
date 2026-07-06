import { apiClient } from "./client";
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
  // Diff / Versions — stubs (UI standards §4.5 / §11 Backend gaps)
  // -----------------------------------------------------------------------

  /**
   * Field-level diff between two Stakeholder Need versions. Signature
   * mirrors `requirementsApi.diff` / `architectureApi.diff` so the
   * DiffPanel can swap fetchers per kind without changing the call site.
   * TODO(backend): wire to GET /api/v1/needs/{id}/diff/ (not exposed yet).
   */
  diff: async (id: string, fromVersion: number, toVersion: number): Promise<ArtifactDiffResult> => {
    return Promise.reject(
      new Error(
        `Not Implemented: StakeholderNeed /diff/ endpoint for ${id} (from v${fromVersion} to v${toVersion}) — see UI standards §11.`
      )
    );
  },

  /**
   * Version list for a Stakeholder Need. The backend does not expose a
   * `/versions/` endpoint for stakeholder needs. DiffPanel will short-circuit
   * to its empty state for StakeholderNeed in the meantime.
   * TODO(backend): wire to GET /api/v1/needs/{id}/versions/.
   */
  versions: async (id: string): Promise<ArtifactVersion[]> => {
    return Promise.reject(
      new Error(
        `Not Implemented: StakeholderNeed /versions/ endpoint for ${id} — see UI standards §11.`
      )
    );
  },
};
