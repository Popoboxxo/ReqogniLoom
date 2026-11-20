/**
 * ARIA treeview keyboard navigation (roving tabindex) for `WorkspaceTree`.
 *
 * Extracted verbatim from the 1000-line `WorkspaceTree` component: the hook
 * owns focus state, the id→<li> element map, virtualizer-aware focus moves and
 * the delegated key handler (↑ ↓ → ← Home End, letter-jump, Enter, `*`,
 * Alt+↑/↓ for reordering). Behaviour and comments are preserved; the component
 * keeps selection reveal (which only needs the exposed `rowElementsRef`).
 *
 * Design reference: docs/architecture §12.5.
 */
import { type KeyboardEvent as ReactKeyboardEvent, useCallback, useEffect, useRef, useState } from 'react';
import {
  artifactNodeId,
  isGroupFolderNode,
} from './tree-groups';
import type { FlatRow } from './workspace-tree.logic';
import type { TreeStepDirection } from './tree-reorder';

/** The subset of the virtualizer this hook needs. */
export interface TreeKeyboardVirtualizer {
  scrollToIndex: (index: number, options?: { align?: 'auto' | 'start' | 'center' | 'end' }) => void;
}

export interface UseTreeKeyboardOptions {
  visibleRows: FlatRow[];
  selectedId: string | null | undefined;
  onSelect: (id: string) => void;
  toggleExpand: (id: string) => void;
  setExpanded: React.Dispatch<React.SetStateAction<Set<string>>>;
  stepReorder: (id: string, direction: TreeStepDirection) => void;
  useVirtual: boolean;
  rowVirtualizer: TreeKeyboardVirtualizer;
}

export interface UseTreeKeyboardResult {
  focusedId: string | null;
  setFocusedId: React.Dispatch<React.SetStateAction<string | null>>;
  /** Maps node id → mounted <li> element (virtualized rows mount/unmount). */
  rowElementsRef: React.MutableRefObject<Map<string, HTMLLIElement>>;
  effectiveFocusedId: string | null;
  registerRowRef: (id: string, el: HTMLLIElement | null) => void;
  handleTreeKeyDown: (e: ReactKeyboardEvent<HTMLUListElement>) => void;
  focusRowAtIndex: (index: number) => void;
}

export function useTreeKeyboard({
  visibleRows,
  selectedId,
  onSelect,
  toggleExpand,
  setExpanded,
  stepReorder,
  useVirtual,
  rowVirtualizer,
}: UseTreeKeyboardOptions): UseTreeKeyboardResult {
  const [focusedId, setFocusedId] = useState<string | null>(null);
  const rowElementsRef = useRef<Map<string, HTMLLIElement>>(new Map());
  // Id awaiting DOM focus once its row is scrolled into view and mounts.
  const pendingFocusIdRef = useRef<string | null>(null);

  // Drop a stale focus target once it scrolls out of the visible/filtered set
  // (e.g. search narrows the list, or a collapse hides the focused node).
  useEffect(() => {
    if (focusedId !== null && !visibleRows.some((r) => r.internal.node.id === focusedId)) {
      setFocusedId(null);
    }
  }, [visibleRows, focusedId]);

  const registerRowRef = useCallback((id: string, el: HTMLLIElement | null): void => {
    if (el) {
      rowElementsRef.current.set(id, el);
      // The row we were waiting to scroll into view just mounted — focus it now.
      if (pendingFocusIdRef.current === id) {
        pendingFocusIdRef.current = null;
        el.focus();
      }
    } else {
      rowElementsRef.current.delete(id);
    }
  }, []);

  /**
   * Moves roving-tabindex focus to `visibleRows[index]`.
   *
   * In the virtualized path the target row may not be mounted yet — in
   * that case we ask the virtualizer to scroll it into view and defer the
   * actual `.focus()` call to `registerRowRef`, which fires once the row's
   * <li> commits to the DOM. Calling `.focus()` on a not-yet-rendered node
   * is impossible, so this two-step sequence (scroll, then focus-on-mount)
   * is required rather than optional.
   */
  const focusRowAtIndex = useCallback(
    (index: number): void => {
      if (index < 0 || index >= visibleRows.length) return;
      const targetId = visibleRows[index].internal.node.id;
      setFocusedId(targetId);
      const el = rowElementsRef.current.get(targetId);
      if (el) {
        el.focus();
      } else {
        pendingFocusIdRef.current = targetId;
        if (useVirtual) {
          rowVirtualizer.scrollToIndex(index, { align: 'auto' });
        }
      }
    },
    [visibleRows, useVirtual, rowVirtualizer],
  );

  // The row that currently owns tabIndex=0 for keyboard entry into the tree,
  // even before any key has been pressed (falls back to selection, then root).
  const effectiveFocusedId =
    focusedId ?? selectedId ?? visibleRows[0]?.internal.node.id ?? null;

  const handleTreeKeyDown = useCallback(
    (e: ReactKeyboardEvent<HTMLUListElement>): void => {
      // N1 (SC 2.1.1, Phase 6 review): this handler is delegated on the <ul>,
      // so it also sees keys pressed while one of a row's own native controls
      // has focus — the "Move…" button, the expand toggle, a form control in a
      // custom `renderRow`. Those controls own their keys: without this guard
      // Enter on the Move button was swallowed by the case below (it called
      // `onSelect` instead of activating the button, so the dialog never
      // opened) and printable keys were swallowed by the letter-jump. Bail out
      // before the switch, so the native activation wins. Rows themselves
      // (`<li role="treeitem">`) are unaffected — keyboard navigation between
      // rows still runs through the switch below.
      const eventTarget = e.target as HTMLElement | null;
      if (eventTarget?.closest('button, a, input, select, textarea')) return;
      if (visibleRows.length === 0) return;
      const currentId = focusedId ?? selectedId ?? visibleRows[0].internal.node.id;
      const currentIndex = visibleRows.findIndex((r) => r.internal.node.id === currentId);
      const safeIndex = currentIndex === -1 ? 0 : currentIndex;
      const currentRow = visibleRows[safeIndex];

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          if (e.altKey) {
            // P1 Task 1.7: the keyboard alternative to dragging (WCAG 2.1.1 /
            // 2.5.7) — one sibling step, no pointer needed.
            stepReorder(currentRow.internal.node.id, 'down');
            break;
          }
          focusRowAtIndex(Math.min(safeIndex + 1, visibleRows.length - 1));
          break;
        case 'ArrowUp':
          e.preventDefault();
          if (e.altKey) {
            stepReorder(currentRow.internal.node.id, 'up');
            break;
          }
          focusRowAtIndex(Math.max(safeIndex - 1, 0));
          break;
        case 'ArrowRight':
          e.preventDefault();
          if (currentRow.hasChildren && !currentRow.isExpanded) {
            toggleExpand(currentRow.internal.node.id);
          } else if (currentRow.hasChildren && currentRow.isExpanded) {
            // Children are flattened immediately after their parent (flattenVisible).
            focusRowAtIndex(safeIndex + 1);
          }
          break;
        case 'ArrowLeft': {
          e.preventDefault();
          if (currentRow.hasChildren && currentRow.isExpanded) {
            toggleExpand(currentRow.internal.node.id);
          } else {
            const parentId = currentRow.internal.node.parentId;
            if (parentId) {
              const parentIndex = visibleRows.findIndex(
                (r) => r.internal.node.id === parentId,
              );
              if (parentIndex !== -1) focusRowAtIndex(parentIndex);
            }
          }
          break;
        }
        case 'Home':
          e.preventDefault();
          focusRowAtIndex(0);
          break;
        case 'End':
          e.preventDefault();
          focusRowAtIndex(visibleRows.length - 1);
          break;
        case 'Enter':
          // Same activation the row's onClick already performs. A group folder
          // is chrome, not an artifact: activating it opens/closes it.
          e.preventDefault();
          if (isGroupFolderNode(currentRow.internal.node)) {
            if (currentRow.hasChildren) toggleExpand(currentRow.internal.node.id);
            break;
          }
          onSelect(artifactNodeId(currentRow.internal.node));
          break;
        case '*': {
          // ARIA treeview convention: expand every sibling at the current
          // item's level (i.e. every node sharing its parentId).
          e.preventDefault();
          const parentId = currentRow.internal.node.parentId;
          const siblingIdsToExpand = visibleRows
            .filter((r) => r.hasChildren && r.internal.node.parentId === parentId)
            .map((r) => r.internal.node.id);
          if (siblingIdsToExpand.length > 0) {
            setExpanded((prev) => {
              const next = new Set(prev);
              for (const id of siblingIdsToExpand) next.add(id);
              return next;
            });
          }
          break;
        }
        default: {
          // Letter-jump: move to the next visible item whose label starts
          // with the typed character (case-insensitive), cycling.
          if (e.key.length === 1 && !e.ctrlKey && !e.metaKey && !e.altKey) {
            const char = e.key.toLowerCase();
            const n = visibleRows.length;
            for (let step = 1; step <= n; step++) {
              const idx = (safeIndex + step) % n;
              if (visibleRows[idx].internal.node.name.toLowerCase().startsWith(char)) {
                e.preventDefault();
                focusRowAtIndex(idx);
                break;
              }
            }
          }
        }
      }
    },
    [
      visibleRows,
      focusedId,
      selectedId,
      toggleExpand,
      onSelect,
      focusRowAtIndex,
      stepReorder,
      setExpanded,
    ],
  );

  return {
    focusedId,
    setFocusedId,
    rowElementsRef,
    effectiveFocusedId,
    registerRowRef,
    handleTreeKeyDown,
    focusRowAtIndex,
  };
}
