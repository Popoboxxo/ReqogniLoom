/**
 * ARCH-L1-001 ReactFrontend — Workspace Members API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceSettings scope)
 * req_id:  REQ-014 (Item-Permission user picker, COMP-AT-002),
 *          multi-user management design spec (role assign/suspend/reactivate)
 *
 * Wraps:
 *   GET  /api/v1/workspaces/{workspace_id}/members/                          (any active member)
 *   POST /api/v1/workspaces/{workspace_id}/members/                          (assign a role, admin-guarded)
 *   POST /api/v1/workspaces/{workspace_id}/members/{user_id}/suspend/        (admin-guarded)
 *   POST /api/v1/workspaces/{workspace_id}/members/{user_id}/reactivate/     (admin-guarded)
 * Provides the roster that backs the Item-Permission user picker so admins no
 * longer copy-paste raw user UUIDs, plus the role lifecycle actions used by
 * the User Management screen.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export interface WorkspaceMember {
  user_id: UUID;
  username: string;
  email: string;
  display_name: string;
  roles: string[];
}

export interface AssignRolePayload {
  user_id: UUID;
  role: string;
}

export const workspaceMembersApi = {
  /** List the active members of a workspace. Requires workspace membership. */
  async list(workspaceId: UUID): Promise<WorkspaceMember[]> {
    const resp = await apiClient.get<{ members: WorkspaceMember[] }>(
      `/workspaces/${workspaceId}/members/`
    );
    return resp.members;
  },

  /**
   * Assign a role to a user in this workspace. Requires workspace-admin or
   * tenant-admin. The preset tier is resolved server-side (never trust a
   * client-supplied tier for the Approver-role gate), so no `preset` field
   * is sent here.
   */
  async assignRole(workspaceId: UUID, payload: AssignRolePayload): Promise<void> {
    return apiClient.post(`/workspaces/${workspaceId}/members/`, payload);
  },

  /**
   * Suspend a single role of a member in this workspace. Requires
   * workspace-admin or tenant-admin; rejected with a `LAST_ADMIN` 409 if
   * this would leave the workspace without an active admin.
   */
  async suspendRole(workspaceId: UUID, userId: UUID, role: string): Promise<void> {
    return apiClient.post(`/workspaces/${workspaceId}/members/${userId}/suspend/`, { role });
  },

  /**
   * Reactivate a previously suspended role of a member in this workspace.
   * Requires workspace-admin or tenant-admin.
   */
  async reactivateRole(workspaceId: UUID, userId: UUID, role: string): Promise<void> {
    return apiClient.post(`/workspaces/${workspaceId}/members/${userId}/reactivate/`, { role });
  },
};
