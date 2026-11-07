/**
 * P4.4 — batch workflow-lock read for the classic trees.
 *
 * Wraps `GET /api/v1/workspaces/<id>/locks/?type=requirement|architecture`
 * (`WorkspaceViewSet.locks`, backed by `application.artifact_freeze`).
 *
 * | `type` | keys of the returned map |
 * |--------|--------------------------|
 * | `requirement` | `Requirement.id` — exactly the id the requirement tree uses as node id |
 * | `architecture` | `ArchitectureElement.id` — exactly the id the architecture tree uses as node id |
 *
 * The answer only contains FROZEN artifacts: `{id: workflow state name}` for
 * every artifact whose current workflow state carries
 * `state_meta.freeze_on_enter`. Unfrozen artifacts are absent, so an empty
 * object is the normal answer for a workspace whose presets lock nothing.
 *
 * The endpoint is a read: a missing/wrong `type` answers 400, a caller without
 * read permission 403 and a foreign workspace 404. Callers treat a failed read
 * as "no locks" (see `useWorkspaceLocks`) — the backend still enforces the
 * freeze, so degrading the *display* never weakens the rule.
 *
 * Deliberately NOT re-exported from `api/index.ts`, like the other
 * single-surface modules (`tiers.ts`, `tree-display-config.ts`).
 */

import { apiClient } from "./client";

/** The two artifact types whose trees show the lock (P4.4). */
export type LockTargetType = "requirement" | "architecture";

/** Wire shape of the batch lock endpoint. */
export interface WorkspaceLocksResponse {
  locks: Record<string, string>;
}

/** Map of artifact id → freezing workflow state name. */
export type LockMap = Record<string, string>;

export const locksApi = {
  /**
   * GET — the frozen artifacts of one type in a workspace. One request for the
   * whole tree; never one per row.
   */
  async list(workspaceId: string, type: LockTargetType): Promise<LockMap> {
    const query = new URLSearchParams({ type }).toString();
    const response = await apiClient.get<WorkspaceLocksResponse>(
      `/workspaces/${workspaceId}/locks/?${query}`,
    );
    return response?.locks ?? {};
  },
};

/**
 * Convenience function form used by the tree consumers (and their tests).
 * Mirrors {@link locksApi.list}.
 */
export function fetchLocks(
  workspaceId: string,
  type: LockTargetType,
): Promise<LockMap> {
  return locksApi.list(workspaceId, type);
}
