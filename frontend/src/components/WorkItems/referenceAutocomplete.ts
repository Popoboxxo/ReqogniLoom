/**
 * ARCH-L1-001 ReactFrontend — `[[` reference autocomplete helpers (F3-T9).
 *
 * Pure functions so the trigger grammar and the ranking are testable without
 * a DOM. The editor owns the popup and the insertion; this module only answers
 * "is the caret inside an open `[[…` trigger?" and "which terms match?".
 */

import type { GlossaryTerm } from "../../types";

export interface ReferenceTrigger {
  /** Offset of the opening `[[` in the current value. */
  start: number;
  /** Text typed after `[[`, up to the caret. */
  query: string;
}

/** Longest query we still treat as a term search, not prose. */
const MAX_QUERY_LENGTH = 60;

/**
 * Detect an open `[[` trigger before `caret`.
 *
 * Returns `null` when there is no opening `[[`, when a `]]` already closes it,
 * or when the text between them cannot be a term name (newline/bracket).
 */
export function findReferenceTrigger(
  text: string,
  caret: number
): ReferenceTrigger | null {
  if (caret < 0 || caret > text.length) return null;
  const before = text.slice(0, caret);
  const open = before.lastIndexOf("[[");
  if (open === -1) return null;
  const close = before.lastIndexOf("]]");
  if (close > open) return null;
  const query = before.slice(open + 2);
  if (query.length > MAX_QUERY_LENGTH) return null;
  if (/[\n\r[\]]/.test(query)) return null;
  return { start: open, query };
}

/**
 * Terms matching `query` by name, abbreviation or synonym, case-insensitively.
 * A term without a `global_uuid` cannot be referenced and is never offered.
 */
export function filterReferenceSuggestions(
  terms: readonly GlossaryTerm[],
  query: string,
  limit = 8
): GlossaryTerm[] {
  const needle = query.trim().toLowerCase();
  return terms
    .filter((term) => Boolean(term.global_uuid))
    .filter((term) => {
      if (!needle) return true;
      const haystack = [term.term, term.abbreviation ?? "", ...(term.synonyms ?? [])]
        .join(" ")
        .toLowerCase();
      return haystack.includes(needle);
    })
    .slice(0, limit);
}
