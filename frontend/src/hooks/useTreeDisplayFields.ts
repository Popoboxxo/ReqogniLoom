/**
 * Issue #1257 — the navigation tree's configurable field selection.
 *
 * The tree (`shared/WorkspaceTree`) used to render one fixed field combination
 * per artifact type. Since #1257 that combination is configurable on three
 * levels (global → workspace → personal, precedence
 * `user > workspace > global`) and per artifact type; the server resolves the
 * precedence (`GET …/tree-display-config/?resolve=effective&item_type=…`) and
 * this module is the synchronous, app-wide *read* surface for the result.
 *
 * Why a module-level store with `useSyncExternalStore` (the same shape
 * `hooks/useReadableIdsVisible` uses, and for the same reason): the selection is
 * read by *every* rendered tree row. A virtualized artifact list mounts
 * hundreds of rows; one `useState` per row would mean hundreds of subscribers
 * for one list. One store, one subscription per mounted tree, and a consistent
 * snapshot mid-render.
 *
 * Degradation is deliberate and never blocks a render:
 *   - an unconfigured item type (or a store that has not loaded yet) reads as
 *     :data:`DEFAULT_TREE_DISPLAY_FIELDS`, the pre-#1257 combination, so an
 *     existing user's tree looks exactly as it did;
 *   - a failed load leaves the default in place. A display preference is not
 *     worth breaking navigation over, and the settings surfaces — which *do*
 *     own loading/error state — are where a real failure is reported.
 *
 * The loader is opt-in and separate from the selector, so a component that only
 * *renders* fields (e.g. `ArtifactRow`) never triggers a network call:
 * `WorkspaceTree` owns that.
 */

import { useCallback, useEffect, useSyncExternalStore } from "react";

import { treeDisplayConfigApi } from "../api/tree-display-config";

/**
 * The pre-#1257 field combination, in its rendered order: readable id, V-model
 * level, workflow status, last-change timestamp and the version badge
 * (`<ArtifactRow>` shows it from v2 on, ch. 12.4 — dropping it here would
 * silently remove it from every artifact list). A configuration absent on every
 * level resolves to this (issue #1257 point 5).
 */
export const DEFAULT_TREE_DISPLAY_FIELDS: readonly string[] = [
  "uid",
  "level",
  "status",
  "updated_at",
  "version",
] as const;

/** Item types the settings editor offers, matching the backend artifact types. */
export const TREE_DISPLAY_ITEM_TYPES: readonly string[] = [
  "Requirement",
  "ArchitectureElement",
  "TestCase",
  "StakeholderNeed",
  "Adr",
  "Risk",
  "Issue",
] as const;

/** `{itemType: [key, …]}` — only item types with a *loaded* selection appear. */
let selections: Record<string, readonly string[]> = {};
const listeners = new Set<() => void>();
/** In-flight requests, so two mounted trees share one round trip. */
const inFlight = new Map<string, Promise<void>>();
/** Keys whose load attempt finished — success or not (never retry in a loop). */
const loadedKeys = new Set<string>();

function notify(): void {
  for (const listener of [...listeners]) listener();
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function cacheKey(itemType: string, workspaceId: string | null | undefined): string {
  return `${workspaceId ?? ""}\u0000${itemType}`;
}

/** Current selection for `itemType`, or the built-in default. */
export function getTreeDisplayFields(itemType?: string | null): readonly string[] {
  if (!itemType) return DEFAULT_TREE_DISPLAY_FIELDS;
  return selections[itemType] ?? DEFAULT_TREE_DISPLAY_FIELDS;
}

/**
 * Replace the cached selection for `itemType`.
 *
 * Called by the loader below and by the settings sections after a successful
 * save, so the tree in the same tab follows immediately (issue #1257: the
 * settings editor is the writer, the tree is the reader).
 */
export function setTreeDisplayFields(
  itemType: string,
  keys: readonly string[] | null
): void {
  const next = { ...selections };
  if (keys === null) {
    delete next[itemType];
  } else {
    next[itemType] = [...keys];
  }
  selections = next;
  notify();
}

/** Drop every cached selection — test helper and sign-out hygiene. */
export function resetTreeDisplayFields(): void {
  selections = {};
  inFlight.clear();
  loadedKeys.clear();
  notify();
}

/**
 * Load the resolved selection for `(itemType, workspace)` into the store.
 *
 * Idempotent per `(itemType, workspace)`: concurrent callers share one request,
 * and a resolved (or failed) key is not fetched again. Resolves to `void` and
 * never rejects — the store simply keeps the default (see module docstring).
 *
 * @param force  re-fetch even when the key is already cached (used by the
 *   settings sections after a save).
 */
export async function loadTreeDisplayFields(
  itemType: string,
  workspaceId?: string | null,
  options: { force?: boolean } = {}
): Promise<void> {
  const key = cacheKey(itemType, workspaceId);
  const pending = inFlight.get(key);
  if (pending) return pending;
  // `Set.has`, not `in`: a `Set` has no own properties, so `key in loadedKeys`
  // is always false and every call would re-request (caught by the
  // deduplication test in `useTreeDisplayFields.test.ts`).
  if (!options.force && loadedKeys.has(key)) return;

  const request = treeDisplayConfigApi
    .getEffective({ itemType, workspaceId: workspaceId ?? null })
    .then((payload) => {
      loadedKeys.add(key);
      setTreeDisplayFields(
        itemType,
        payload.fields.map((entry) => entry.key)
      );
    })
    .catch(() => {
      // Deliberate, documented degradation: keep the default and let the
      // settings surface (which owns error UI) report a real failure.
      loadedKeys.add(key);
      setTreeDisplayFields(itemType, null);
    })
    .finally(() => {
      inFlight.delete(key);
    });

  inFlight.set(key, request);
  return request;
}

/**
 * The ordered field keys the tree renders for `itemType`.
 *
 * `undefined` (the default) reads as :data:`DEFAULT_TREE_DISPLAY_FIELDS` and
 * never triggers a request, so a caller that does not know its item type
 * behaves exactly as before #1257.
 */
export function useTreeDisplayFields(itemType?: string | null): readonly string[] {
  const getSnapshot = useCallback(
    () => getTreeDisplayFields(itemType),
    [itemType]
  );
  const getServerSnapshot = useCallback(
    () => DEFAULT_TREE_DISPLAY_FIELDS,
    []
  );
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}

/**
 * Load `(itemType, workspace)`'s resolved selection once, on mount and whenever
 * either changes. Mounted by `WorkspaceTree` — the component that renders the
 * fields and therefore knows the item type.
 *
 * Both arguments are required for a load to happen. Without a workspace the
 * resolution cannot include the workspace level, and the *personal* route is not
 * a substitute: it would hide a workspace override behind the caller's own
 * selection. A tree that does not know its workspace therefore keeps the
 * built-in default rather than showing a different level's configuration.
 */
export function useTreeDisplayFieldsLoader(
  itemType?: string | null,
  workspaceId?: string | null
): void {
  useEffect(() => {
    if (!itemType || !workspaceId) return;
    void loadTreeDisplayFields(itemType, workspaceId);
  }, [itemType, workspaceId]);
}
