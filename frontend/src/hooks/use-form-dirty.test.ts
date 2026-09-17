import { describe, it, expect } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useFormDirty } from './use-form-dirty';

interface Values {
  title: string;
  count: number;
}

describe('useFormDirty', () => {
  it('starts clean when values equal the initial baseline', () => {
    const values: Values = { title: 'a', count: 1 };
    const { result } = renderHook(() => useFormDirty(values, values));
    expect(result.current.isDirty).toBe(false);
  });

  it('becomes dirty once values diverge from the baseline', () => {
    const initial: Values = { title: 'a', count: 1 };
    const { result, rerender } = renderHook(
      ({ values }) => useFormDirty(values, initial),
      { initialProps: { values: initial } },
    );
    expect(result.current.isDirty).toBe(false);

    rerender({ values: { title: 'edited', count: 1 } });
    expect(result.current.isDirty).toBe(true);
  });

  it('markClean re-anchors the baseline so isDirty goes back to false', () => {
    const initial: Values = { title: 'a', count: 1 };
    const { result, rerender } = renderHook(
      ({ values }) => useFormDirty(values, initial),
      { initialProps: { values: initial } },
    );

    const edited: Values = { title: 'edited', count: 1 };
    rerender({ values: edited });
    expect(result.current.isDirty).toBe(true);

    act(() => {
      result.current.markClean(edited);
    });
    rerender({ values: edited });
    expect(result.current.isDirty).toBe(false);
  });

  /**
   * Issue #672 — the whole point of an explicit `markClean` instead of an
   * automatic prop-driven baseline: a successful save must be able to
   * declare "clean" using the values it just submitted, without waiting for
   * a refetch (which may lag behind and would otherwise flash a spurious
   * dirty state).
   */
  it('markClean can anchor to values that differ from the current `values` argument (e.g. a save that already cleared a save-time-only field)', () => {
    const initial: Values = { title: 'a', count: 1 };
    const { result, rerender } = renderHook(
      ({ values }) => useFormDirty(values, initial),
      { initialProps: { values: initial } },
    );

    rerender({ values: { title: 'a', count: 2 } });
    expect(result.current.isDirty).toBe(true);

    act(() => {
      result.current.markClean({ title: 'a', count: 2 });
    });
    rerender({ values: { title: 'a', count: 2 } });
    expect(result.current.isDirty).toBe(false);
  });
});
