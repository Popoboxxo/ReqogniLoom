/**
 * ARCH-L1-001 ReactFrontend — Workspace Members API.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — WorkspaceSettings scope)
 * req_id:  REQ-014 (Item-Permission user picker, COMP-AT-002)
 *
 * Wraps GET /api/v1/workspaces/{workspace_id}/members/ (any active member).
 * Provides the roster that backs the Item-Permission user picker so admins no
 * longer copy-paste raw user UUIDs.
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

export const workspaceMembersApi = {
  /** List the active members of a workspace. Requires workspace membership. */
  async list(workspaceId: UUID): Promise<WorkspaceMember[]> {
    const resp = await apiClient.get<{ members: WorkspaceMember[] }>(
      `/workspaces/${workspaceId}/members/`
    );
    return resp.members;
  },
};
