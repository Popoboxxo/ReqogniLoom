/**
 * ARCH-L1-001 ReactFrontend — visual requirement groups (P6 Task 6.3).
 *
 * Wraps the committed group REST surface:
 *
 *   GET  /api/v1/groups/?workspace_id=<uuid>          -> { results: Group[] }
 *   POST /api/v1/groups/                              -> Group
 *   GET  /api/v1/groups/{id}/members/                 -> { members: GroupMember[] }
 *   POST /api/v1/groups/{id}/members/                 -> { members: GroupMember[] }
 *   POST /api/v1/groups/{id}/members/remove/          -> 204
 *   POST /api/v1/groups/{id}/members/move/            -> { trace_link_id, sort_key }
 *
 * Two id spaces show up here and must never be mixed up:
 *
 * - A member is identified by its **requirement entity id** in every write
 *   (`requirement_id`), because that is what the service resolves to the
 *   backing artifact.
 * - Everything the read side returns — `requirement_artifact_id` and the
 *   `after_id` anchor of a move — is an **artifact id** (`requirement_artifact_id`
 *   is the member's artifact, `after_id` is the *TraceLink* id of the member
 *   the moved one should follow).
 *
 * The membership order lives on `TraceLink.sort_key` (nullable, used only for
 * `grouped-in` links); the read side returns the rows already sorted by it.
 */

import { apiClient } from "./client";
import type { UUID } from "../types";

/** One visual requirement group. */
export interface RequirementGroup {
  id: UUID;
  workspace_id: UUID;
  title: string;
  description: string;
}

/** One ordered group membership (`grouped-in` TraceLink). */
export interface GroupMember {
  /** Id of the membership link — the anchor a move is expressed against. */
  trace_link_id: UUID;
  /** Backing Artifact id of the member requirement. */
  requirement_artifact_id: UUID;
  sort_key: string | null;
}

/** A group together with its ordered membership. */
export interface GroupWithMembers extends RequirementGroup {
  members: GroupMember[];
}

interface GroupsListResponse {
  results: RequirementGroup[];
}

interface MembersResponse {
  members: GroupMember[];
}

export interface MoveMemberResult {
  trace_link_id: UUID;
  sort_key: string | null;
}

export const groupsApi = {
  /** List the workspace's groups (creation order, as the service returns them). */
  async list(workspaceId: UUID): Promise<RequirementGroup[]> {
    const response = await apiClient.get<GroupsListResponse>(
      `/groups/?workspace_id=${encodeURIComponent(workspaceId)}`
    );
    return response.results ?? [];
  },

  /** Create a group. The title lives in the artifact's `custom_fields`. */
  create(
    workspaceId: UUID,
    title: string,
    description = ""
  ): Promise<RequirementGroup> {
    return apiClient.post<RequirementGroup>("/groups/", {
      workspace_id: workspaceId,
      title,
      description,
    });
  },

  /** The group's members, already ordered by their membership `sort_key`. */
  async members(groupId: UUID): Promise<GroupMember[]> {
    const response = await apiClient.get<MembersResponse>(
      `/groups/${groupId}/members/`
    );
    return response.members ?? [];
  },

  /**
   * Append a requirement to a group (or insert it behind `afterTraceLinkId`,
   * the membership link of the anchor member).
   */
  async addMember(
    groupId: UUID,
    requirementId: UUID,
    afterTraceLinkId?: UUID
  ): Promise<GroupMember[]> {
    const response = await apiClient.post<MembersResponse>(
      `/groups/${groupId}/members/`,
      {
        requirement_id: requirementId,
        ...(afterTraceLinkId ? { after_id: afterTraceLinkId } : {}),
      }
    );
    return response.members ?? [];
  },

  /** Remove a requirement from a group. */
  removeMember(groupId: UUID, requirementId: UUID): Promise<void> {
    return apiClient.post<void>(`/groups/${groupId}/members/remove/`, {
      requirement_id: requirementId,
    });
  },

  /**
   * Reorder an existing member. `afterTraceLinkId` is the *membership link* of
   * the member it should follow; omitting it inserts the member first
   * (the service's `after_id is None` branch).
   */
  moveMember(
    groupId: UUID,
    requirementId: UUID,
    afterTraceLinkId?: UUID
  ): Promise<MoveMemberResult> {
    return apiClient.post<MoveMemberResult>(
      `/groups/${groupId}/members/move/`,
      {
        requirement_id: requirementId,
        ...(afterTraceLinkId ? { after_id: afterTraceLinkId } : {}),
      }
    );
  },
};

/**
 * Load every group of a workspace together with its ordered membership.
 *
 * One request per group: the committed REST surface has no bulk endpoint, and
 * the group count is expected to stay in the tens. Requests run in parallel.
 */
export async function loadGroupsWithMembers(
  workspaceId: UUID
): Promise<GroupWithMembers[]> {
  const groups = await groupsApi.list(workspaceId);
  return Promise.all(
    groups.map(async (group) => ({
      ...group,
      members: await groupsApi.members(group.id),
    }))
  );
}
