const OUTDATED_STATES: ReadonlySet<string> = new Set([
  "deprecated",
  "rejected",
  "superseded",
  "closed",
  "wontfix",
  "archiviert",
  "archived",
  "abandoned",
  "outdated",
  "deleted",
]);

export function isOutdatedState(state?: string | null): boolean {
  if (!state) return false;
  return OUTDATED_STATES.has(state.trim().toLowerCase());
}

export function findOutdatedTransition<T extends { target_state: string }>(
  transitions: readonly T[],
): T | undefined {
  return transitions.find((transition) => isOutdatedState(transition.target_state));
}
