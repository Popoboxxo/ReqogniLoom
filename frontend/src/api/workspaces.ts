/**
 * ARCH-L1-001 ReactFrontend — Workspaces API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — workspace bootstrap)
 * req_id:  REQ-L2-RF-012 (Workspace-Konfigurations-UI),
 *          REQ-L2-RF-007 (Preset-basierte Sichtbarkeit),
 *          REQ-L2-RF-008 (Terminologie-Profil)
 *
 * Wraps /api/v1/workspaces/ endpoints.
 */

import { apiClient, getList, getAuthToken } from "./client";
import type {
  PaginatedResponse,
  TerminologyProfile,
  UUID,
  Workspace,
  WorkspacePreset,
} from "../types";

export interface WorkspaceCreatePayload {
  name: string;
  preset: WorkspacePreset;
  terminology_profile: TerminologyProfile;
  language: string;
}

export const workspacesApi = {
  list(): Promise<PaginatedResponse<Workspace>> {
    return getList<Workspace>("/workspaces/");
  },

  get(id: UUID): Promise<Workspace> {
    return apiClient.get<Workspace>(`/workspaces/${id}/`);
  },

  create(payload: WorkspaceCreatePayload): Promise<Workspace> {
    return apiClient.post<Workspace>("/workspaces/", payload);
  },

  update(
    id: UUID,
    data: Partial<{ name: string; language: string; terminology_profile: TerminologyProfile; decomposition_link_type: string }>
  ): Promise<Workspace> {
    return apiClient.patch<Workspace>(`/workspaces/${id}/`, data);
  },

  clone(id: UUID, target_name: string): Promise<Workspace> {
    return apiClient.post<Workspace>(`/workspaces/${id}/clone/`, { target_name });
  },

  setPreset(id: UUID, preset: WorkspacePreset): Promise<{ id: string; preset: string }> {
    return apiClient.patch<{ id: string; preset: string }>(`/workspaces/${id}/preset/`, { preset });
  },

  /**
   * Download a PDF report for the workspace.
   * REQ-L2-AS-016 / REQ-L2-RF-005 / REQ-L2-RF-006.
   */
  async downloadPdfReport(
    id: UUID,
    layout: "requirement_document" | "traceability_matrix" = "requirement_document"
  ): Promise<Blob> {
    const token = getAuthToken();
    const headers: Record<string, string> = {};
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const resp = await fetch(
      `/api/v1/workspaces/${id}/reports/pdf/?layout=${layout}`
    , { headers });
    if (!resp.ok) {
      throw new Error(`PDF export failed: ${resp.status}`);
    }
    return resp.blob();
  },

  // ---- Lifecycle API (REQ-L1-042) ----

  /**
   * Soft-close a workspace (admin only).
   * POST /api/v1/workspaces/{id}/close/
   */
  closeWorkspace(id: UUID): Promise<Workspace> {
    return apiClient.post<Workspace>(`/workspaces/${id}/close/`);
  },

  /**
   * Reactivate a closed workspace (admin only).
   * POST /api/v1/workspaces/{id}/reactivate/
   */
  reactivateWorkspace(id: UUID): Promise<Workspace> {
    return apiClient.post<Workspace>(`/workspaces/${id}/reactivate/`);
  },

  /**
   * Hard-delete a workspace with captcha confirmation (admin only).
   * POST /api/v1/workspaces/{id}/delete/
   * Body: { confirmation: "<workspace name>" }
   */
  deleteWorkspace(id: UUID, confirmation: string): Promise<void> {
    return apiClient.post<void>(`/workspaces/${id}/delete/`, { confirmation });
  },
};
