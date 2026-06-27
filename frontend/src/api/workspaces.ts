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

import { apiClient, getList } from "./client";
import type { PaginatedResponse, UUID, Workspace } from "../types";

export const workspacesApi = {
  list(): Promise<PaginatedResponse<Workspace>> {
    return getList<Workspace>("/workspaces/");
  },

  get(id: UUID): Promise<Workspace> {
    return apiClient.get<Workspace>(`/workspaces/${id}/`);
  },
};
