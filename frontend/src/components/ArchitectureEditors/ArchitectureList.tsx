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

import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { ArchitectureElement } from '../../types';
import { getAsilColor, getAsilBadgeStyle } from '../../utils/asilUtils';

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
  depth: number;
  onSelect: (id: string) => void;
  onAddChild: (parentId: string) => void;
  onDelete: (element: ArchitectureElement) => void;
  children?: TreeNode[];
}

function TreeItem({
  element,
  isSelected,
  depth,
  onSelect,
  onAddChild,
  onDelete,
  children = [],
}: TreeItemProps): JSX.Element {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(true);
  const hasChildren = children.length > 0;
  const indent = depth * 16; // 16px per level

  const elementTypeColor = getElementTypeColor(element.element_type);
  const asilColor = getAsilColor(element.asil_level ?? null);
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
          paddingTop: 'var(--space-2)',
          paddingBottom: 'var(--space-2)',
          marginBottom: 'var(--space-1)',
          background: isSelected ? 'var(--color-primary)' : 'transparent',
          color: isSelected ? '#ffffff' : 'var(--color-text)',
          borderRadius: 'var(--radius-md)',
          cursor: 'pointer',
          transition: 'var(--transition-fast)',
          fontSize: 'var(--font-size-sm)',
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
              setIsExpanded(!isExpanded);
            }}
            style={{
              border: 'none',
              background: 'transparent',
              cursor: 'pointer',
              fontSize: 'var(--font-size-sm)',
              color: 'inherit',
              padding: 0,
              width: '20px',
              height: '20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {isExpanded ? '▼' : '▶'}
          </button>
        )}
        {!hasChildren && <span style={{ width: '20px' }} />}

        {/* Element type badge */}
        <span
          style={{
            display: 'inline-block',
            background: elementTypeColor,
            color: '#ffffff',
            padding: '2px 6px',
            borderRadius: 'var(--radius-full)',
            fontSize: 'var(--font-size-xs)',
            fontWeight: 600,
            whiteSpace: 'nowrap',
            minWidth: '60px',
            textAlign: 'center',
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
              isSelected={isSelected === child.id}
              depth={depth + 1}
              onSelect={onSelect}
              onAddChild={onAddChild}
              onDelete={onDelete}
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
export function ArchitectureList({
  elements,
  selectedId,
  onSelect,
  onAddChild,
  onDelete,
  onReparent,
}: ArchitectureListProps): JSX.Element {
  // Build tree hierarchy
  const hierarchy = buildHierarchy(elements);

  return (
    <div style={{ overflow: 'auto', height: '100%' }}>
      {hierarchy.map((root) => (
        <TreeItem
          key={root.id}
          element={root}
          isSelected={selectedId === root.id}
          depth={0}
          onSelect={onSelect}
          onAddChild={onAddChild}
          onDelete={onDelete}
          children={root.children}
        />
      ))}
    </div>
  );
}

export default ArchitectureList;
