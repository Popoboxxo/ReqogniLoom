/**
 * WorkspaceTree — opt-in drag & drop reordering and reparenting (FE-01 extraction).
 *
 * Native HTML5 drag & drop, enabled only when a consumer passes `onReparent`
 * and/or `onReorder`. Extracted from `workspace-tree.tsx` so the drag state
 * machine, the cycle guard and the row/root-dropzone wiring live in one place
 * instead of being interleaved with the tree's rendering. The row and
 * root-dropzone *JSX* stays in `workspace-tree.tsx` (the `ui-ratchet`
 * design-system baseline is pinned to that file), this module owns the
 * behaviour behind it.
 *
 * Contract:
 *   - Both callbacks are opt-in; without either, nothing is draggable and no
 *     handlers are attached (see the prop docs in `workspace-tree.tsx`).
 *   - `onReparent` is the pre-P1 contract ("make this the parent"); it stays
 *     supported for callers that only re-parent.
 *   - `onReorder` additionally carries the position inside the new parent
 *     (`afterId`, see `tree-reorder.ts`) and wins when both are supplied.
 *   - Dropping a node on itself or into its own subtree is swallowed here and
 *     never reaches a callback (see `collectSelfAndDescendantIds` — a cycle
 *     makes a subtree unreachable).
 *   - `ROOT_DROP_TARGET` is a sentinel for the root dropzone; node ids come
 *     from the API, so a reserved non-UUID string cannot collide with one.
 */

import {
  type DragEvent as ReactDragEvent,
  useCallback,
  useMemo,
  useState,
} from 'react';
import {
  collectSelfAndDescendantIds,
  type HierarchyRef,
} from './tree-hierarchy';
import {
  type TreeDropPosition,
  resolveDropTarget,
} from './tree-reorder';

/**
 * Sentinel drop-target id for the root dropzone. Not a node id — node ids come
 * from the API, so a reserved non-UUID string cannot collide with one.
 */
export const ROOT_DROP_TARGET = '__root__';

/** Fraction of the row height on each edge that means "insert before/after". */
const DROP_EDGE_RATIO = 0.25;

/**
 * Classifies the pointer position over a row: the outer quarters act as
 * "insert before/after", the middle third as "drop into".
 *
 * jsdom reports a zero-height rect, so unit tests that need an edge override
 * `getBoundingClientRect` on the row; the fallback keeps the previous
 * behaviour (drop onto the row = make it the parent) there.
 */
export function dropPositionFromPointer(
  element: Element | null,
  clientY: number,
): TreeDropPosition {
  if (!element || typeof element.getBoundingClientRect !== 'function') {
    return 'inside';
  }
  const rect = element.getBoundingClientRect();
  if (rect.height <= 0) return 'inside';
  const ratio = (clientY - rect.top) / rect.height;
  if (ratio < DROP_EDGE_RATIO) return 'before';
  if (ratio > 1 - DROP_EDGE_RATIO) return 'after';
  return 'inside';
}

export interface TreeDragController {
  /** True when the consumer opted in via `onReparent` or `onReorder`. */
  dndEnabled: boolean;
  /** Id of the node currently being dragged, or `null`. */
  draggingId: string | null;
  /** Current drop target id; `ROOT_DROP_TARGET` marks the root dropzone. */
  dropTargetId: string | null;
  /** Which zone of the hovered row the pointer is in (reorder mode only). */
  dropPosition: TreeDropPosition | null;
  /** Row wiring, `undefined` when D&D is off (rows then render unchanged). */
  rowDragProps: TreeRowDragProps | undefined;
  /**
   * Shared move entry point for the keyboard "Move…" dialog. With `onReorder`
   * the target is appended as the last child of `newParentId`; with only
   * `onReparent` it is the pre-P1 reparent call.
   */
  reparent: (draggedId: string, newParentId: string | null) => boolean;
  /** Root dropzone is only mounted while `draggingId` is set. */
  onRootDragOver: (e: ReactDragEvent) => void;
  onRootDragLeave: (e: ReactDragEvent) => void;
  onRootDrop: (e: ReactDragEvent) => void;
}

/** Drag & drop wiring handed down from the tree to each row. */
export interface TreeRowDragProps {
  draggingId: string | null;
  dropTargetId: string | null;
  dropPosition: TreeDropPosition | null;
  onDragStartRow: (e: ReactDragEvent, id: string) => void;
  onDragOverRow: (e: ReactDragEvent, id: string) => void;
  onDragLeaveRow: (e: ReactDragEvent, id: string) => void;
  onDropRow: (e: ReactDragEvent, id: string) => void;
  onDragEndRow: () => void;
}

/**
 * Wires up the drag & drop reordering state for one tree.
 *
 * @param nodes       Flat hierarchy the tree renders (in render order).
 * @param onReparent  Pre-P1 callback; omitted disables plain reparenting.
 * @param onReorder   Positional callback; when given it takes precedence.
 */
export function useTreeDrag(
  nodes: readonly HierarchyRef[],
  onReparent?: (id: string, newParentId: string | null) => void,
  onReorder?: (
    id: string,
    newParentId: string | null,
    afterId: string | null | undefined,
  ) => void,
): TreeDragController {
  const dndEnabled = Boolean(onReparent || onReorder);
  const reorderEnabled = Boolean(onReorder);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);
  const [dropPosition, setDropPosition] = useState<TreeDropPosition | null>(
    null,
  );

  const parentById = useMemo((): Map<string, string | null> => {
    const map = new Map<string, string | null>();
    for (const n of nodes) map.set(n.id, n.parentId ?? null);
    return map;
  }, [nodes]);

  const resetDrag = useCallback((): void => {
    setDraggingId(null);
    setDropTargetId(null);
    setDropPosition(null);
  }, []);

  /**
   * Ids the in-flight node may not be dropped on: itself and its own subtree.
   * Recomputed per drag, not per dragover, so hovering a long list stays cheap.
   */
  const forbiddenDropTargetIds = useMemo((): Set<string> => {
    if (!draggingId) return new Set<string>();
    return collectSelfAndDescendantIds(nodes, draggingId);
  }, [nodes, draggingId]);

  const handleDragStart = useCallback(
    (e: ReactDragEvent, id: string): void => {
      e.dataTransfer?.setData('text/plain', id);
      if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move';
      setDraggingId(id);
    },
    [],
  );

  const handleDragOverTarget = useCallback(
    (e: ReactDragEvent, targetId: string): void => {
      // Not a drag we started, the row being dragged itself, or a row inside
      // its own subtree: leaving preventDefault() unset is what tells the
      // browser "not a drop target" (no highlight, no-drop cursor).
      if (!draggingId || forbiddenDropTargetIds.has(targetId)) return;
      e.preventDefault();
      if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
      setDropTargetId((prev) => (prev === targetId ? prev : targetId));
      setDropPosition(
        reorderEnabled
          ? dropPositionFromPointer(e.currentTarget, e.clientY)
          : 'inside',
      );
    },
    [draggingId, forbiddenDropTargetIds, reorderEnabled],
  );

  const handleDragLeaveTarget = useCallback(
    (e: ReactDragEvent, targetId: string): void => {
      // Native D&D fires dragleave when the pointer crosses onto a nested
      // child of the same row (chevron, label, badge) even though it is still
      // logically over that row — ignoring those keeps the drop-target
      // highlight from flickering through the whole drag.
      const related = e.relatedTarget as Node | null;
      if (related && e.currentTarget.contains(related)) return;
      setDropTargetId((prev) => (prev === targetId ? null : prev));
    },
    [],
  );

  /**
   * Applies the client-side no-op guards and forwards the move. Shared by the
   * pointer drop and the keyboard path so both swallow the same cases.
   * Returns whether a callback was invoked.
   */
  const reparent = useCallback(
    (draggedId: string, newParentId: string | null): boolean => {
      if (!draggedId) return false;
      if (onReorder) {
        // The dialog has no position control: append under the chosen parent.
        onReorder(draggedId, newParentId, undefined);
        return true;
      }
      if (!onReparent) return false;
      // Dropping onto the parent it already has moves nothing.
      if ((parentById.get(draggedId) ?? null) === newParentId) return false;
      // Moving a node onto itself or into its own subtree would close a cycle.
      // Detaching to root (newParentId === null) can never be a cycle.
      if (
        newParentId !== null &&
        collectSelfAndDescendantIds(nodes, draggedId).has(newParentId)
      ) {
        return false;
      }
      onReparent(draggedId, newParentId);
      return true;
    },
    [nodes, parentById, onReparent, onReorder],
  );

  /**
   * Forwards a positional move. The no-op/cycle guards live in
   * `predictReorder` (inside the tree's own wrapper), so the drag path and the
   * keyboard path cannot disagree about what a valid move is.
   */
  const handleDrop = useCallback(
    (e: ReactDragEvent, rowTargetId: string | null): void => {
      e.preventDefault();
      e.stopPropagation();
      const draggedId = e.dataTransfer?.getData('text/plain') || draggingId;
      const position = dropPositionFromPointer(e.currentTarget, e.clientY);
      resetDrag();
      if (!draggedId) return;

      if (onReorder) {
        const target =
          rowTargetId === null
            ? { newParentId: null, afterId: undefined }
            : resolveDropTarget(nodes, draggedId, rowTargetId, position);
        if (target) onReorder(draggedId, target.newParentId, target.afterId);
        return;
      }

      reparent(draggedId, rowTargetId);
    },
    [draggingId, nodes, onReorder, reparent, resetDrag],
  );

  const handleRootDragOver = useCallback((e: ReactDragEvent): void => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    setDropTargetId((prev) =>
      prev === ROOT_DROP_TARGET ? prev : ROOT_DROP_TARGET,
    );
    setDropPosition(null);
  }, []);

  const handleRootDragLeave = useCallback((e: ReactDragEvent): void => {
    const related = e.relatedTarget as Node | null;
    if (related && e.currentTarget.contains(related)) return;
    setDropTargetId((prev) => (prev === ROOT_DROP_TARGET ? null : prev));
  }, []);

  const handleRootDrop = useCallback(
    (e: ReactDragEvent): void => {
      // The root dropzone always means "top level"; with reorder enabled the
      // node is appended to the roots (an omitted `after_id`).
      handleDrop(e, null);
    },
    [handleDrop],
  );

  const rowDragProps = dndEnabled
    ? {
        draggingId,
        dropTargetId,
        dropPosition,
        onDragStartRow: handleDragStart,
        onDragOverRow: handleDragOverTarget,
        onDragLeaveRow: handleDragLeaveTarget,
        onDropRow: handleDrop,
        onDragEndRow: resetDrag,
      }
    : undefined;

  return {
    dndEnabled,
    draggingId,
    dropTargetId,
    dropPosition,
    rowDragProps,
    reparent,
    onRootDragOver: handleRootDragOver,
    onRootDragLeave: handleRootDragLeave,
    onRootDrop: handleRootDrop,
  };
}
