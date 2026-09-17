import { useEffect, useState } from "react";

import {
  attributeDefinitionsApi,
  type AttributeItemType,
  type ResolvedAttributeDefinition,
} from "../../../api/attribute-definitions";
import { extractErrorMessage } from "../../../api/client";
import { useWorkspace } from "../../../context/WorkspaceContext";

export interface UseArtifactDefinitionResult {
  definition: ResolvedAttributeDefinition | null;
  loading: boolean;
  error: string | null;
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
 * caller renders its load-error branch rather than spinning forever.
 */
export function useArtifactDefinition(
  itemType: AttributeItemType
): UseArtifactDefinitionResult {
  const { activeWorkspace } = useWorkspace();
  const [definition, setDefinition] = useState<ResolvedAttributeDefinition | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const workspaceId = activeWorkspace?.id;

  useEffect(() => {
    let cancelled = false;
    if (!workspaceId) {
      setDefinition(null);
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    setError(null);
    attributeDefinitionsApi
      .getWorkspace(workspaceId, itemType)
      .then((resolved) => {
        if (cancelled) return;
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
  }, [workspaceId, itemType]);

  return { definition, loading, error };
}
