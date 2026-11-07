/**
 * Pure allocation-view helpers (P3/P4).
 *
 * Kept out of `api/allocation-view.ts` so tests that mock the API module (a
 * full module replacement) still get the lock/suggestion helpers at runtime.
 */

import type {
  AllocationLock,
  ArchitectureSuggestion,
  SuggestArchitectureResponse,
} from "../api/allocation-view";

/** The workflow state name that freezes a row, or `null` when writable. */
export function lockStateName(locked: AllocationLock | undefined): string | null {
  if (typeof locked === "string") return locked || null;
  if (locked && typeof locked === "object") return locked.state ?? null;
  return null;
}

/** Whether the row is frozen (any non-empty lock marker). */
export function isRowLocked(locked: AllocationLock | undefined): boolean {
  return locked === true || lockStateName(locked) !== null;
}

/**
 * Normalise the suggestion response into one de-duplicated candidate list.
 *
 * The committed backend returns `suggested_arch_element_ids`; the richer
 * `suggested_elements` shape (id + reason) is accepted so a future provider
 * answer needs no client change.
 */
export function toArchitectureSuggestions(
  response: SuggestArchitectureResponse | null | undefined
): ArchitectureSuggestion[] {
  if (!response) return [];
  const seen = new Set<string>();
  const suggestions: ArchitectureSuggestion[] = [];

  for (const entry of response.suggested_elements ?? []) {
    const elementId = entry.element_id ?? entry.id;
    if (!elementId || seen.has(elementId)) continue;
    seen.add(elementId);
    suggestions.push({
      element_id: elementId,
      reason: entry.reason ?? entry.rationale ?? null,
      title: entry.title ?? null,
    });
  }

  for (const elementId of response.suggested_arch_element_ids ?? []) {
    if (!elementId || seen.has(elementId)) continue;
    seen.add(elementId);
    suggestions.push({ element_id: elementId, reason: null });
  }

  return suggestions;
}
