/**
 * ARCH-L1-001 ReactFrontend — requirement groups state (P6 Task 6.3).
 *
 * Owns the two things the requirement view needs from the group surface and
 * nothing else:
 *
 * - the workspace's groups with their ordered membership, loaded through the
 *   committed REST wrapper in `api/groups.ts`;
 * - the id translation the tree cannot do itself. The tree addresses nodes by
 *   **requirement entity id**, memberships arrive by **requirement artifact
 *   id**, and a move anchor is the **membership TraceLink id** — all three are
 *   resolved here, once, rather than at every call site.
 *
 * Deliberately plain `useEffect` state instead of React Query: `RequirementList`
 * and its focused unit tests render without a `QueryClientProvider`, and the
 * group panel is a small, single-workspace read. Mutations re-read the list
 * after they succeed, so membership order always matches the server's
 * `TraceLink.sort_key` instead of a client-side prediction.
 */

import { useCallback, useEffect, useMemo, useState } from "react";

import { extractApiErrorMessage } from "../../api/client";
import {
  groupsApi,
  loadGroupsWithMembers,
  type GroupWithMembers,
} from "../../api/groups";
import type { Requirement } from "../../types";
import type { WorkspaceTreeGroup } from "../shared/WorkspaceTree";

/** One member as the group manager renders it (name already resolved). */
export interface GroupManagerMember {
  requirementId: string;
  label: string;
  uid?: string | null;
}

/** One group as the group manager renders it. */
export interface GroupManagerGroup {
  id: string;
  title: string;
  description: string;
  members: GroupManagerMember[];
}

export interface UseRequirementGroupsResult {
  /** Groups with members, in server order (loading/queue order). */
  groups: GroupWithMembers[];
  /** Groups resolved into the tree's node-id space. */
  treeGroups: WorkspaceTreeGroup[];
  /** Groups with member names resolved, for the manager panel. */
  managerGroups: GroupManagerGroup[];
  isLoading: boolean;
  error: string | null;
  createGroup: (title: string, description?: string) => Promise<void>;
  addMember: (groupId: string, requirementId: string) => Promise<void>;
  removeMember: (groupId: string, requirementId: string) => Promise<void>;
  /**
   * Reorder a member. `afterRequirementId` uses the tree's move contract:
   * `undefined` appends, `null` inserts first, an id places the member behind
   * that requirement.
   */
  reorderMember: (
    groupId: string,
    requirementId: string,
    afterRequirementId?: string | null,
  ) => Promise<void>;
}

const NO_GROUPS: GroupWithMembers[] = [];

export function useRequirementGroups(
  workspaceId: string | null,
  requirements: readonly Requirement[],
): UseRequirementGroupsResult {
  const [groups, setGroups] = useState<GroupWithMembers[]>(NO_GROUPS);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    if (!workspaceId) {
      setGroups(NO_GROUPS);
      setIsLoading(false);
      setError(null);
      return;
    }
    let active = true;
    setIsLoading(true);
    setError(null);
    loadGroupsWithMembers(workspaceId)
      .then((loaded) => {
        if (!active) return;
        setGroups(loaded);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setGroups(NO_GROUPS);
        setError(extractApiErrorMessage(err));
      })
      .finally(() => {
        if (active) setIsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [workspaceId, reloadToken]);

  /** Re-read after a successful write so order/ids are the server's truth. */
  const reload = useCallback((): void => {
    setReloadToken((token) => token + 1);
  }, []);

  const artifactIdByRequirementId = useMemo(
    () =>
      new Map<string, string>(
        requirements
          .filter((req) => Boolean(req.artifact_id))
          .map((req) => [req.id, req.artifact_id as string]),
      ),
    [requirements]
  );

  const requirementById = useMemo(
    () => new Map<string, Requirement>(requirements.map((req) => [req.id, req])),
    [requirements]
  );

  const requirementIdByArtifactId = useMemo(() => {
    const map = new Map<string, string>();
    for (const [requirementId, artifactId] of artifactIdByRequirementId) {
      map.set(artifactId, requirementId);
    }
    return map;
  }, [artifactIdByRequirementId]);

  const treeGroups = useMemo(
    (): WorkspaceTreeGroup[] =>
      groups.map((group) => ({
        id: group.id,
        title: group.title,
        memberIds: group.members
          .map((member) =>
            requirementIdByArtifactId.get(member.requirement_artifact_id)
          )
          .filter((id): id is string => Boolean(id)),
      })),
    [groups, requirementIdByArtifactId]
  );

  const managerGroups = useMemo((): GroupManagerGroup[] => {
    return groups.map((group) => {
      const members: GroupManagerMember[] = [];
      for (const member of group.members) {
        const requirementId = requirementIdByArtifactId.get(
          member.requirement_artifact_id
        );
        if (!requirementId) continue;
        const requirement = requirementById.get(requirementId);
        members.push({
          requirementId,
          label: requirement?.title || requirementId,
          uid: requirement?.uid ?? null,
        });
      }
      return {
        id: group.id,
        title: group.title,
        description: group.description,
        members,
      };
    });
  }, [groups, requirementById, requirementIdByArtifactId]);

  const requireWorkspace = useCallback((): string => {
    if (!workspaceId) throw new Error("No active workspace");
    return workspaceId;
  }, [workspaceId]);

  const createGroup = useCallback(
    async (title: string, description = ""): Promise<void> => {
      await groupsApi.create(requireWorkspace(), title, description);
      reload();
    },
    [reload, requireWorkspace]
  );

  const addMember = useCallback(
    async (groupId: string, requirementId: string): Promise<void> => {
      await groupsApi.addMember(groupId, requirementId);
      reload();
    },
    [reload]
  );

  const removeMember = useCallback(
    async (groupId: string, requirementId: string): Promise<void> => {
      await groupsApi.removeMember(groupId, requirementId);
      reload();
    },
    [reload]
  );

  const reorderMember = useCallback(
    async (
      groupId: string,
      requirementId: string,
      afterRequirementId?: string | null
    ): Promise<void> => {
      const group = groups.find((candidate) => candidate.id === groupId);
      if (!group) throw new Error(`Group ${groupId} not found`);

      const movedArtifactId = artifactIdByRequirementId.get(requirementId);
      const linkIdOf = (targetRequirementId: string): string | undefined => {
        const artifactId = artifactIdByRequirementId.get(targetRequirementId);
        return group.members.find(
          (member) => member.requirement_artifact_id === artifactId
        )?.trace_link_id;
      };

      let afterTraceLinkId: string | undefined;
      if (afterRequirementId === undefined) {
        // Append: the API's "no after_id" branch inserts *first*, so the
        // anchor is the last remaining member's membership link.
        const others = group.members.filter(
          (member) => member.requirement_artifact_id !== movedArtifactId
        );
        afterTraceLinkId = others[others.length - 1]?.trace_link_id;
      } else if (afterRequirementId !== null) {
        afterTraceLinkId = linkIdOf(afterRequirementId);
      }

      await groupsApi.moveMember(groupId, requirementId, afterTraceLinkId);
      reload();
    },
    [artifactIdByRequirementId, groups, reload]
  );

  return {
    groups,
    treeGroups,
    managerGroups,
    isLoading,
    error,
    createGroup,
    addMember,
    removeMember,
    reorderMember,
  };
}
