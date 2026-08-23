/**
 * Issue #672 — shared "has this form got unsaved local edits" tracker.
 *
 * `isDirty` compares the caller-supplied `values` snapshot against a
 * baseline the caller controls explicitly via `markClean` — it is NOT
 * re-derived automatically from a prop. That is deliberate: the baseline
 * must be re-anchored at two specific moments only —
 *   1. when the edited entity actually changes (pair with `useEntityReset`
 *      and call `markClean` from inside its `reset` callback), and
 *   2. right after a save the caller knows succeeded, using the exact
 *      values that were just submitted — not whatever the next refetch of
 *      `requirement`/`element` happens to resolve with, which may lag the
 *      save by a network round trip and would otherwise flash a spurious
 *      "unsaved changes" state for that window.
 *
 * Values are compared with `JSON.stringify`, which is adequate for the flat
 * string/number/boolean fields and small `custom_fields` maps these two
 * forms carry — no need for a deep-equality dependency at this scope.
 */

import { useCallback, useState } from 'react';

export interface UseFormDirtyResult<T> {
  isDirty: boolean;
  /** Re-anchor the baseline to `snapshot` so `isDirty` goes back to `false`
   *  until the next local edit. */
  markClean: (snapshot: T) => void;
}

export function useFormDirty<T>(values: T, initial: T): UseFormDirtyResult<T> {
  const [baseline, setBaseline] = useState<string>(() => JSON.stringify(initial));

  const markClean = useCallback((snapshot: T): void => {
    setBaseline(JSON.stringify(snapshot));
  }, []);

  return { isDirty: JSON.stringify(values) !== baseline, markClean };
}
