/**
 * WorkspaceTree — configured display-field selection (FE-01 extraction,
 * issue #1257).
 *
 * The loader and the synchronous per-field gate used by the tree's default row
 * were inlined in `workspace-tree.tsx`. They are extracted here so the tree
 * only says *which* fields it renders while the resolution details (one load
 * per `(itemType, workspace)`, default fallback, per-row gate) live in one
 * place.
 *
 * This is the *array* side of the field selection: the tree that renders the
 * fields resolves them from the store. The `Set`-based publication to
 * caller-supplied row renderers (`<ArtifactRow>`) stays in
 * `tree-display-fields-context.tsx` — that module's `isTreeFieldVisible` has a
 * different contract (`null` means "no provider, everything visible") and is
 * therefore intentionally not re-implemented here.
 */

import { useCallback } from 'react';
import {
  useTreeDisplayFields,
  useTreeDisplayFieldsLoader,
} from '../../../hooks/useTreeDisplayFields';

export interface TreeDisplayFieldsSelection {
  /** The ordered field keys this tree renders. */
  displayFields: readonly string[];
  /** Whether `key` is part of the selection — the per-field gate. */
  showsField: (key: string) => boolean;
}

/**
 * Pure per-field gate over a resolved selection.
 *
 * Mirrors the store's own semantics: an unconfigured type resolves to
 * `DEFAULT_TREE_DISPLAY_FIELDS`, so the caller never sees an empty list here.
 */
export function treeShowsField(fields: readonly string[], key: string): boolean {
  return fields.includes(key);
}

/**
 * Loads the configured selection for `(itemType, workspace)` and returns it
 * together with the per-field gate.
 *
 * Both arguments are required for a load: without a workspace the resolution
 * cannot include the workspace level, and the personal route is not a
 * substitute (see `hooks/useTreeDisplayFields`). A tree that does not know its
 * workspace keeps the built-in default rather than showing another level's
 * configuration.
 */
export function useTreeDisplayFieldsSelection(
  itemType?: string | null,
  workspaceId?: string | null,
): TreeDisplayFieldsSelection {
  useTreeDisplayFieldsLoader(itemType, workspaceId ?? null);
  const displayFields = useTreeDisplayFields(itemType);
  // FE-07: `displayFields` is a tiny, referentially stable store value, so a
  // plain `includes` lookup replaces the premature `new Set(...)` memo without
  // tripping react-hooks/exhaustive-deps over a per-render Set.
  const showsField = useCallback(
    (key: string): boolean => treeShowsField(displayFields, key),
    [displayFields],
  );
  return { displayFields, showsField };
}
