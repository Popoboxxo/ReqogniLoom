/**
 * WorkspaceTree — sibling reordering (P1 Task 1.7).
 *
 * The tree owns expand/collapse and reports moves; the persisted order lives on
 * `Artifact.sort_key` and is written through one endpoint
 * (`POST /api/v1/artifacts/{id}/move/`). This module is the pure part between
 * the two: it turns a drop target into the API's `(parent_id, after_id)` triple
 * and predicts the resulting sibling order for the optimistic update.
 *
 * Three cases encode the move contract (spec B8):
 *   - `afterId === undefined` → append at the end of the target parent,
 *   - `afterId === null`      → insert as the first child,
 *   - `afterId === '<id>'`    → insert directly behind that sibling.
 *
 * Kept free of React so the drag controller, the keyboard path and the "Move…"
 * dialog share one implementation, and so the rules are unit-testable without
 * a DOM.
 */

import { collectSelfAndDescendantIds, type HierarchyRef } from './tree-hierarchy';

/** Where the pointer sits on a row while dragging: above, below or on it. */
export type TreeDropPosition = 'before' | 'after' | 'inside';

/** One resolved move, in the API's terms. */
export interface TreeReorderTarget {
  /** New container; `null` means "top level". */
  newParentId: string | null;
  /** `undefined` appends, `null` inserts first, an id inserts behind it. */
  afterId: string | null | undefined;
}

/** Direction of one keyboard step inside the current sibling block. */
export type TreeStepDirection = 'up' | 'down';

/**
 * Ids of the children of *parentId*, in the order the tree renders them.
 *
 * The flat node array is the render order (`buildInternalTree` buckets it by
 * parent without re-sorting), so the filtered sequence *is* the visible order.
 */
export function orderedSiblingIds(
  nodes: readonly HierarchyRef[],
  parentId: string | null,
): string[] {
  return nodes
    .filter((node) => (node.parentId ?? null) === parentId)
    .map((node) => node.id);
}

/**
 * Translates "dropped *position* on *targetId*" into the API's
 * `(parent_id, after_id)` pair.
 *
 * `inside` makes the target the new parent and appends; `before`/`after` keep
 * the target's parent and place the dragged node next to the target, with
 * `afterId = null` when the target is the first sibling (`before`) — that is
 * the only way to express "insert first".
 *
 * @returns `null` when the target is the dragged node itself or is unknown.
 */
export function resolveDropTarget(
  nodes: readonly HierarchyRef[],
  draggedId: string,
  targetId: string,
  position: TreeDropPosition,
): TreeReorderTarget | null {
  if (draggedId === targetId) return null;
  if (position === 'inside') {
    return { newParentId: targetId, afterId: undefined };
  }

  const target = nodes.find((node) => node.id === targetId);
  if (!target) return null;

  const newParentId = target.parentId ?? null;
  if (position === 'after') {
    return { newParentId, afterId: targetId };
  }

  const siblings = orderedSiblingIds(nodes, newParentId);
  const index = siblings.indexOf(targetId);
  if (index === -1) return null;
  return { newParentId, afterId: index === 0 ? null : siblings[index - 1] };
}

/**
 * One-step keyboard move inside the current sibling block (Alt+↑ / Alt+↓).
 *
 * `up` inserts before the previous sibling, which is `null` (first) when that
 * sibling is the block's first entry; `down` inserts behind the next one. Both
 * return `null` at the block's edge, where the move would be a no-op.
 */
export function resolveStepTarget(
  nodes: readonly HierarchyRef[],
  nodeId: string,
  direction: TreeStepDirection,
): TreeReorderTarget | null {
  const node = nodes.find((candidate) => candidate.id === nodeId);
  if (!node) return null;

  const parentId = node.parentId ?? null;
  const siblings = orderedSiblingIds(nodes, parentId);
  const index = siblings.indexOf(nodeId);
  if (index === -1) return null;

  if (direction === 'up') {
    if (index === 0) return null;
    return {
      newParentId: parentId,
      afterId: index === 1 ? null : siblings[index - 2],
    };
  }

  if (index === siblings.length - 1) return null;
  return { newParentId: parentId, afterId: siblings[index + 1] };
}

/**
 * Predicts the node list after the move, for the optimistic update.
 *
 * Only the moved node's `parentId` and its position among its new siblings
 * change; every other node keeps its relative order. Returns `null` when the
 * move is a no-op (same parent, same position) or impossible (the new parent is
 * the node itself or one of its descendants — a cycle would make the subtree
 * unreachable from any root).
 */
export function predictReorder<T extends HierarchyRef>(
  nodes: readonly T[],
  nodeId: string,
  newParentId: string | null,
  afterId: string | null | undefined,
): T[] | null {
  const moved = nodes.find((node) => node.id === nodeId);
  if (!moved) return null;

  if (
    newParentId !== null &&
    collectSelfAndDescendantIds(nodes, nodeId).has(newParentId)
  ) {
    return null;
  }

  const currentParentId = moved.parentId ?? null;
  const currentSiblings = orderedSiblingIds(nodes, currentParentId);
  const targetSiblings = orderedSiblingIds(nodes, newParentId).filter(
    (id) => id !== nodeId,
  );

  if (afterId !== null && afterId !== undefined && !targetSiblings.includes(afterId)) {
    return null;
  }

  if (afterId === undefined && targetSiblings.length === 0) {
    // The new parent has no other children: no anchor exists, so the move is
    // only meaningful if the parent actually changes.
    if (currentParentId === newParentId) return null;
    return rebuild(nodes, moved, newParentId, null);
  }

  const afterSiblingId: string | null =
    afterId === undefined
      ? (targetSiblings[targetSiblings.length - 1] ?? null)
      : afterId;

  if (
    currentParentId === newParentId &&
    isSamePosition(currentSiblings, nodeId, afterSiblingId)
  ) {
    return null;
  }

  return rebuild(nodes, moved, newParentId, afterSiblingId);
}

/** True when *nodeId* already sits directly behind *afterSiblingId*. */
function isSamePosition(
  siblings: readonly string[],
  nodeId: string,
  afterSiblingId: string | null,
): boolean {
  const index = siblings.indexOf(nodeId);
  if (index === -1) return false;
  if (index === 0) return afterSiblingId === null;
  return siblings[index - 1] === afterSiblingId;
}

/**
 * Rebuilds the flat list with the moved node re-parented and placed behind
 * *afterSiblingId* (`null` = first child of the new parent).
 */
function rebuild<T extends HierarchyRef>(
  nodes: readonly T[],
  moved: T,
  newParentId: string | null,
  afterSiblingId: string | null,
): T[] {
  const others = nodes.filter((node) => node.id !== moved.id);

  let insertIndex = others.length;
  if (afterSiblingId === null) {
    const firstSibling = others.find(
      (node) => (node.parentId ?? null) === newParentId,
    );
    if (firstSibling) insertIndex = others.indexOf(firstSibling);
  } else {
    const anchor = others.find((node) => node.id === afterSiblingId);
    if (anchor) insertIndex = others.indexOf(anchor) + 1;
  }

  const next = [...others];
  next.splice(insertIndex, 0, { ...moved, parentId: newParentId });
  return next;
}
