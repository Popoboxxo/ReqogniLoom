/**
 * WorkspaceTree — shared compact tree navigation (REQ-003).
 *
 * Export surface for all views that use the unified tree module.
 */
export { WorkspaceTree, getTypeBadgeAbbreviation } from './workspace-tree';
export type {
  WorkspaceTreeNode,
  WorkspaceTreeNodeType,
  WorkspaceTreeProps,
} from './workspace-tree';
export {
  artifactNodeId,
  buildGroupNodes,
  groupFolderNodeId,
  groupMemberNodeId,
  isGroupFolderNode,
  isGroupMember,
  isGroupMemberNode,
} from './tree-groups';
export type { GroupMembershipRef, WorkspaceTreeGroup } from './tree-groups';
export { classifyTreeDrop } from './tree-drag';
export type { TreeDropNode, TreeDropPlan } from './tree-drag';
export { collectSelfAndDescendantIds } from './tree-hierarchy';
export type { HierarchyRef } from './tree-hierarchy';
