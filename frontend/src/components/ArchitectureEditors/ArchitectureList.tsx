/**
 * ArchitectureList Component — REQ-L3-RF004-003, REQ-L1-084
 *
 * Displays a hierarchical list of architecture elements with:
 * - Indentation based on hierarchy level
 * - Element type badges
 * - ASIL level indicators
 * - Click to select for detail editing
 *
 * leaf_id: COMP-RF-004-List
 * req_id: REQ-L3-RF004-003, REQ-L1-084
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ArchitectureElement } from '../../types';
import { getAsilBadgeStyle } from '../../utils/asilUtils';

interface ArchitectureListProps {
  /**
   * All architecture elements to display.
   */
  elements: ArchitectureElement[];

  /**
   * Currently selected element ID.
   */
  selectedId?: string;

  /**
   * Callback when element is selected.
   */
  onSelect: (id: string) => void;

  /**
   * Callback to add a new child under a parent.
   */
  onAddChild: (parentId: string) => void;

  /**
   * Callback to delete an element.
   */
  onDelete: (element: ArchitectureElement) => void;

  /**
   * Callback to reparent an element.
   */
  onReparent: (elementId: string, newParentId: string | null) => void;
}

/**
 * Get element type badge color.
 */
function getElementTypeColor(type: string): string {
  switch (type) {
    case 'component':
      return '#3B82F6'; // blue
    case 'interface':
      return '#F97316'; // orange
    case 'subsystem':
      return '#8B5CF6'; // purple
    case 'layer':
      return '#10B981'; // green
    case 'module':
      return '#EC4899'; // pink
    default:
      return '#6B7280'; // gray
  }
}

/**
 * Build tree hierarchy from flat elements.
 * Returns array of root elements with children nested.
 */
interface TreeNode extends ArchitectureElement {
  children?: TreeNode[];
}

function buildHierarchy(elements: ArchitectureElement[]): TreeNode[] {
  const byId = new Map<string, TreeNode>(
    elements.map((el) => [el.id, { ...el, children: [] }])
  );
  const roots: TreeNode[] = [];

  for (const el of byId.values()) {
    if (!el.parent_id) {
      roots.push(el);
    } else {
      const parent = byId.get(el.parent_id);
      if (parent && parent.children) {
        parent.children.push(el);
      }
    }
  }

  return roots;
}

/**
 * Render tree item recursively with indentation.
 */
interface TreeItemProps {
  element: TreeNode;
  isSelected: boolean;
  /** Currently selected element id — needed to highlight nested children. */
  selectedId?: string;
  depth: number;
  onSelect: (id: string) => void;
  onAddChild: (parentId: string) => void;
  onDelete: (element: ArchitectureElement) => void;
  /** Ids collapsed by the user; lifted to the list so "collapse all" can reset them in one shot. */
  collapsedIds: ReadonlySet<string>;
  onToggleExpand: (id: string) => void;
  children?: TreeNode[];
}

function TreeItem({
  element,
  isSelected,
  selectedId,
  depth,
  onSelect,
  onAddChild,
  onDelete,
  collapsedIds,
  onToggleExpand,
  children = [],
}: TreeItemProps): JSX.Element {
  const { t } = useTranslation();
  const isExpanded = !collapsedIds.has(element.id);
  const hasChildren = children.length > 0;
  const indent = depth * 14; // 14px per level — keeps deep trees compact

  const elementTypeColor = getElementTypeColor(element.element_type);
  const asilBadge = getAsilBadgeStyle(element.asil_level ?? null);

  return (
    <div key={element.id}>
      {/* Tree item row */}
      <div
        onClick={() => onSelect(element.id)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          paddingLeft: `${indent}px`,
          paddingRight: 'var(--space-2)',
          paddingTop: 'var(--space-1)',
          paddingBottom: 'var(--space-1)',
          background: isSelected ? 'var(--color-primary)' : 'transparent',
          color: isSelected ? '#ffffff' : 'var(--color-text)',
          borderRadius: 'var(--radius-sm)',
          cursor: 'pointer',
          transition: 'var(--transition-fast)',
          fontSize: 'var(--font-size-sm)',
          lineHeight: 1.3,
        }}
        onMouseEnter={(e) => {
          if (!isSelected) {
            (e.currentTarget as HTMLDivElement).style.background = 'var(--color-surface-raised)';
          }
        }}
        onMouseLeave={(e) => {
          if (!isSelected) {
            (e.currentTarget as HTMLDivElement).style.background = 'transparent';
          }
        }}
      >
        {/* Expand/collapse toggle */}
        {hasChildren && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onToggleExpand(element.id);
            }}
            style={{
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              fontSize: 'var(--font-size-xs)',
              color: 'inherit',
              padding: 0,
              width: '16px',
              height: '16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {isExpanded ? '▼' : '▶'}
          </button>
        )}
        {!hasChildren && <span style={{ width: '16px', flexShrink: 0 }} />}

        {/* Element type badge */}
        <span
          style={{
            display: 'inline-block',
            background: elementTypeColor,
            color: '#ffffff',
            padding: '1px 5px',
            borderRadius: 'var(--radius-full)',
            fontSize: 'var(--font-size-xs)',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            textAlign: 'center',
            flexShrink: 0,
          }}
        >
          {element.element_type}
        </span>

        {/* Title */}
        <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {element.title || t('editor.untitled')}
        </span>

        {/* ASIL badge */}
        {element.asil_level && (
          <span
            style={{
              display: 'inline-block',
              background: asilBadge.background,
              color: asilBadge.text,
              padding: '2px 6px',
              borderRadius: 'var(--radius-full)',
              fontSize: 'var(--font-size-xs)',
              fontWeight: 600,
              whiteSpace: 'nowrap',
            }}
          >
            {element.asil_level}
          </span>
        )}

        {/* Level indicator */}
        <span
          style={{
            fontSize: 'var(--font-size-xs)',
            color: isSelected ? 'rgba(255,255,255,0.7)' : 'var(--color-text-muted)',
            whiteSpace: 'nowrap',
          }}
        >
          L{element.level ?? 0}
        </span>

        {/* Context menu (minimal) */}
        <div style={{ display: 'flex', gap: '4px' }}>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onAddChild(element.id);
            }}
            title={t('actions.new')}
            style={{
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              fontSize: 'var(--font-size-sm)',
              color: 'inherit',
              padding: '2px 4px',
            }}
          >
            +
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              onDelete(element);
            }}
            title={t('actions.delete')}
            style={{
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              fontSize: 'var(--font-size-sm)',
              color: 'inherit',
              padding: '2px 4px',
            }}
          >
            ✕
          </button>
        </div>
      </div>

      {/* Children (recursive) */}
      {hasChildren && isExpanded && (
        <div>
          {children.map((child) => (
            <TreeItem
              key={child.id}
              element={child}
              isSelected={selectedId === child.id}
              selectedId={selectedId}
              depth={depth + 1}
              onSelect={onSelect}
              onAddChild={onAddChild}
              onDelete={onDelete}
              collapsedIds={collapsedIds}
              onToggleExpand={onToggleExpand}
              children={child.children}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/**
 * ArchitectureList — implements REQ-L3-RF004-003
 *
 * Displays hierarchical list of architecture elements with
 * tree expand/collapse, type badges, and ASIL indicators.
 */
// onReparent stays in ArchitectureListProps for callers; drag&drop reparenting
// is not implemented in this list yet, so it is not destructured here.
export function ArchitectureList({
  elements,
  selectedId,
  onSelect,
  onAddChild,
  onDelete,
}: ArchitectureListProps): JSX.Element {
  const { t } = useTranslation();
  // Build tree hierarchy
  const hierarchy = useMemo(() => buildHierarchy(elements), [elements]);
  const [collapsedIds, setCollapsedIds] = useState<ReadonlySet<string>>(new Set());

  const parentIds = useMemo(
    () => new Set(elements.filter((el) => el.parent_id).map((el) => el.parent_id as string)),
    [elements]
  );

  const toggleExpand = (id: string): void => {
    setCollapsedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  return (
    <div style={{ overflow: 'auto', height: '100%' }}>
      {parentIds.size > 0 && (
        <div
          style={{
            display: 'flex',
            justifyContent: 'flex-end',
            gap: 'var(--space-2)',
            marginBottom: 'var(--space-1)',
          }}
        >
          <button
            onClick={() => setCollapsedIds(new Set())}
            style={{
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              fontSize: 'var(--font-size-xs)',
              color: 'var(--color-text-muted)',
              padding: '2px 4px',
            }}
          >
            {t('actions.expandAll', 'Alle ausklappen')}
          </button>
          <button
            onClick={() => setCollapsedIds(parentIds)}
            style={{
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              fontSize: 'var(--font-size-xs)',
              color: 'var(--color-text-muted)',
              padding: '2px 4px',
            }}
          >
            {t('actions.collapseAll', 'Alle einklappen')}
          </button>
        </div>
      )}
      {hierarchy.map((root) => (
        <TreeItem
          key={root.id}
          element={root}
          isSelected={selectedId === root.id}
          selectedId={selectedId}
          depth={0}
          onSelect={onSelect}
          onAddChild={onAddChild}
          onDelete={onDelete}
          collapsedIds={collapsedIds}
          onToggleExpand={toggleExpand}
          children={root.children}
        />
      ))}
    </div>
  );
}

export default ArchitectureList;
