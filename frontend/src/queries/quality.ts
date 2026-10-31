/**
 * ARCH-L1-001 ReactFrontend — quality assessment hooks (Plan B / B5-T5).
 *
 * Both the header badge and the expanded panel read through the SAME
 * `useQualityHistory` query key, and `useAssessQuality` invalidates that key on
 * success — so a run started in the panel updates the badge straight from the
 * shared cache. There is deliberately no effect-based, provider-less
 * controller and no `onAssessed` callback: the cache is the single source of
 * truth for the advisory verdict.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  assessQuality, getQualityHistory,
  type QualityAssessment, type QualityEntityType, type QualityHistory,
} from "../api/quality";
import type { UUID } from "../types";

export const qualityKeys = {
  history: (ws: UUID | undefined, type: QualityEntityType, id: UUID | undefined) =>
    ["quality", "history", ws ?? "", type, id ?? ""] as const,
};

export function useQualityHistory(
  workspaceId: UUID | undefined, entityType: QualityEntityType, entityId: UUID | undefined
) {
  return useQuery<QualityHistory>({
    queryKey: qualityKeys.history(workspaceId, entityType, entityId),
    queryFn: () => getQualityHistory(workspaceId as UUID, entityType, entityId as UUID),
    enabled: Boolean(workspaceId && entityId),
  });
}

/** Runs an assessment and invalidates the entity's history on success. */
export function useAssessQuality(
  workspaceId: UUID, entityType: QualityEntityType, entityId: UUID
) {
  const queryClient = useQueryClient();
  return useMutation<QualityAssessment, unknown, { force?: boolean }>({
    mutationFn: ({ force = false }) => assessQuality(workspaceId, entityType, entityId, force),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: qualityKeys.history(workspaceId, entityType, entityId),
      });
    },
  });
}

/** Stale only when both versions are known and the verdict is older. */
export function isAssessmentStale(
  latest: QualityAssessment | null | undefined, entityVersion: number | undefined
): boolean {
  if (!latest || typeof entityVersion !== "number") return false;
  const assessedVersion = latest.entity_version;
  if (typeof assessedVersion !== "number") return false;
  return assessedVersion < entityVersion;
}

/**
 * Badge controller: the OPEN state of the disclosure plus the latest verdict
 * from the shared history query. It never fetches on its own — a failed read
 * stays "not assessed" (advisory only, never a gate), and a successful
 * assessment updates it through cache invalidation.
 */
export function useQualityBadge(
  workspaceId: UUID | undefined,
  entityType: QualityEntityType,
  entityId: UUID | undefined,
  entityVersion?: number
) {
  const [open, setOpen] = useState(false);
  const history = useQualityHistory(workspaceId, entityType, entityId);
  const latest = history.data?.latest ?? null;

  return {
    open,
    toggle: () => setOpen((value) => !value),
    latest,
    stale: isAssessmentStale(latest, entityVersion),
  };
}
