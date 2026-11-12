/**
 * ARCH-L1-001 ReactFrontend — actor candidates for the picker (#598 S2).
 *
 * Extracted from `ActorPicker.tsx`: the workspace actor list and its own
 * loading/error lifecycle. The combobox state (query, open, active index) stays
 * with the picker, because it is interaction state, not data.
 *
 * Degradation kept verbatim: without a workspace the list is empty and not
 * loading; a failed request leaves an empty list and its message so the picker
 * can still allow free-text actors.
 */

import { useEffect, useState } from "react";

import { actorsApi, type ActorCandidate } from "../../../../api/actors";
import { extractErrorMessage } from "../../../../api/client";

export interface UseActorCandidatesResult {
  candidates: ActorCandidate[];
  loading: boolean;
  loadError: string | null;
}

export function useActorCandidates(
  workspaceId: string | undefined
): UseActorCandidatesResult {
  const [candidates, setCandidates] = useState<ActorCandidate[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    if (!workspaceId) {
      setCandidates([]);
      setLoading(false);
      return undefined;
    }
    setLoading(true);
    setLoadError(null);
    actorsApi
      .list(workspaceId)
      .then((resolved) => {
        if (cancelled) return;
        setCandidates(resolved);
        setLoading(false);
      })
      .catch((exc: unknown) => {
        if (cancelled) return;
        setCandidates([]);
        setLoadError(extractErrorMessage(exc));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  return { candidates, loading, loadError };
}
