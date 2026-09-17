/**
 * Hierarchy helpers shared by every parent-picking surface (REQ-003).
 *
 * A node may never become a child of itself or of one of its own descendants —
 * that closes a cycle, and a cycle makes the whole subtree unreachable from any
 * root (see `buildInternalTree`, which only treats nodes without a resolvable
 * parent as roots).
 *
 * The rule is structural, not artifact-specific, so both entry points that can
 * change a parent share this one implementation instead of keeping two copies
 * that can drift apart:
 *   - `ArchitectureForm`'s parent dropdown (filters these ids out of the
 *     options)
 *   - `WorkspaceTree`'s drag & drop (refuses these ids as drop targets)
 *
 * `collectAncestorIds` is the mirror walk (upwards instead of downwards) and
 * backs the two selection-visibility behaviours added for issues #668/#665.
 */

/** Minimal shape needed to walk a parent/child hierarchy. */
export interface HierarchyRef {
  id: string;
  parentId: string | null;
}

/**
 * Returns the ids that must not become *nodeId*'s new parent: the node itself
 * plus every transitive descendant of it.
 *
 * Terminates on already-corrupted data (a pre-existing cycle) because every id
 * enters the result set at most once.
 *
 * @param nodes - Flat hierarchy, in any order.
 * @param nodeId - The node about to be re-parented.
 * @returns Set of forbidden parent ids, always containing `nodeId`.
 */
export function collectSelfAndDescendantIds(
  nodes: readonly HierarchyRef[],
  nodeId: string,
): Set<string> {
  const childrenByParent = new Map<string, string[]>();
  for (const node of nodes) {
    if (!node.parentId) continue;
    const bucket = childrenByParent.get(node.parentId);
    if (bucket) bucket.push(node.id);
    else childrenByParent.set(node.parentId, [node.id]);
  }

  const forbidden = new Set<string>([nodeId]);
  const stack: string[] = [nodeId];
  while (stack.length > 0) {
    const current = stack.pop();
    if (current === undefined) break;
    for (const childId of childrenByParent.get(current) ?? []) {
      if (forbidden.has(childId)) continue;
      forbidden.add(childId);
      stack.push(childId);
    }
  }
  return forbidden;
}

/**
 * Returns every transitive ancestor of *nodeId*, nearest parent first.
 *
 * Used for the two "the selection must stay findable" behaviours in
 * `WorkspaceTree`:
 *   - issue #665: expanding this chain reveals a node that was selected from
 *     outside the tree (global search hit, deep link, trace-spine jump),
 *   - issue #668: a *collapsed* member of this chain is the row that hides the
 *     current selection and therefore carries the "contains selection" marker.
 *
 * `nodeId` itself is never included — a node is not its own ancestor, and both
 * call sites need to distinguish "is the selection" from "holds the selection".
 * Ids with no matching entry in `nodes` (dangling `parentId`, node not loaded
 * yet) end the walk, and a pre-existing cycle terminates it because every id is
 * visited at most once.
 *
 * @param nodes - Flat hierarchy, in any order.
 * @param nodeId - The node whose ancestors are wanted.
 * @returns Ancestor ids ordered from the direct parent up to the root.
 */
export function collectAncestorIds(
  nodes: readonly HierarchyRef[],
  nodeId: string,
): string[] {
  const parentById = new Map<string, string | null>();
  for (const node of nodes) parentById.set(node.id, node.parentId ?? null);

  const ancestors: string[] = [];
  const seen = new Set<string>([nodeId]);
  let cursor = parentById.get(nodeId) ?? null;
  while (cursor !== null && parentById.has(cursor) && !seen.has(cursor)) {
    seen.add(cursor);
    ancestors.push(cursor);
    cursor = parentById.get(cursor) ?? null;
  }
  return ancestors;
}
