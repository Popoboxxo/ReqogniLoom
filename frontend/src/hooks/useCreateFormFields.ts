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

import { useEffect, useState } from "react";

import {
  createFormConfigApi,
  type CreateFormFieldEntry,
} from "../api/create-form-config";
import { useWorkspace } from "../context/WorkspaceContext";

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
 */
export function useCreateFormFields(
  itemType: string,
  enabled: boolean
): UseCreateFormFieldsResult {
  const { activeWorkspace } = useWorkspace();
  const [entries, setEntries] = useState<CreateFormFieldEntry[] | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const workspaceId = activeWorkspace?.id;

  useEffect(() => {
    if (!enabled || !itemType) {
      setEntries(null);
      setLoading(false);
      return undefined;
    }
    let cancelled = false;
    setLoading(true);
    createFormConfigApi
      .getEffective({ itemType, workspaceId: workspaceId ?? null })
      .then((payload) => {
        if (cancelled) return;
        setEntries(payload.fields);
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
  }, [enabled, itemType, workspaceId]);

  return { entries, loading };
}
