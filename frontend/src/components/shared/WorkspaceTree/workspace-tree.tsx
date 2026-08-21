/**
 * WorkspaceTree — shared compact tree navigation component (REQ-003).
 *
 * leaf_id: COMP-RF-TREE-001
 * req_id:  REQ-003 (Einheitliches Tree-Modul für alle Ansichten)
 *
 * Design reference: docs/architecture/DESIGN_TREE_VIEW_L0_L4_HIERARCHY.md
 *
 * Used across all artifact views (Bedarfe, Anforderungen, Architektur,
 * ADRs, Risiken, Probleme, Testfälle) for a consistent left-panel
 * navigation with compact tree rows, expand/collapse, optional search,
 * level badges (Architecture) and status badges (all other views).
 *
 * Key behaviors (design doc §3–6):
 *   - Expand/Collapse via ▶ icon (rotates 90° when expanded)
 *   - Click-to-select with translucent primary bg + left border highlight
 *   - Hover: var(--color-surface-raised) background
 *   - Optional built-in search (300ms debounce); parents stay visible
 *   - Optional L0-L4 level badge with design-doc colors (showLevelBadge)
 *   - Optional status/type badge per node (node.badge)
 *   - Optional "+ child" button per node (onAddChild — Architecture use)
 *   - ARIA: role="tree" / role="treeitem" / aria-expanded / aria-selected
 */

import {
  type CSSProperties,
  type DragEvent as ReactDragEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';
import { collectSelfAndDescendantIds } from './tree-hierarchy';
import styles from './workspace-tree.module.css';

// ---------------------------------------------------------------------------
// Level badge colors — design doc section 6
// ---------------------------------------------------------------------------

// Theming phase 2, checkpoint 1: migrated onto the --color-level-* design
// tokens (tokens.css) where an existing --palette-* primitive was a close
// enough match. L2 (cyan) has no close primitive in the current palette
// (nearest, emerald-400, is a visibly different hue) and is intentionally
// left as a raw hex literal here rather than force a wrong-looking match —
// see the checkpoint-1 report for the full color-distance analysis.
const LEVEL_BADGE_COLORS: Record<number, string> = {
  0: 'var(--color-level-l0)', // L0 dark blue
  1: 'var(--color-level-l1)', // L1 blue
  2: '#06B6D4', // L2 cyan — no matching token yet, see comment above
  3: 'var(--color-level-l3)', // L3 green
  4: 'var(--color-level-l4)', // L4 gray
};

function levelBadgeColor(levelStr: string): string {
  const num = parseInt(levelStr.replace(/^L/i, ''), 10);
  return LEVEL_BADGE_COLORS[Math.min(Math.max(isNaN(num) ? 0 : num, 0), 4)];
}

// ---------------------------------------------------------------------------
// Type badge abbreviation map — REQ-007
// ---------------------------------------------------------------------------

/** Maps verbose type/element strings to short badge labels (REQ-007). */
const TYPE_BADGE_ABBREVIATION: Readonly<Record<string, string>> = {
  // Requirement types (backend values)
  SyReq: 'SR',
  UseCase: 'UC',
  FeatureReq: 'FR',
  // Legacy requirement types, kept so historical rows still render a badge.
  SWReq: 'SW',
  HWReq: 'HW',
  // Requirement types (long-form display names)
  SysRec: 'SR',
  Stakeholder: 'SH',
  Hardware: 'HW',
  Software: 'SW',
  Interface: 'IF',
  Performance: 'PF',
  Safety: 'SA',
  Security: 'SEC',
  // Architecture element types (backend values)
  component: 'C',
  interface: 'IF',
  subsystem: 'SS',
  layer: 'LY',
  module: 'MOD',
  // Architecture element types (display names)
  System: 'SYS',
  Subsystem: 'SS',
  Component: 'C',
  Function: 'FN',
} as const;

/**
 * Returns a short badge abbreviation for the given type string.
 * Falls back to the original string if no mapping exists.
 *
 * @param type - Raw type or element_type string from the API.
 * @returns Short abbreviation, e.g. 'SR', 'C', 'SS'.
 */
export function getTypeBadgeAbbreviation(type: string): string {
  return (TYPE_BADGE_ABBREVIATION as Record<string, string>)[type] ?? type;
}

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

/**
 * A single navigable item in the tree.
 * Hierarchy is expressed via parentId — WorkspaceTree builds the tree
 * from the flat list, matching the API's parent_id pattern.
 */
export interface WorkspaceTreeNode {
  id: string;
  name: string;
  parentId: string | null;
  /** Architecture level string, e.g. "L0", "L1". Required for showLevelBadge. */
  level?: string;
  /** Optional badge shown right of the name (status, type, …). */
  badge?: {
    text: string;
    /** CSS background color or variable, e.g. 'var(--color-badge-success-bg)'. */
    bg: string;
    /** CSS text color or variable. */
    color: string;
    /**
     * Spelled-out meaning of `text` (e.g. "System Requirement (SyReq)" for
     * the "SR" abbreviation) shown as a native tooltip and exposed to
     * screen readers (issue #169). Falls back to `text` when omitted.
     */
    title?: string;
  };
}

export interface WorkspaceTreeProps {
  /** Flat list of nodes — WorkspaceTree builds the tree via parentId. */
  nodes: WorkspaceTreeNode[];
  selectedId?: string;
  onSelect: (id: string) => void;
  /**
   * If provided, each tree row shows a small "+" button to add a child
   * under that node. Used by the Architecture view.
   */
  onAddChild?: (id: string) => void;
  /**
   * Show L0-L4 colored level badge (right of name).
   * Uses node.level string. Default: false.
   */
  showLevelBadge?: boolean;
  /**
   * Render a built-in debounced search box above the tree.
   * Set to false when the parent view already provides search (via ListToolbar).
   * Default: true.
   */
  showSearch?: boolean;
  searchPlaceholder?: string;
  emptyLabel?: string;
  noMatchesLabel?: string;
  /**
   * REQ-091: Opt-in list virtualization for large artifact lists.
   * When true and the number of visible rows exceeds the threshold, rows are
   * rendered through @tanstack/react-virtual so only on-screen rows hit the DOM.
   * Small lists fall back to normal rendering (no layout change). Default: false.
   */
  virtualize?: boolean;
  /**
   * Task 3.1: optional per-row content override. When provided, replaces
   * the tree's default name+badge label with custom content (e.g. an
   * `<ArtifactRow>`) while TreeRow keeps owning the chrome that makes this
   * a *tree* — the expand/collapse chevron, depth indent and click-to-select.
   * Purely additive: callers that omit this prop (Architecture, Needs,
   * Goals) render exactly as before.
   */
  renderRow?: (node: WorkspaceTreeNode, ctx: { isSelected: boolean }) => ReactNode;
  /**
   * Task 3.1: overrides the virtualizer's fixed row-height estimate
   * (`VIRTUAL_ROW_HEIGHT`, tuned for the default single-line label). A
   * `renderRow` override that is visually taller — e.g. `<ArtifactRow>`'s
   * two-line id/title layout — MUST pass a matching estimate here, or
   * absolutely-positioned virtualized rows will overlap once the list
   * exceeds `VIRTUALIZE_THRESHOLD`. No effect when `virtualize` is unset.
   */
  virtualRowHeight?: number;
  /**
   * Opt-in drag & drop reparenting (user decision 2026-08-15). When provided,
   * every row becomes draggable and a drop target, and a root dropzone appears
   * above the tree for the duration of a drag (drop there = detach to root).
   *
   * Called with the dragged node's id and the id of its new parent, `null`
   * meaning "no parent / root level". Three cases are swallowed here as
   * impossible or meaningless and never reach the callback:
   *   - dropping a node on itself,
   *   - dropping it on the parent it already has,
   *   - dropping it into its own subtree (would close a cycle — see
   *     `collectSelfAndDescendantIds`; those rows are not offered as drop
   *     targets in the first place).
   *
   * The cycle rule is structural, not artifact-specific: a node inside its own
   * subtree has no path to any root, so `buildInternalTree` would drop the
   * whole subtree from the view. It therefore applies to every consumer and is
   * not configurable.
   *
   * Everything else — level ordering, single-root rules, permissions — belongs
   * to the caller and its backend; the drop is forwarded and the caller
   * surfaces any rejection.
   *
   * Strictly additive: consumers that omit this prop render exactly the DOM
   * they rendered before (no `draggable` attribute, no dropzone, no handlers).
   */
  onReparent?: (id: string, newParentId: string | null) => void;
  /**
   * Label inside the root dropzone. Only used when `onReparent` is set;
   * translated by the caller (WorkspaceTree carries no i18n of its own).
   */
  rootDropzoneLabel?: string;
  'data-testid'?: string;
}

/**
 * Sentinel drop-target id for the root dropzone. Not a node id — node ids come
 * from the API, so a reserved non-UUID string cannot collide with one.
 */
const ROOT_DROP_TARGET = '__root__';

// REQ-091: virtualization threshold 100 items
const VIRTUALIZE_THRESHOLD = 100;
// REQ-091: fixed row height estimate — TreeRow minHeight 32px + 2px list gap.
const VIRTUAL_ROW_HEIGHT = 34;

// ---------------------------------------------------------------------------
// Internal tree model
// ---------------------------------------------------------------------------

interface InternalNode {
  node: WorkspaceTreeNode;
  children: InternalNode[];
  depth: number;
}

function buildInternalTree(nodes: WorkspaceTreeNode[]): InternalNode[] {
  const byId = new Map<string, WorkspaceTreeNode>();
  for (const n of nodes) byId.set(n.id, n);

  const childrenByParent = new Map<string | null, WorkspaceTreeNode[]>();
  for (const n of nodes) {
    const parentKey =
      n.parentId && byId.has(n.parentId) ? n.parentId : null;
    const bucket = childrenByParent.get(parentKey);
    if (bucket) bucket.push(n);
    else childrenByParent.set(parentKey, [n]);
  }

  const toInternal = (
    n: WorkspaceTreeNode,
    depth: number,
    seen: Set<string>,
  ): InternalNode => {
    seen.add(n.id);
    const kids = (childrenByParent.get(n.id) ?? []).filter(
      (c) => !seen.has(c.id),
    );
    return {
      node: n,
      depth,
      children: kids.map((c) => toInternal(c, depth + 1, seen)),
    };
  };

  const seen = new Set<string>();
  return (childrenByParent.get(null) ?? []).map((root) =>
    toInternal(root, 0, seen),
  );
}

interface FlatRow {
  internal: InternalNode;
  hasChildren: boolean;
  isExpanded: boolean;
}

function flattenVisible(
  roots: InternalNode[],
  expanded: Set<string>,
  visibleIds: Set<string> | null,
  out: FlatRow[] = [],
): FlatRow[] {
  for (const internal of roots) {
    if (visibleIds !== null && !visibleIds.has(internal.node.id)) continue;
    const visibleChildren =
      visibleIds === null
        ? internal.children
        : internal.children.filter((c) => visibleIds.has(c.node.id));
    const hasChildren = visibleChildren.length > 0;
    // While searching, matched subtrees are force-expanded.
    const isExpanded = visibleIds !== null ? true : expanded.has(internal.node.id);
    out.push({ internal, hasChildren, isExpanded });
    if (hasChildren && isExpanded) {
      flattenVisible(internal.children, expanded, visibleIds, out);
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// WorkspaceTree
// ---------------------------------------------------------------------------

export function WorkspaceTree({
  nodes,
  selectedId,
  onSelect,
  onAddChild,
  showLevelBadge = false,
  showSearch = true,
  searchPlaceholder = 'Search...',
  emptyLabel = 'No items.',
  noMatchesLabel = 'No matches found.',
  virtualize = false,
  renderRow,
  virtualRowHeight,
  onReparent,
  rootDropzoneLabel = 'Drop here to make root',
  'data-testid': testId = 'workspace-tree',
}: WorkspaceTreeProps): JSX.Element {
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const didInitRef = useRef(false);

  const tree = useMemo(() => buildInternalTree(nodes), [nodes]);

  // Auto-expand root nodes on first data load (design doc §7 step 1).
  useEffect(() => {
    if (didInitRef.current || tree.length === 0) return;
    didInitRef.current = true;
    setExpanded(new Set(tree.map((n) => n.node.id)));
  }, [tree]);

  // 300ms debounce on search input (design doc §4 — type_in_search_field).
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setSearchQuery(searchInput), 300);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [searchInput]);

  // Compute visible node set: matching nodes + all their ancestors.
  const visibleIds = useMemo((): Set<string> | null => {
    const q = searchQuery.trim().toLowerCase();
    if (!q) return null;
    const idSet = new Set(nodes.map((n) => n.id));
    const parentById = new Map<string, string | null>();
    for (const n of nodes) {
      parentById.set(
        n.id,
        n.parentId && idSet.has(n.parentId) ? n.parentId : null,
      );
    }
    const visible = new Set<string>();
    for (const n of nodes) {
      if (!n.name.toLowerCase().includes(q)) continue;
      let cursor: string | null = n.id;
      while (cursor && !visible.has(cursor)) {
        visible.add(cursor);
        cursor = parentById.get(cursor) ?? null;
      }
    }
    return visible;
  }, [nodes, searchQuery]);

  const visibleRows = useMemo(
    () => flattenVisible(tree, expanded, visibleIds),
    [tree, expanded, visibleIds],
  );

  const toggleExpand = useCallback((id: string): void => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // REQ-091: virtualize only when opted in and the visible list is large.
  const parentRef = useRef<HTMLDivElement>(null);
  const useVirtual = virtualize && visibleRows.length > VIRTUALIZE_THRESHOLD;
  const rowVirtualizer = useVirtualizer({
    count: visibleRows.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => virtualRowHeight ?? VIRTUAL_ROW_HEIGHT,
    overscan: 12,
  });

  // -------------------------------------------------------------------
  // Task 4.1: ARIA treeview keyboard navigation (roving tabindex).
  // Design ref: docs §12.5 — ↑ ↓ → ← Home End, letter-jump, Enter, *.
  // -------------------------------------------------------------------
  const [focusedId, setFocusedId] = useState<string | null>(null);
  // Maps node id -> mounted <li> element. Entries appear/disappear as the
  // virtualizer mounts/unmounts rows outside its visible window.
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
      if (visibleRows.length === 0) return;
      const currentId = focusedId ?? selectedId ?? visibleRows[0].internal.node.id;
      const currentIndex = visibleRows.findIndex((r) => r.internal.node.id === currentId);
      const safeIndex = currentIndex === -1 ? 0 : currentIndex;
      const currentRow = visibleRows[safeIndex];

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          focusRowAtIndex(Math.min(safeIndex + 1, visibleRows.length - 1));
          break;
        case 'ArrowUp':
          e.preventDefault();
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
          // Same activation the row's onClick already performs.
          e.preventDefault();
          onSelect(currentRow.internal.node.id);
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
    [visibleRows, focusedId, selectedId, toggleExpand, onSelect, focusRowAtIndex],
  );

  // -------------------------------------------------------------------
  // Drag & drop reparenting (opt-in via onReparent) — native HTML5 D&D.
  // -------------------------------------------------------------------
  const dndEnabled = Boolean(onReparent);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  // Current drop target; ROOT_DROP_TARGET marks the root dropzone.
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

  const handleDrop = useCallback(
    (e: ReactDragEvent, newParentId: string | null): void => {
      e.preventDefault();
      e.stopPropagation();
      const draggedId = e.dataTransfer?.getData('text/plain') || draggingId;
      resetDrag();
      if (!draggedId || !onReparent) return;
      // Dropping onto the parent it already has moves nothing.
      if ((parentById.get(draggedId) ?? null) === newParentId) return;
      // Dropping a node on itself or into its own subtree would close a cycle.
      // Recomputed from the id that actually arrived rather than reusing
      // `forbiddenDropTargetIds`, which is keyed on the drag we started.
      // Detaching to root (newParentId === null) can never be a cycle.
      if (
        newParentId !== null &&
        collectSelfAndDescendantIds(nodes, draggedId).has(newParentId)
      ) {
        return;
      }
      onReparent(draggedId, newParentId);
    },
    [draggingId, nodes, parentById, resetDrag, onReparent],
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

  return (
    <div
      data-testid={testId}
      style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}
    >
      {showSearch && (
        <input
          type="search"
          data-testid={`${testId}-search`}
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          style={{
            height: '32px',
            borderRadius: 'var(--radius-sm)',
            border: '1px solid var(--color-border)',
            padding: '0 var(--space-2)',
            fontSize: 'var(--font-size-sm)',
            fontFamily: 'inherit',
            background: 'var(--color-surface)',
            color: 'var(--color-text)',
            boxSizing: 'border-box',
            width: '100%',
            outline: 'none',
          }}
        />
      )}

      {/* Root dropzone — only mounted while a drag is in flight. Dropping
          here detaches the dragged node to root level (parent = null). */}
      {dndEnabled && draggingId && (
        <div
          data-testid={`${testId}-root-dropzone`}
          className={`${styles.rootDropzone}${
            dropTargetId === ROOT_DROP_TARGET ? ` ${styles.rootDropzoneActive}` : ''
          }`}
          onDragOver={(e) => {
            e.preventDefault();
            if (e.dataTransfer) e.dataTransfer.dropEffect = 'move';
            setDropTargetId((prev) =>
              prev === ROOT_DROP_TARGET ? prev : ROOT_DROP_TARGET,
            );
          }}
          onDragLeave={(e) => {
            const related = e.relatedTarget as Node | null;
            if (related && e.currentTarget.contains(related)) return;
            setDropTargetId((prev) => (prev === ROOT_DROP_TARGET ? null : prev));
          }}
          onDrop={(e) => handleDrop(e, null)}
        >
          {rootDropzoneLabel}
        </div>
      )}

      {nodes.length === 0 ? (
        <p
          data-testid={`${testId}-empty`}
          style={{
            color: 'var(--color-text-muted)',
            fontSize: 'var(--font-size-sm)',
            margin: 0,
          }}
        >
          {emptyLabel}
        </p>
      ) : visibleRows.length === 0 ? (
        <p
          data-testid={`${testId}-no-matches`}
          style={{
            color: 'var(--color-text-muted)',
            fontSize: 'var(--font-size-sm)',
            margin: 0,
          }}
        >
          {noMatchesLabel}
        </p>
      ) : useVirtual ? (
        // REQ-091: virtualized rendering — only on-screen rows hit the DOM.
        <div
          ref={parentRef}
          data-testid={`${testId}-scroll`}
          style={{ overflowY: 'auto', maxHeight: '70vh' }}
        >
          <ul
            role="tree"
            data-testid={`${testId}-list`}
            onKeyDown={handleTreeKeyDown}
            style={{
              listStyle: 'none',
              padding: 0,
              margin: 0,
              position: 'relative',
              height: `${rowVirtualizer.getTotalSize()}px`,
            }}
          >
            {rowVirtualizer.getVirtualItems().map((virtualRow) => {
              const { internal, hasChildren, isExpanded } =
                visibleRows[virtualRow.index];
              return (
                <TreeRow
                  key={internal.node.id}
                  node={internal.node}
                  depth={internal.depth}
                  isSelected={internal.node.id === selectedId}
                  isFocused={internal.node.id === effectiveFocusedId}
                  hasChildren={hasChildren}
                  isExpanded={isExpanded}
                  showLevelBadge={showLevelBadge}
                  onAddChild={onAddChild}
                  renderRow={renderRow}
                  testIdPrefix={testId}
                  onSelect={onSelect}
                  onToggle={toggleExpand}
                  onRowRef={registerRowRef}
                  onFocusRow={setFocusedId}
                  dragProps={rowDragProps}
                  rowStyle={{
                    position: 'absolute',
                    top: 0,
                    left: 0,
                    width: '100%',
                    transform: `translateY(${virtualRow.start}px)`,
                  }}
                />
              );
            })}
          </ul>
        </div>
      ) : (
        <ul
          role="tree"
          data-testid={`${testId}-list`}
          onKeyDown={handleTreeKeyDown}
          style={{
            listStyle: 'none',
            padding: 0,
            margin: 0,
            display: 'flex',
            flexDirection: 'column',
            gap: '2px',
          }}
        >
          {visibleRows.map(({ internal, hasChildren, isExpanded }) => (
            <TreeRow
              key={internal.node.id}
              node={internal.node}
              depth={internal.depth}
              isSelected={internal.node.id === selectedId}
              isFocused={internal.node.id === effectiveFocusedId}
              hasChildren={hasChildren}
              isExpanded={isExpanded}
              showLevelBadge={showLevelBadge}
              onAddChild={onAddChild}
              renderRow={renderRow}
              testIdPrefix={testId}
              onSelect={onSelect}
              onToggle={toggleExpand}
              onRowRef={registerRowRef}
              onFocusRow={setFocusedId}
              dragProps={rowDragProps}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TreeRow — single row in the tree
// ---------------------------------------------------------------------------

interface TreeRowProps {
  node: WorkspaceTreeNode;
  depth: number;
  isSelected: boolean;
  /** Task 4.1: roving-tabindex focus target — true for at most one row. */
  isFocused: boolean;
  hasChildren: boolean;
  isExpanded: boolean;
  showLevelBadge: boolean;
  onAddChild?: (id: string) => void;
  /** Task 3.1: custom row content override — see `WorkspaceTreeProps.renderRow`. */
  renderRow?: (node: WorkspaceTreeNode, ctx: { isSelected: boolean }) => ReactNode;
  testIdPrefix: string;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  /**
   * Task 4.1: registers/unregisters this row's <li> DOM node with the
   * parent's roving-tabindex focus manager. Called with `null` on unmount
   * (e.g. when the virtualizer windows the row out of the DOM).
   */
  onRowRef: (id: string, el: HTMLLIElement | null) => void;
  /** Task 4.1: moves roving-tabindex focus to this row (click-to-focus). */
  onFocusRow: (id: string) => void;
  /**
   * Drag & drop reparenting wiring. `undefined` when the consumer did not
   * opt in via `onReparent` — the row then renders without any drag
   * attributes or handlers at all, exactly as before.
   */
  dragProps?: TreeRowDragProps;
  /** REQ-091: extra positioning styles injected by the virtualizer. */
  rowStyle?: CSSProperties;
}

/** Drag & drop wiring handed down from WorkspaceTree to each row. */
interface TreeRowDragProps {
  draggingId: string | null;
  dropTargetId: string | null;
  onDragStartRow: (e: ReactDragEvent, id: string) => void;
  onDragOverRow: (e: ReactDragEvent, id: string) => void;
  onDragLeaveRow: (e: ReactDragEvent, id: string) => void;
  onDropRow: (e: ReactDragEvent, newParentId: string | null) => void;
  onDragEndRow: () => void;
}

function TreeRow({
  node,
  depth,
  isSelected,
  isFocused,
  hasChildren,
  isExpanded,
  showLevelBadge,
  onAddChild,
  renderRow,
  testIdPrefix,
  onSelect,
  onToggle,
  onRowRef,
  onFocusRow,
  dragProps,
  rowStyle,
}: TreeRowProps): JSX.Element {
  // Task 3.1: when a custom row renderer is used (e.g. <ArtifactRow>), it
  // owns its own selected background/left-edge accent and hover state, so
  // the <li> chrome around it stays neutral to avoid a double highlight.
  const hasCustomRow = Boolean(renderRow);

  const isDragging = dragProps?.draggingId === node.id;
  const isDropTarget = Boolean(dragProps) && dragProps!.dropTargetId === node.id;
  // Highlight lives in the CSS module, not inline: the <li>'s inline styles
  // already own background/border-left, and an inline rule would win over a
  // class. `outline`/`opacity` are untouched inline, so the class applies.
  const dragClassName =
    [isDropTarget ? styles.dropTarget : '', isDragging ? styles.dragging : '']
      .filter(Boolean)
      .join(' ') || undefined;

  return (
    <li
      ref={(el) => onRowRef(node.id, el)}
      role="treeitem"
      aria-selected={isSelected}
      aria-expanded={hasChildren ? isExpanded : undefined}
      tabIndex={isFocused ? 0 : -1}
      data-testid={`${testIdPrefix}-node-${node.id}`}
      className={dragClassName}
      draggable={dragProps ? true : undefined}
      data-dragging={isDragging ? 'true' : undefined}
      data-drop-target={isDropTarget ? 'true' : undefined}
      onDragStart={
        dragProps ? (e) => dragProps.onDragStartRow(e, node.id) : undefined
      }
      onDragEnd={dragProps ? () => dragProps.onDragEndRow() : undefined}
      onDragOver={
        dragProps ? (e) => dragProps.onDragOverRow(e, node.id) : undefined
      }
      onDragLeave={
        dragProps ? (e) => dragProps.onDragLeaveRow(e, node.id) : undefined
      }
      onDrop={dragProps ? (e) => dragProps.onDropRow(e, node.id) : undefined}
      onClick={() => {
        onSelect(node.id);
        onFocusRow(node.id);
      }}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-1)',
        minHeight: '32px',
        padding: hasCustomRow ? '0 8px' : '4px 8px',
        paddingLeft: `${8 + depth * 16}px`,
        borderRadius: 'var(--radius-sm)',
        cursor: 'pointer',
        userSelect: 'none',
        background: !hasCustomRow && isSelected ? 'var(--color-card-active-bg)' : 'transparent',
        borderLeft:
          !hasCustomRow && isSelected
            ? '3px solid var(--color-primary)'
            : '3px solid transparent',
        color: 'var(--color-text)',
        transition: 'background var(--transition-fast)',
        boxSizing: 'border-box',
        ...rowStyle,
      }}
      onMouseEnter={
        hasCustomRow
          ? undefined
          : (e) => {
              if (!isSelected) {
                (e.currentTarget as HTMLLIElement).style.background =
                  'var(--color-surface-raised)';
              }
            }
      }
      onMouseLeave={
        hasCustomRow
          ? undefined
          : (e) => {
              if (!isSelected) {
                (e.currentTarget as HTMLLIElement).style.background = 'transparent';
              }
            }
      }
    >
      {/* Expand / collapse toggle — rotate 90° when expanded (design doc §6) */}
      {hasChildren ? (
        <button
          type="button"
          data-testid={`${testIdPrefix}-toggle-${node.id}`}
          aria-label={isExpanded ? 'Collapse' : 'Expand'}
          onClick={(e) => {
            e.stopPropagation();
            onToggle(node.id);
          }}
          style={{
            width: '16px',
            height: '16px',
            padding: 0,
            border: 'none',
            background: 'transparent',
            color: 'var(--color-text-muted)',
            cursor: 'pointer',
            fontSize: '0.65rem',
            lineHeight: 1,
            flexShrink: 0,
            transform: isExpanded ? 'rotate(90deg)' : 'rotate(0deg)',
            transition: `transform var(--transition-fast)`,
          }}
        >
          ▶
        </button>
      ) : (
        <span aria-hidden="true" style={{ width: '16px', flexShrink: 0 }} />
      )}

      {hasCustomRow ? (
        // Task 3.1: custom row content (e.g. <ArtifactRow>) replaces the
        // default name+badge label. The chevron above and depth indent
        // already applied via the <li> padding are the only tree chrome.
        <div className={styles.customRowSlot} data-testid={`${testIdPrefix}-row-${node.id}`}>
          {renderRow!(node, { isSelected })}
        </div>
      ) : (
        <>
          {/* Node name */}
          <span
            style={{
              flex: 1,
              minWidth: 0,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              fontSize: 'var(--font-size-sm)',
              fontWeight: isSelected ? 600 : 400,
            }}
            title={node.name}
          >
            {node.name}
          </span>

          {/* Status / type badge (node.badge) */}
          {node.badge && (
            <span
              data-testid={`${testIdPrefix}-badge-${node.id}`}
              title={node.badge.title ?? node.badge.text}
              aria-label={node.badge.title ?? node.badge.text}
              style={{
                flexShrink: 0,
                fontSize: '0.7rem',
                padding: '1px 6px',
                borderRadius: 'var(--radius-full)',
                background: node.badge.bg,
                color: node.badge.color,
                fontWeight: 500,
                lineHeight: '16px',
                whiteSpace: 'nowrap',
              }}
            >
              {node.badge.text}
            </span>
          )}

          {/* Level badge L0-L4 (design doc §6 — level_badge colors) */}
          {showLevelBadge && node.level && (
            <span
              data-testid={`${testIdPrefix}-level-${node.id}`}
              style={{
                flexShrink: 0,
                fontSize: '12px',
                padding: '1px 6px',
                borderRadius: 'var(--radius-full)',
                background: levelBadgeColor(node.level),
                color: 'white',
                fontWeight: 600,
                lineHeight: '16px',
                whiteSpace: 'nowrap',
              }}
            >
              {node.level}
            </span>
          )}
        </>
      )}

      {/* Add-child button — Architecture view only (onAddChild prop) */}
      {onAddChild && (
        <button
          type="button"
          data-testid={`${testIdPrefix}-add-child-${node.id}`}
          aria-label="Add child"
          title="Add child"
          onClick={(e) => {
            e.stopPropagation();
            onAddChild(node.id);
          }}
          style={{
            width: '18px',
            height: '18px',
            padding: 0,
            border: 'none',
            background: 'transparent',
            color: 'var(--color-text-muted)',
            cursor: 'pointer',
            fontSize: '0.9rem',
            lineHeight: 1,
            flexShrink: 0,
            borderRadius: 'var(--radius-sm)',
          }}
        >
          +
        </button>
      )}
    </li>
  );
}
