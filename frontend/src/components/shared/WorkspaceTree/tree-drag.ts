/**
 * WorkspaceTree — opt-in drag & drop reparenting (FE-01 extraction).
 *
 * Native HTML5 drag & drop, enabled only when a consumer passes `onReparent`.
 * Extracted from `workspace-tree.tsx` so the drag state machine, the cycle
 * guard and the row/root-dropzone wiring live in one place instead of being
 * interleaved with the tree's rendering. The row and root-dropzone *JSX* stays
 * in `workspace-tree.tsx` (the `ui-ratchet` design-system baseline is pinned to
 * that file), this module owns the behaviour behind it.
 *
 * Contract (unchanged from the in-component version):
 *   - `onReparent` is opt-in; without it nothing is draggable and no handlers
 *     are attached (see the prop docs in `workspace-tree.tsx`).
 *   - Dropping a node on itself, on its current parent or into its own subtree
 *     is swallowed here and never reaches the callback (see
 *     `collectSelfAndDescendantIds` — a cycle makes a subtree unreachable).
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

/**
 * Sentinel drop-target id for the root dropzone. Not a node id — node ids come
 * from the API, so a reserved non-UUID string cannot collide with one.
 */
export const ROOT_DROP_TARGET = '__root__';

export interface TreeDragController {
  /** True when the consumer opted in via `onReparent`. */
  dndEnabled: boolean;
  /** Id of the node currently being dragged, or `null`. */
  draggingId: string | null;
  /** Current drop target id; `ROOT_DROP_TARGET` marks the root dropzone. */
  dropTargetId: string | null;
  /** Row wiring, `undefined` when D&D is off (rows then render unchanged). */
  rowDragProps: TreeRowDragProps | undefined;
  /**
   * Shared move entry point for the pointer drop and the keyboard "Move…"
   * dialog. Runs the client-side guards and returns whether `onReparent` was
   * invoked (i.e. whether the move was forwarded).
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
  onDragStartRow: (e: ReactDragEvent, id: string) => void;
  onDragOverRow: (e: ReactDragEvent, id: string) => void;
  onDragLeaveRow: (e: ReactDragEvent, id: string) => void;
  onDropRow: (e: ReactDragEvent, newParentId: string | null) => void;
  onDragEndRow: () => void;
}

/**
 * Wires up the drag & drop reparenting state for one tree.
 *
 * @param nodes       Flat hierarchy the tree renders.
 * @param onReparent  Opt-in callback; omitting it disables D&D entirely.
 */
export function useTreeDrag(
  nodes: readonly HierarchyRef[],
  onReparent?: (id: string, newParentId: string | null) => void,
): TreeDragController {
  const dndEnabled = Boolean(onReparent);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dropTargetId, setDropTargetId] = useState<string | null>(null);

  const parentById = useMemo((): Map<string, string | null> => {
    const map = new Map<string, string | null>();
    for (const n of nodes) map.set(n.id, n.parentId ?? null);
    return map;
  }, [nodes]);

  const resetDrag = useCallback((): void => {
    setDraggingId(null);
    setDropTargetId(null);
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
    },
    [draggingId, forbiddenDropTargetIds],
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
   * Applies the client-side no-op guards and forwards the move to `onReparent`.
   *
   * Shared by the pointer drop and the keyboard "Move…" dialog so both paths
   * swallow exactly the same cases (same parent, the node itself, its own
   * subtree) instead of one of them drifting from the other. Returns whether
   * the callback was invoked.
   */
  const reparent = useCallback(
    (draggedId: string, newParentId: string | null): boolean => {
      if (!draggedId || !onReparent) return false;
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
    [nodes, parentById, onReparent],
  );

  const handleDrop = useCallback(
    (e: ReactDragEvent, newParentId: string | null): void => {
      e.preventDefault();
      e.stopPropagation();
      const draggedId = e.dataTransfer?.getData('text/plain') || draggingId;
      resetDrag();
      if (!draggedId) return;
      reparent(draggedId, newParentId);
    },
    [draggingId, resetDrag, reparent],
  );

  const handleRootDragOver = useCallback((e: ReactDragEvent): void => {
    e.preventDefault();
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
    setDropTargetId((prev) =>
      prev === ROOT_DROP_TARGET ? prev : ROOT_DROP_TARGET,
    );
  }, []);

  const handleRootDragLeave = useCallback((e: ReactDragEvent): void => {
    const related = e.relatedTarget as Node | null;
    if (related && e.currentTarget.contains(related)) return;
    setDropTargetId((prev) => (prev === ROOT_DROP_TARGET ? null : prev));
  }, []);

  const handleRootDrop = useCallback(
    (e: ReactDragEvent): void => {
      handleDrop(e, null);
    },
    [handleDrop],
  );

  const rowDragProps = dndEnabled
    ? {
        draggingId,
        dropTargetId,
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
    rowDragProps,
    reparent,
    onRootDragOver: handleRootDragOver,
    onRootDragLeave: handleRootDragLeave,
    onRootDrop: handleRootDrop,
  };
}
