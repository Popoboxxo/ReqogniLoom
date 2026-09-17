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

import { apiClient, getAllPages, getList } from "./client";
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

  /**
   * Fetch the complete workspace list across all pages (issue C /
   * GESAMTTEST_BERICHT_2026-08-21 §10.2): `list()` only returns page 1
   * (default page size 25), so any tenant with more workspaces than that
   * had entries unreachable via the UI switcher. Used by
   * `WorkspaceContext.reloadWorkspaces` instead of `list()`.
   */
  listAll(): Promise<Workspace[]> {
    return getAllPages<Workspace>("/workspaces/");
  },

  get(id: UUID): Promise<Workspace> {
    return apiClient.get<Workspace>(`/workspaces/${id}/`);
  },

  create(payload: WorkspaceCreatePayload): Promise<Workspace> {
    return apiClient.post<Workspace>("/workspaces/", payload);
  },

  update(
    id: UUID,
    data: Partial<{
      name: string;
      language: string;
      theme: string;
      terminology_profile: TerminologyProfile;
      decomposition_link_type: string;
      default_link_type: string;
      ai_prompts: Record<string, string>;
      goals_enabled: boolean;
      goals_ai_enabled: boolean;
    }>
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
    // Auth flows via the httpOnly cookie (REQ-052) — send credentials, no header.
    const resp = await fetch(
      `/api/v1/workspaces/${id}/reports/pdf/?layout=${layout}`
    , { credentials: "same-origin" });
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
    return apiClient.post<Workspace>(`/workspaces/${id}/close/`, {});
  },

  /**
   * Reactivate a closed workspace (admin only).
   * POST /api/v1/workspaces/{id}/reactivate/
   */
  reactivateWorkspace(id: UUID): Promise<Workspace> {
    return apiClient.post<Workspace>(`/workspaces/${id}/reactivate/`, {});
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
