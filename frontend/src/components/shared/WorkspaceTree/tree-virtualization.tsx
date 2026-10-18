/**
 * WorkspaceTree — opt-in list virtualization (FE-01 extraction, REQ-091).
 *
 * Extracted from `workspace-tree.tsx`: the threshold gate, the virtualizer
 * setup, the measured list height and the per-row transform. The virtualized
 * `<ul>`/`<li>` JSX stays in `workspace-tree.tsx` (the design-system ratchet
 * baseline is pinned to that file); this module owns the harness around it.
 *
 * Behaviour is unchanged: virtualization only kicks in when the consumer opted
 * in via `virtualize` *and* the visible row count exceeds
 * `VIRTUALIZE_THRESHOLD`; a `renderRow` override that is taller than the
 * default single-line label must pass a matching `virtualRowHeight`, or the
 * absolutely-positioned rows overlap past the threshold.
 */

import { type CSSProperties, type RefObject, useCallback, useRef } from 'react';
import {
  useVirtualizer,
  type ReactVirtualizer,
} from '@tanstack/react-virtual';

// REQ-091: virtualization threshold 100 items.
export const VIRTUALIZE_THRESHOLD = 100;
// REQ-091: fixed row height estimate — TreeRow minHeight 32px + 2px list gap.
export const VIRTUAL_ROW_HEIGHT = 34;

export interface TreeVirtualizationOptions {
  /** Consumer opt-in (`WorkspaceTreeProps.virtualize`). */
  virtualize: boolean;
  /** Number of currently visible rows (flattened, filtered). */
  rowCount: number;
  /** Optional per-row height override (see `WorkspaceTreeProps.virtualRowHeight`). */
  virtualRowHeight?: number;
}

export interface TreeVirtualization {
  /** Attach to the scroll host the virtualizer measures. */
  parentRef: RefObject<HTMLDivElement | null>;
  /** True when virtualization is on *and* the row count exceeds the threshold. */
  useVirtual: boolean;
  /** The virtualizer instance — needed for `scrollToIndex` by the tree. */
  rowVirtualizer: ReactVirtualizer<HTMLDivElement, Element>;
  /** Measured list height; spread onto the `<ul>`'s `style`. */
  virtualListStyle: CSSProperties;
  /**
   * Absolute positioning (including the virtualizer's `translateY`) for one
   * row. Returned as a computed identifier, never an inline JSX object literal
   * (see the module header of `workspace-tree.tsx`).
   */
  rowPositionStyle: (start: number) => CSSProperties;
}

/** Sets up the tree's virtualizer and the derived styles that go with it. */
export function useTreeVirtualization({
  virtualize,
  rowCount,
  virtualRowHeight,
}: TreeVirtualizationOptions): TreeVirtualization {
  const parentRef = useRef<HTMLDivElement>(null);
  const useVirtual = virtualize && rowCount > VIRTUALIZE_THRESHOLD;
  const rowVirtualizer = useVirtualizer({
    count: rowCount,
    getScrollElement: () => parentRef.current,
    estimateSize: () => virtualRowHeight ?? VIRTUAL_ROW_HEIGHT,
    overscan: 12,
  });

  // Issue #876 (Etappe 5): the virtualized list's height is a measured pixel
  // value (`getTotalSize()`), so it stays on the `style` prop as a computed
  // identifier rather than a class.
  const virtualListStyle = {
    height: `${rowVirtualizer.getTotalSize()}px`,
  } as CSSProperties;

  const rowPositionStyle = useCallback(
    (start: number): CSSProperties => ({
      position: 'absolute',
      top: 0,
      left: 0,
      width: '100%',
      transform: `translateY(${start}px)`,
    }),
    [],
  );

  return {
    parentRef,
    useVirtual,
    rowVirtualizer,
    virtualListStyle,
    rowPositionStyle,
  };
}
