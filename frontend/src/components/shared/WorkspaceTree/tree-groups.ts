/**
 * WorkspaceTree — visual groups as pseudo-folders (P6 Task 6.3).
 *
 * A group is not part of the requirement hierarchy: it is a second, visual
 * ordering of the same requirements (a requirement may even sit in several
 * groups). The tree therefore renders each group as a synthetic folder row
 * whose children are *clones* of the requirement nodes:
 *
 * - the folder row is a plain `WorkspaceTreeNode` flagged with `isGroupFolder`,
 *   so `buildInternalTree` can bucket its children like any other parent;
 * - a clone keeps the original node's presentation fields but gets a unique
 *   id (`__group__:<groupId>::<nodeId>`) and records the underlying node in
 *   `sourceNodeId`. The unique id is what lets the same requirement appear
 *   under two folders at once without one row shadowing the other.
 *
 * The plain (non-group) tree is returned unchanged: `buildGroupNodes` is only
 * called while the "Gruppen anzeigen" toggle is on, so switching it off is
 * byte-for-byte the previous render.
 *
 * Requirements that belong to no group keep their plain hierarchy below the
 * folders, so turning the toggle on never hides an artifact.
 */

import type { WorkspaceTreeNode } from './workspace-tree';

/** Prefix of a synthetic folder row id. Node ids come from the API, so a
 * reserved non-UUID prefix cannot collide with one. */
export const GROUP_FOLDER_PREFIX = '__group__:';

/** Separates the folder id from the member's node id in a clone id. */
const GROUP_MEMBER_SEPARATOR = '::';

/** One group, already resolved to tree node ids by the caller. */
export interface WorkspaceTreeGroup {
  id: string;
  title: string;
  /** Member node ids in the group's own order (`sort_key` on the link). */
  memberIds: string[];
}

/** Synthetic row id of the group's folder. */
export function groupFolderNodeId(groupId: string): string {
  return `${GROUP_FOLDER_PREFIX}${groupId}`;
}

/** Synthetic row id of one member clone inside a group folder. */
export function groupMemberNodeId(groupId: string, nodeId: string): string {
  return `${groupFolderNodeId(groupId)}${GROUP_MEMBER_SEPARATOR}${nodeId}`;
}

/** True for the synthetic folder row itself (not for its member clones). */
export function isGroupFolderNode(node: WorkspaceTreeNode): boolean {
  return node.isGroupFolder === true;
}

/** True for a member clone inside a group folder. */
export function isGroupMemberNode(node: WorkspaceTreeNode): boolean {
  return Boolean(node.groupId && node.sourceNodeId);
}

/**
 * The node id the artifact actually has — the underlying id for a clone, the
 * node's own id otherwise. Selection, the row click and `renderRow` hydration
 * all address the artifact in this id space.
 */
export function artifactNodeId(node: WorkspaceTreeNode): string {
  return node.sourceNodeId ?? node.id;
}

/**
 * Build the group view: one collapsible folder per group (in group order),
 * its members in membership order, followed by every requirement that is in no
 * group (plain hierarchy preserved).
 *
 * Member ids that are not part of `nodes` are ignored: the caller hands over
 * the *filtered* list, and a search/filter must behave exactly like it does in
 * the plain tree instead of resurrecting hidden rows.
 */
export function buildGroupNodes(
  nodes: readonly WorkspaceTreeNode[],
  groups: readonly WorkspaceTreeGroup[],
): WorkspaceTreeNode[] {
  const byId = new Map<string, WorkspaceTreeNode>();
  for (const node of nodes) byId.set(node.id, node);

  // How many groups each requirement really belongs to — including members
  // the current filter hides, so the "in N groups" marker does not change
  // meaning while a search is active.
  const membershipCount = new Map<string, number>();
  for (const group of groups) {
    for (const nodeId of new Set(group.memberIds)) {
      if (!byId.has(nodeId)) continue;
      membershipCount.set(nodeId, (membershipCount.get(nodeId) ?? 0) + 1);
    }
  }

  const result: WorkspaceTreeNode[] = [];
  for (const group of groups) {
    const folderId = groupFolderNodeId(group.id);
    const memberIds = [...new Set(group.memberIds)].filter((id) => byId.has(id));

    result.push({
      id: folderId,
      name: group.title,
      parentId: null,
      isGroupFolder: true,
      groupId: group.id,
      groupMemberCount: memberIds.length,
    });

    for (const memberId of memberIds) {
      const base = byId.get(memberId);
      if (!base) continue;
      result.push({
        ...base,
        id: groupMemberNodeId(group.id, memberId),
        parentId: folderId,
        groupId: group.id,
        sourceNodeId: memberId,
        groupCount: membershipCount.get(memberId) ?? 1,
      });
    }
  }

  for (const node of nodes) {
    if (membershipCount.has(node.id)) continue;
    result.push(node);
  }

  return result;
}

/**
 * Map a reorder target expressed in clone ids back into the group's member id
 * space. `afterId` keeps its three-way meaning (`undefined` = append, `null` =
 * insert first, id = follow that member).
 */
export function resolveGroupReorderAfterId(
  nodes: readonly WorkspaceTreeNode[],
  afterId: string | null | undefined,
): string | null | undefined {
  if (afterId === null || afterId === undefined) return afterId;
  const anchor = nodes.find((node) => node.id === afterId);
  return anchor ? artifactNodeId(anchor) : null;
}
