/**
 * REUSE finding F-14 (frontend audit 2026-10-15, plan Phase 3 §3.7): the
 * `const initialValues = useMemo(() => xToFormValues(x), [x])` boilerplate was
 * repeated verbatim in all seven `*ArtifactForm` wrappers. This hook is that
 * extraction, so the memo is declared once instead of seven times.
 *
 * Why `useMemo` at all: `ArtifactForm` keeps
 * `initialRef.current = initialValues` and re-derives its whole field bag from
 * `initialValues`, so handing it a fresh object on every parent render would
 * look like a new baseline on every keystroke. The wrappers memoized on the
 * artifact identity for exactly that reason; this hook keeps that contract.
 *
 * `toValues` is a dependency of the memo, so it MUST be referentially stable —
 * i.e. a module-scope function. A `toValues` defined inline in the component
 * body would recreate on every render, defeat the memo entirely and reintroduce
 * the per-render object churn this extraction exists to remove. Every call site
 * therefore passes its module-scope `xToFormValues` function
 * (`adrToFormValues`, `riskToFormValues`, …); `useInitialFormValues.test.ts`
 * pins both halves of that contract.
 */

import { useMemo } from "react";

/**
 * Derive an artifact form's `initialValues` from its REST entity, memoized on
 * the entity and the converter.
 *
 * @param artifact the REST entity the form is bound to (its identity is the
 *   reset signal `ArtifactForm` already relies on).
 * @param toValues module-scope mapper from the entity to the form's value bag
 *   (see the stability contract in the file header).
 */
export function useInitialFormValues<TIn, TOut>(
  artifact: TIn,
  toValues: (artifact: TIn) => TOut,
): TOut {
  return useMemo(() => toValues(artifact), [artifact, toValues]);
}
