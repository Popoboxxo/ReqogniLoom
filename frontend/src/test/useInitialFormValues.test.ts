/**
 * ARCH-L1-001 ReactFrontend — useInitialFormValues hook.
 *
 * REUSE finding F-14 (frontend audit 2026-10-15, plan Phase 3b §3.7): the
 * `const initialValues = useMemo(() => xToFormValues(x), [x])` boilerplate was
 * duplicated in all seven `*ArtifactForm` wrappers. This suite pins the pieces
 * the wrapper migrations rely on for zero behavior change:
 *
 *   - the derivation is exactly `toValues(artifact)` (no transformation of its
 *     own — the wrappers' `xToFormValues` stays authoritative),
 *   - the result reference is stable while artifact and `toValues` are stable
 *     (`ArtifactForm` treats a new object as a new baseline),
 *   - the memo recomputes when either the artifact or `toValues` changes, and
 *     `toValues` is a documented referential-stability requirement (all seven
 *     call sites pass a module-scope function).
 *
 * Location note: the task allowed either a co-located `hooks/*.test.ts` or a
 * central `src/test/*.test.ts`. This follows the closer precedent — the
 * previous extraction of the SAME phase, `useArtifactList.test.ts`, which lives
 * in `src/test/` — rather than the older co-located `use-form-dirty.test.ts`.
 */

import { describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import { useInitialFormValues } from "../hooks/useInitialFormValues";

interface Entity {
  id: string;
  title: string;
  custom_fields?: Record<string, unknown>;
}

interface FormValues {
  title: string;
  custom_fields: Record<string, unknown>;
}

/** Module-scope converter — mirrors the wrappers' `xToFormValues` helpers. */
function toFormValues(entity: Entity): FormValues {
  return {
    title: entity.title,
    custom_fields: entity.custom_fields ?? {},
  };
}

const ENTITY: Entity = { id: "a-1", title: "Alpha" };

describe("useInitialFormValues", () => {
  it("returns the converter's output for the given artifact", () => {
    const { result } = renderHook(() => useInitialFormValues(ENTITY, toFormValues));

    expect(result.current).toEqual({ title: "Alpha", custom_fields: {} });
  });

  it("keeps the result reference stable across rerenders with stable inputs", () => {
    const { result, rerender } = renderHook(
      (props: { artifact: Entity; toValues: (e: Entity) => FormValues }) =>
        useInitialFormValues(props.artifact, props.toValues),
      { initialProps: { artifact: ENTITY, toValues: toFormValues } },
    );

    const first = result.current;
    // A rerender with the same references must not re-derive the value bag.
    rerender({ artifact: ENTITY, toValues: toFormValues });

    expect(result.current).toBe(first);
  });

  it("recomputes when the artifact identity changes", () => {
    const next: Entity = { id: "a-2", title: "Beta" };
    const { result, rerender } = renderHook(
      (props: { artifact: Entity }) => useInitialFormValues(props.artifact, toFormValues),
      { initialProps: { artifact: ENTITY } },
    );

    const first = result.current;
    rerender({ artifact: next });

    expect(result.current).not.toBe(first);
    expect(result.current.title).toBe("Beta");
  });

  it("recomputes when the converter identity changes (module-scope requirement)", () => {
    // `toValues` is a memo dependency on purpose: an inline converter would
    // defeat the memo — this test documents that the caller, not the hook, owns
    // that stability (see the hook's file header).
    const first = vi.fn(toFormValues);
    const second = vi.fn(toFormValues);
    const { result, rerender } = renderHook(
      (props: { toValues: (e: Entity) => FormValues }) =>
        useInitialFormValues(ENTITY, props.toValues),
      { initialProps: { toValues: first } },
    );

    const initial = result.current;
    rerender({ toValues: second });

    expect(first).toHaveBeenCalledTimes(1);
    expect(second).toHaveBeenCalledTimes(1);
    expect(result.current).not.toBe(initial);
  });

  it("calls the converter once per artifact change, not once per render", () => {
    const spy = vi.fn(toFormValues);
    const { rerender } = renderHook(
      (props: { artifact: Entity }) => useInitialFormValues(props.artifact, spy),
      { initialProps: { artifact: ENTITY } },
    );

    // Same artifact, same (module-scope-stable) spy: no extra call.
    rerender({ artifact: ENTITY });
    expect(spy).toHaveBeenCalledTimes(1);

    // A different entity re-derives exactly once.
    rerender({ artifact: { id: "a-3", title: "Gamma" } });
    expect(spy).toHaveBeenCalledTimes(2);
  });
});
