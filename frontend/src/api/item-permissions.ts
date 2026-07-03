/**
 * ARCH-L1-001 ReactFrontend — Item Permissions API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceSettings scope)
 * req_id:  REQ-L1-039 (ItemPermission CRUD, COMP-AT-005)
 *
 * Wraps /api/v1/workspaces/{workspace_id}/permissions/ (admin-only).
 *   GET    ?user_id=<uuid>[&artifact_id=<uuid>] — list rules
 *   POST   {user_id, artifact_id?, permission_level}  — grant (upsert)
 *   DELETE ?permission_id=<uuid>                       — revoke
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

export type ItemPermissionLevel = "read" | "write" | "none";

export interface ItemPermission {
  id: UUID;
  user_id: UUID;
  workspace_id: UUID;
  artifact_id: UUID | null;
  permission_level: ItemPermissionLevel;
  granted_by: UUID | null;
  is_workspace_wide: boolean;
  is_explicit_deny: boolean;
}

export const itemPermissionsApi = {
  /** List permission rules for a (user, workspace) pair. Admin-only. */
  async list(
    workspaceId: UUID,
    userId: UUID,
    artifactId?: UUID
  ): Promise<ItemPermission[]> {
    const query = new URLSearchParams({ user_id: userId });
    if (artifactId) query.set("artifact_id", artifactId);
    const resp = await apiClient.get<{ permissions: ItemPermission[] }>(
      `/workspaces/${workspaceId}/permissions/?${query.toString()}`
    );
    return resp.permissions;
  },

  /** Grant (upsert) a permission rule. Admin-only. */
  async grant(
    workspaceId: UUID,
    data: {
      user_id: UUID;
      artifact_id?: UUID | null;
      permission_level: ItemPermissionLevel;
    }
  ): Promise<ItemPermission> {
    const resp = await apiClient.post<{ permission: ItemPermission }>(
      `/workspaces/${workspaceId}/permissions/`,
      data
    );
    return resp.permission;
  },

  /** Revoke a permission rule by id. Admin-only. */
  revoke(workspaceId: UUID, permissionId: UUID): Promise<void> {
    // DELETE with the id in the query string — apiClient.delete sends no body.
    return apiClient.delete(
      `/workspaces/${workspaceId}/permissions/?permission_id=${permissionId}`
    );
  },
};
