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
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { useVirtualizer } from '@tanstack/react-virtual';

// ---------------------------------------------------------------------------
// Level badge colors — design doc section 6
// ---------------------------------------------------------------------------

const LEVEL_BADGE_COLORS: Record<number, string> = {
  0: '#1E3A8A', // L0 dark blue
  1: '#3B82F6', // L1 blue
  2: '#06B6D4', // L2 cyan
  3: '#10B981', // L3 green
  4: '#9CA3AF', // L4 gray
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
  'data-testid'?: string;
}

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
    estimateSize: () => VIRTUAL_ROW_HEIGHT,
    overscan: 12,
  });

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
                  hasChildren={hasChildren}
                  isExpanded={isExpanded}
                  showLevelBadge={showLevelBadge}
                  onAddChild={onAddChild}
                  testIdPrefix={testId}
                  onSelect={onSelect}
                  onToggle={toggleExpand}
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
              hasChildren={hasChildren}
              isExpanded={isExpanded}
              showLevelBadge={showLevelBadge}
              onAddChild={onAddChild}
              testIdPrefix={testId}
              onSelect={onSelect}
              onToggle={toggleExpand}
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
  hasChildren: boolean;
  isExpanded: boolean;
  showLevelBadge: boolean;
  onAddChild?: (id: string) => void;
  testIdPrefix: string;
  onSelect: (id: string) => void;
  onToggle: (id: string) => void;
  /** REQ-091: extra positioning styles injected by the virtualizer. */
  rowStyle?: CSSProperties;
}

function TreeRow({
  node,
  depth,
  isSelected,
  hasChildren,
  isExpanded,
  showLevelBadge,
  onAddChild,
  testIdPrefix,
  onSelect,
  onToggle,
  rowStyle,
}: TreeRowProps): JSX.Element {
  return (
    <li
      role="treeitem"
      aria-selected={isSelected}
      aria-expanded={hasChildren ? isExpanded : undefined}
      data-testid={`${testIdPrefix}-node-${node.id}`}
      onClick={() => onSelect(node.id)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-1)',
        minHeight: '32px',
        padding: '4px 8px',
        paddingLeft: `${8 + depth * 16}px`,
        borderRadius: 'var(--radius-sm)',
        cursor: 'pointer',
        userSelect: 'none',
        background: isSelected ? 'var(--color-card-active-bg)' : 'transparent',
        borderLeft: isSelected
          ? '3px solid var(--color-primary)'
          : '3px solid transparent',
        color: 'var(--color-text)',
        transition: 'background var(--transition-fast)',
        boxSizing: 'border-box',
        ...rowStyle,
      }}
      onMouseEnter={(e) => {
        if (!isSelected) {
          (e.currentTarget as HTMLLIElement).style.background =
            'var(--color-surface-raised)';
        }
      }}
      onMouseLeave={(e) => {
        if (!isSelected) {
          (e.currentTarget as HTMLLIElement).style.background = 'transparent';
        }
      }}
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
