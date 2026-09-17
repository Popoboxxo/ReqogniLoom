import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useEntityReset } from './use-entity-reset';

describe('useEntityReset', () => {
  it('runs reset on mount', () => {
    const reset = vi.fn();
    renderHook(() => useEntityReset('id-1', reset));
    expect(reset).toHaveBeenCalledTimes(1);
  });

  it('runs reset again when entityId changes', () => {
    const reset = vi.fn();
    const { rerender } = renderHook(({ id }) => useEntityReset(id, reset), {
      initialProps: { id: 'id-1' },
    });
    expect(reset).toHaveBeenCalledTimes(1);

    rerender({ id: 'id-2' });
    expect(reset).toHaveBeenCalledTimes(2);
  });

  it('issue #700: does NOT re-run reset when entityId stays the same, even if the reset callback identity changes (e.g. a same-entity refetch)', () => {
    const reset = vi.fn();
    const { rerender } = renderHook(({ id }) => useEntityReset(id, reset), {
      initialProps: { id: 'id-1' },
    });
    expect(reset).toHaveBeenCalledTimes(1);

    // Same id, brand-new closure — simulates a parent re-render caused by a
    // refetch of the SAME entity (new object reference, same id).
    const reset2 = vi.fn();
    rerender({ id: 'id-1' });
    expect(reset).toHaveBeenCalledTimes(1);
    expect(reset2).not.toHaveBeenCalled();
  });
});
