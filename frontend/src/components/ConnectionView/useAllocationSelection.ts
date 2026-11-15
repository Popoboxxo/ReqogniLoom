/**
 * ARCH-L1-001 ReactFrontend — connection view "Bäume" selection (V.3).
 *
 * The tree renderer selects requirement rows by checkbox. The selection is the
 * one piece of state that has to outlive a filter change: ticking a row,
 * narrowing the filter and widening it again must not silently drop the tick.
 * So the hook keeps the raw **id set** and derives everything else from the
 * rows it is currently given:
 *
 * - `selectableIds` — the visible rows that may be selected at all (frozen rows
 *   are never selectable, matching the assistant's own rule);
 * - `selectedRows` — the visible, selectable rows that carry a tick, in the
 *   caller's row order. A tick on a row the current filter hides is kept in
 *   state but not reported, so "selected" always means "selected and visible";
 * - `isSelected` — the same predicate for one id, for rendering a checkbox.
 *
 * `selectAll` deliberately **adds** every visible selectable row instead of
 * replacing the set, so it cannot wipe a selection the filter merely hides.
 *
 * A row that becomes frozen while selected stops being reported (and stops
 * rendering as ticked) without losing its id: it becomes selected again only
 * if it is unlocked again. That is the intended reading of "a locked row is not
 * selectable" — the state set is not a place where a write could slip through.
 *
 * Pure local state: the hook keeps no server copy. The page owns it and hands
 * it to the renderer, so the (later) action bar and the tree read the same
 * selection instead of two parallel ones.
 */

import { useCallback, useMemo, useState } from "react";

import type { AllocationRow } from "../../api/allocation-view";
import { isRowLocked } from "../../utils/allocation";

export interface AllocationSelection {
  /** Ids of the visible rows that may be selected (frozen rows are excluded). */
  selectableIds: ReadonlySet<string>;
  /** Visible, selectable rows that are currently selected, in row order. */
  selectedRows: AllocationRow[];
  /** Whether `id` is selected *and* currently visible and selectable. */
  isSelected: (id: string) => boolean;
  /** Flip one id; a frozen or unknown id is a no-op. */
  toggle: (id: string) => void;
  /** Add every visible selectable row; hidden ticks are preserved. */
  selectAll: () => void;
  /** Drop the whole selection, including ticks on currently hidden rows. */
  clear: () => void;
}

export function useAllocationSelection(
  requirements: readonly AllocationRow[]
): AllocationSelection {
  const [selectedIds, setSelectedIds] = useState<ReadonlySet<string>>(
    () => new Set<string>()
  );

  const selectableIds = useMemo((): ReadonlySet<string> => {
    const ids = new Set<string>();
    for (const row of requirements) {
      if (!isRowLocked(row.locked)) ids.add(row.id);
    }
    return ids;
  }, [requirements]);

  const selectedRows = useMemo(
    () =>
      requirements.filter(
        (row) => selectedIds.has(row.id) && selectableIds.has(row.id)
      ),
    [requirements, selectedIds, selectableIds]
  );

  const isSelected = useCallback(
    (id: string) => selectedIds.has(id) && selectableIds.has(id),
    [selectedIds, selectableIds]
  );

  const toggle = useCallback(
    (id: string) => {
      setSelectedIds((previous) => {
        // Guard the write path, not only the checkbox: a frozen row must stay
        // unselectable even if a caller toggles it programmatically.
        if (!selectableIds.has(id)) return previous;
        const next = new Set(previous);
        if (next.has(id)) next.delete(id);
        else next.add(id);
        return next;
      });
    },
    [selectableIds]
  );

  const selectAll = useCallback(() => {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      for (const id of selectableIds) next.add(id);
      return next;
    });
  }, [selectableIds]);

  const clear = useCallback(() => {
    setSelectedIds(new Set<string>());
  }, []);

  return { selectableIds, selectedRows, isSelected, toggle, selectAll, clear };
}
