/**
 * ARCH-L1-001 ReactFrontend — workspace memory digest (#598 S2, RFC #1002 F6).
 *
 * Extracted from `MemoryPage.tsx`: the on-demand digest is independent of the
 * list, the filters, the search and the per-entry actions.
 *
 * Contract kept verbatim:
 *   - loaded on demand only ("load/refresh"), never on mount, so visiting the
 *     page stays a single list request,
 *   - dropped when the workspace changes — a digest is workspace-bound and must
 *     never leak across tenants,
 *   - a failure clears the digest and keeps its own error state.
 */

import { useCallback, useEffect, useState } from "react";
import type { TFunction } from "i18next";

import { memoryApi, type MemoryDigest } from "../../api/memory";
import { formatMemoryErrorMessage } from "./memory-format";

export interface UseMemoryDigestResult {
  digest: MemoryDigest | null;
  isDigestLoading: boolean;
  digestError: string | null;
  loadDigest: () => void;
}

export function useMemoryDigest(
  workspaceId: string | undefined,
  t: TFunction
): UseMemoryDigestResult {
  const [digest, setDigest] = useState<MemoryDigest | null>(null);
  const [isDigestLoading, setIsDigestLoading] = useState(false);
  const [digestError, setDigestError] = useState<string | null>(null);

  useEffect(() => {
    setDigest(null);
    setDigestError(null);
  }, [workspaceId]);

  const loadDigest = useCallback((): void => {
    if (!workspaceId) return;
    setIsDigestLoading(true);
    setDigestError(null);
    memoryApi
      .getWorkspaceDigest(workspaceId)
      .then((result) => setDigest(result))
      .catch((err: unknown) => {
        setDigest(null);
        setDigestError(
          formatMemoryErrorMessage(
            err,
            t("memory.digest.error", "Digest konnte nicht geladen werden.")
          )
        );
      })
      .finally(() => setIsDigestLoading(false));
  }, [workspaceId, t]);

  return { digest, isDigestLoading, digestError, loadDigest };
}
