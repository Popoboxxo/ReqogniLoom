import { useEffect, useRef, useState } from "react";

import {
  attributeDefinitionsApi,
  type AttributeItemType,
  type ResolvedAttributeDefinition,
} from "../../../api/attribute-definitions";
import { extractErrorMessage } from "../../../api/client";
import { useActiveWorkspace } from "../../../hooks/useActiveWorkspace";

export interface UseArtifactDefinitionResult {
  definition: ResolvedAttributeDefinition | null;
  loading: boolean;
  error: string | null;
}

export interface UseArtifactDefinitionOptions {
  /**
   * Fetch only while true (default: always).
   *
   * The create dialogs stay mounted while closed, so a route-level
   * `useFieldContract` would otherwise request a definition the user may never
   * open — `hooks/useFieldContract.ts` passes the dialog's own open state.
   */
  enabled?: boolean;
}

/**
 * Loads the resolved attribute definition for `(activeWorkspace, itemType)`.
 *
 * The backend already caches the resolution per workspace, so this hook does no
 * client-side memoisation of its own — one indexed read per mounted form is
 * cheaper than a cache that has to be invalidated when an admin edits the
 * definition in another tab.
 *
 * With no active workspace there is nothing to resolve against, so the hook
 * settles into `{ definition: null, loading: false, error: null }` and the
 * caller renders its load-error branch rather than spinning forever. The same
 * holds for a `null` item type: item types outside the attribute catalogue
 * (`Diagram` is not an `ITEM_TYPES` member) have no definition to load.
 */
export function useArtifactDefinition(
  itemType: AttributeItemType | null,
  options: UseArtifactDefinitionOptions = {}
): UseArtifactDefinitionResult {
  const { enabled = true } = options;
  const activeWorkspace = useActiveWorkspace();
  const [definition, setDefinition] = useState<ResolvedAttributeDefinition | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const workspaceId = activeWorkspace?.id;
  // Which (workspace, itemType) pair the current `definition` belongs to.
  // GitHub #1393/#1392 follow-up: the create dialogs stay mounted while closed
  // and pass `enabled: false` then, so nulling the definition on every disable
  // made every RE-OPEN start contract-less — no marker, no `maxLength` — until
  // the request resolved, i.e. the #1392 window ("400 chars into a 200 field")
  // re-opened on every open. Only an actual subject change invalidates it.
  const loadedKeyRef = useRef<string | null>(null);
  const key = `${workspaceId ?? ""}:${itemType ?? ""}`;

  useEffect(() => {
    let cancelled = false;
    if (!workspaceId || !itemType) {
      loadedKeyRef.current = null;
      setDefinition(null);
      setLoading(false);
      setError(null);
      return undefined;
    }
    if (loadedKeyRef.current !== key) {
      // A different subject: the previous contract does not describe it.
      loadedKeyRef.current = null;
      setDefinition(null);
      setError(null);
    }
    if (!enabled) {
      // Keep the last known contract for this subject — see above.
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    setError(null);
    attributeDefinitionsApi
      .getWorkspace(workspaceId, itemType)
      .then((resolved) => {
        if (cancelled) return;
        loadedKeyRef.current = key;
        setDefinition(resolved);
        setLoading(false);
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        setDefinition(null);
        setError(extractErrorMessage(exc));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, itemType, enabled, key]);

  return { definition, loading, error };
}
