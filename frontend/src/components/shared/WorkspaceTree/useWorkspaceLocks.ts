/**
 * P4.4 — one batched lock read per tree mount.
 *
 * The requirement tree and the architecture tree each ask for *their* type
 * once (never once per row) and map the result onto `node.locked`. A failed
 * read degrades to "no locks": enforcement lives in the backend, so a missing
 * indicator must never break the tree or block an otherwise valid move.
 *
 * One plain effect rather than a React Query hook on purpose: `RequirementList`
 * is rendered by focused unit tests that mount it without a
 * `QueryClientProvider`, and a lock read is a tiny, fire-and-forget
 * enhancement — not shared cache state worth a provider dependency.
 */

import { useEffect, useState } from "react";
import { fetchLocks, type LockMap, type LockTargetType } from "../../../api/locks";

/**
 * @param workspaceId workspace whose locks are read; falsy = render unlocked
 * @param type        which id space the tree speaks (`requirement` | `architecture`)
 * @returns id → freezing workflow state name (empty on failure)
 */
export function useWorkspaceLocks(
  workspaceId: string | null | undefined,
  type: LockTargetType,
): LockMap {
  const [locks, setLocks] = useState<LockMap>({});

  useEffect(() => {
    if (!workspaceId) {
      setLocks({});
      return;
    }
    let cancelled = false;
    fetchLocks(workspaceId, type)
      .then((next) => {
        if (!cancelled) setLocks(next);
      })
      .catch(() => {
        // Degrade to "no locks" — the server remains the source of truth.
        if (!cancelled) setLocks({});
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId, type]);

  return locks;
}
