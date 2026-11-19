/**
 * Mobile sheet coordinator — plan §3.5 "exactly one expanded sheet" owner.
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector) / trace-spine footer (Schnitt 4b)
 * req_id:  REQ-L1-093 (accessibility baseline)
 *
 * On a phone the trace footer and the artifact inspector are two overlays over
 * the same detail area. Both display preferences may be on at once, but only
 * ONE sheet may be expanded: opening one collapses the other. A tiny external
 * store (React `useSyncExternalStore`) is the single source of truth — it keeps
 * the eight host routes out of the coordination entirely (they keep passing
 * only their artifact descriptor / inspector props as before).
 *
 * The store records *which* surface owns the expanded state, not whether it is
 * modal. Both surfaces are deliberately NON-modal regions (see
 * `InspectorSheet` / issue #1762): the covered detail area is made `inert`
 * instead of trapping focus. A genuine modal dialog (`ImpactDrawer`) does not
 * use this store at all — it is modal by itself and the only surface that
 * legitimately carries `aria-modal="true"`.
 *
 * Release calls are idempotent: releasing "inspector" while the footer owns
 * the expanded state is a no-op, which is what makes the bidirectional
 * "opening one collapses the other" effects free of feedback loops.
 */

export type MobileSheetId = "trace-footer" | "inspector";

type Listener = () => void;

let expandedSheet: MobileSheetId | null = null;
const listeners = new Set<Listener>();

function notify(): void {
  for (const listener of listeners) listener();
}

/** Stable snapshot for `useSyncExternalStore` (a string or null, never a fresh object). */
export function getExpandedMobileSheet(): MobileSheetId | null {
  return expandedSheet;
}

/** Subscribe to owner changes; returns the unsubscribe function. */
export function subscribeToMobileSheet(listener: Listener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/** Claim the expanded-sheet slot for `id`, collapsing whoever owned it. */
export function requestMobileSheet(id: MobileSheetId): void {
  if (expandedSheet === id) return;
  expandedSheet = id;
  notify();
}

/** Release the slot only if `id` currently owns it (idempotent, loop-safe). */
export function releaseMobileSheet(id: MobileSheetId): void {
  if (expandedSheet !== id) return;
  expandedSheet = null;
  notify();
}

/** Test-only reset so a stale owner cannot leak between unit-test renders. */
export function resetMobileSheetCoordinator(): void {
  if (expandedSheet === null) return;
  expandedSheet = null;
  notify();
}
