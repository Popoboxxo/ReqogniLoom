/**
 * Goals route — workflow-semantics helpers (issue #238).
 *
 * Goal and MainGoal are immutable version chains: the backend answers
 * `DELETE /api/v1/goals/{id}/` and `DELETE /api/v1/main-goals/{id}/` with a
 * deliberate 405 (`GoalViewSet.destroy` / `MainGoalViewSet.destroy` — there is
 * no delete semantics for either type, by design). Removing a goal therefore
 * means moving it into the workflow's archive state, which
 * `backend/workflow/definition_store.py` marks `is_outdated_equivalent: True`
 * and which `GoalService.list_current()` then filters out of the list — i.e.
 * exactly the soft-delete escape hatch every other artifact type uses.
 *
 * That makes the archive move destructive *from the user's point of view*
 * (the goal disappears from the route), so it must be confirmed and must not
 * look like the ordinary approve/rework buttons next to it.
 *
 * Identifying WHICH move that is cannot be hardcoded to "Archiviert": a
 * workspace may customise its Goal state machine (ADR-06), and the
 * `/transitions/` contract carries no per-state metadata — `state_meta` is
 * not exposed by any endpoint the frontend can reach. What the codebase does
 * have is `resolveBadgeVariant`, its shared status-semantics classifier
 * (UI concept ch. 8.2), whose `warning` family is defined as exactly the
 * "superseded but recoverable" states (`outdated`, `archiviert`, ...). It is
 * already used the same way in `GoalsPage` to count approved goals without
 * naming a state. A custom workflow with no warning-family state simply gets
 * no archive affordance — the plain transition buttons still work.
 */

import { resolveBadgeVariant } from "../../utils/statusBadge";

/**
 * True when moving into `targetState` archives the artifact, i.e. takes it
 * out of the working set rather than advancing it through the lifecycle.
 */
export function isArchiveTransition(targetState: string): boolean {
  return resolveBadgeVariant(targetState) === "warning";
}

/**
 * True when `status` belongs to the "not yet approved" draft family
 * (review round 2, finding 2): `resolveBadgeVariant`'s `neutral` fallback is
 * exactly the draft/entwurf/unknown-state bucket (ch. 8.2). This is
 * deliberately a positive membership check, not a negative exclusion of
 * `success`/`warning` — a custom ADR-06 workflow can introduce states like
 * `rejected` (→ `danger`) or `in_review` (→ `info`) that a
 * `!== success && !== warning` filter would wrongly wave through as
 * pending drafts. Mirrors `isArchiveTransition` above, which classifies the
 * `warning` family the same positive way.
 */
export function isDraftState(status: string): boolean {
  return resolveBadgeVariant(status) === "neutral";
}
