/**
 * Issue #1263 — the create dialog's configurable form definition.
 *
 * The shared `ArtifactForm` renders its fields from the resolved attribute
 * definition. Since #1263 that rendering is overlaid by a *form definition*
 * (which fields are visible, their order, requiredness and default), resolvable
 * on three levels with precedence `user > workspace > global` and per artifact
 * type. The server resolves the precedence
 * (`GET …/create-form-config/?resolve=effective&item_type=…`) — this hook is the
 * read surface, so the client never re-implements it.
 *
 * Degradation is deliberate and never blocks the dialog: when the request fails,
 * the item type is unknown, or no workspace is active, `entries` stays `null`
 * and the caller renders the plain attribute definition — which is exactly the
 * pre-#1263 behaviour.
 */

import { useEffect, useRef, useState } from "react";

import {
  createFormConfigApi,
  type CreateFormFieldEntry,
} from "../api/create-form-config";
import { useActiveWorkspace } from "./useActiveWorkspace";

/**
 * Item types the create-form editor offers, matching the backend artifact
 * types (same list the #1257 tree-display editor uses).
 */
export const CREATE_FORM_ITEM_TYPES: readonly string[] = [
  "Requirement",
  "ArchitectureElement",
  "TestCase",
  "StakeholderNeed",
  "Adr",
  "Risk",
  "Issue",
] as const;

export interface UseCreateFormFieldsResult {
  /** Resolved entries, or `null` when nothing could be resolved. */
  entries: CreateFormFieldEntry[] | null;
  loading: boolean;
}

/**
 * Overlay a level's *stored* entries onto the definition-derived *base*.
 *
 * Mirrors the backend's ``merge_create_form_entries``: a base field with no
 * stored entry keeps its base entry; a stored entry overrides
 * visible/required/order/default. Used by the editor's live preview so the
 * effect of an (optimistic) edit is immediate, without a second round trip.
 */
export function mergeCreateFormEntries(
  base: readonly CreateFormFieldEntry[],
  stored: readonly CreateFormFieldEntry[] | null
): CreateFormFieldEntry[] {
  if (!stored) return [...base];
  const resolved = new Map(base.map((entry) => [entry.field_key, { ...entry }]));
  for (const raw of stored) {
    const entry = resolved.get(raw.field_key);
    if (!entry) continue;
    entry.visible = raw.visible;
    entry.required = raw.required;
    entry.order = raw.order;
    entry.default = raw.default;
  }
  return [...resolved.values()].sort(
    (a, b) => a.order - b.order || a.field_key.localeCompare(b.field_key)
  );
}

/**
 * Load the effective form definition for `(activeWorkspace, itemType)`.
 *
 * `enabled` is false for the edit path (the form definition governs the *create*
 * dialog only), so a mounted detail editor never issues the request.
 *
 * Disabling does NOT discard an already-resolved definition: it is retained for
 * as long as the `(workspace, itemType)` subject is unchanged, so re-opening a
 * create dialog renders the full contract immediately instead of flashing
 * contract-less until the refetch lands (see the `loadedKeyRef` note below).
 */
export function useCreateFormFields(
  itemType: string,
  enabled: boolean
): UseCreateFormFieldsResult {
  // No provider means "no workspace to resolve against" — the documented
  // `entries === null` degradation, not a crash (see useActiveWorkspace).
  const activeWorkspace = useActiveWorkspace();
  const [entries, setEntries] = useState<CreateFormFieldEntry[] | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const workspaceId = activeWorkspace?.id;
  // Which (workspace, itemType) pair the current `entries` belong to. The
  // create dialogs stay mounted while closed and pass `enabled: false` then,
  // so nulling on every disable made every RE-OPEN start without the form
  // definition — and because the form definition outranks the attribute
  // definition in `useFieldContract`, a field required *only* by the form
  // definition lost its marker until the refetch resolved (N2, the remaining
  // half of the #1393 review's F3). Same retention pattern as
  // `useArtifactDefinition`'s `loadedKeyRef`: only a real subject change
  // invalidates the resolved entries.
  const loadedKeyRef = useRef<string | null>(null);
  const key = `${workspaceId ?? ""}:${itemType}`;

  useEffect(() => {
    // GitHub #1393 review (M3): the guard must include the workspace, otherwise
    // a `null` workspace still issues `getEffective({ workspaceId: null })` —
    // the contradiction with the docstring's "no workspace ⇒ entries stays
    // null". Matches `useArtifactDefinition`'s own guard.
    if (!itemType || !workspaceId) {
      loadedKeyRef.current = null;
      setEntries(null);
      setLoading(false);
      return undefined;
    }
    if (loadedKeyRef.current !== key) {
      // A different subject: the previous form definition does not describe it.
      loadedKeyRef.current = null;
      setEntries(null);
    }
    if (!enabled) {
      // Keep the last known form definition for this subject — see above.
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    createFormConfigApi
      .getEffective({ itemType, workspaceId })
      .then((payload) => {
        if (cancelled) return;
        // Defensive: a degraded/partial payload keeps the documented `null`
        // state instead of handing a non-array to every consumer.
        loadedKeyRef.current = key;
        setEntries(Array.isArray(payload?.fields) ? payload.fields : null);
        setLoading(false);
      })
      .catch(() => {
        // Documented degradation: keep the attribute definition's own rendering.
        if (cancelled) return;
        setEntries(null);
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [enabled, itemType, workspaceId, key]);

  return { entries, loading };
}
