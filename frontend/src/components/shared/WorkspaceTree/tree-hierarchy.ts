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
