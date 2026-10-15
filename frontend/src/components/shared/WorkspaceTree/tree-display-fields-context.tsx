/**
 * Issue #1257 — which tree fields the current tree actually renders.
 *
 * `WorkspaceTree` resolves the configured field selection for its artifact type
 * (three-level, `user > workspace > global`) and publishes it here, so a row
 * renderer the *caller* supplies — chiefly `shared/ArtifactRow` — hides exactly
 * the same fields the tree's own default row does, without every list passing
 * the selection through by hand.
 *
 * The provider is deliberately optional:
 *
 *   - **no provider** (an `<ArtifactRow>` used outside a tree, e.g. a flat list,
 *     or a unit test) reads as `null`, and `isTreeFieldVisible` then returns
 *     `true` for every field — i.e. exactly the pre-#1257 rendering;
 *   - **with a provider**, a field missing from the set is not rendered.
 *
 * Keeping the fallback "everything visible" rather than "nothing visible" is
 * what makes this additive: an unconfigured artifact type resolves to
 * `DEFAULT_TREE_DISPLAY_FIELDS`, which contains the four fields the tree
 * rendered before #1257, so nothing an existing user sees changes.
 */

import { createContext, useContext, useMemo, type ReactNode } from "react";

/** The resolved, ordered field keys a tree renders. */
const TreeDisplayFieldsContext = createContext<ReadonlySet<string> | null>(null);

export interface TreeDisplayFieldsProviderProps {
  /** The resolved field keys (see `hooks/useTreeDisplayFields`). */
  fields: readonly string[];
  children: ReactNode;
}

/** Publishes `fields` to every row rendered inside. */
export function TreeDisplayFieldsProvider({
  fields,
  children,
}: TreeDisplayFieldsProviderProps): JSX.Element {
  // A `Set` rather than the array: a virtualized tree asks once per row per
  // field, so the lookup has to stay O(1) and the value referentially stable
  // (the array is a fresh value on every store notification).
  const visible = useMemo(() => new Set(fields), [fields]);
  return (
    <TreeDisplayFieldsContext.Provider value={visible}>
      {children}
    </TreeDisplayFieldsContext.Provider>
  );
}

/**
 * The enclosing tree's visible field keys, or `null` when there is no tree.
 *
 * `null` means "not inside a configured tree" and must be read through
 * :func:`isTreeFieldVisible` rather than truthiness-checked, so the
 * no-provider case stays "everything visible".
 */
export function useTreeDisplayFieldsContext(): ReadonlySet<string> | null {
  return useContext(TreeDisplayFieldsContext);
}

/**
 * Whether `key` should be rendered.
 *
 * @param visible the enclosing tree's selection, or `null` outside a tree.
 * @param key     the field key (`uid`, `level`, `status`, `updated_at`, …).
 */
export function isTreeFieldVisible(
  visible: ReadonlySet<string> | null,
  key: string
): boolean {
  if (visible === null) return true;
  return visible.has(key);
}

/** Convenience hook: `isTreeFieldVisible` bound to the enclosing tree. */
export function useTreeFieldVisibility(): (key: string) => boolean {
  const visible = useTreeDisplayFieldsContext();
  return useMemo(() => (key: string) => isTreeFieldVisible(visible, key), [visible]);
}
