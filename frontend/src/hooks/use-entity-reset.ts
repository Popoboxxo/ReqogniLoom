/**
 * Issue #700 / #673 — shared entity-switch reset primitive.
 *
 * Runs `reset` exactly once per distinct `entityId`, i.e. when the caller
 * switches to editing a genuinely different artifact (a different
 * Requirement/ArchitectureElement/...), NEVER on a refetch of the SAME
 * artifact that merely produces a new object reference with an unchanged
 * id (e.g. after a save completes, or an unrelated background refresh).
 *
 * `RequirementForm` used to key its reset effect on the whole `requirement`
 * object (`useEffect(..., [requirement])`), which re-ran on every one of
 * those same-id refetches too. That blindly overwrote local form state —
 * including fields that never round-trip through the server at all (e.g.
 * `change_reason`, a save-time-only annotation that is always `null`/empty
 * once reloaded). If such a refetch landed while a save was still in
 * flight, the reset could silently wipe text the user had just typed
 * before the save call ever read it (issue #700).
 *
 * `ArchitectureForm` already keyed its own reset effect on `element.id`
 * for this exact reason; this hook lifts that (correct) pattern out so
 * both forms share one implementation instead of two effects that can
 * silently drift apart again (issue #673).
 */

import { useEffect } from 'react';

export function useEntityReset(entityId: string, reset: () => void): void {
  useEffect(() => {
    reset();
    // `reset` is intentionally excluded from the dependency array: it is a
    // fresh closure on every render, and only a genuine identity change
    // (`entityId`) must trigger a reset here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [entityId]);
}
