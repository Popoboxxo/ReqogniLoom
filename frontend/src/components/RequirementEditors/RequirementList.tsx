/**
 * REQ-L3-RF003-005: RequirementList Component
 *
 * Renders a searchable/filterable list of requirements with:
 * - Type badge (StReq, SyReq, etc.)
 * - Status badge
 * - Search/Filter/Sort via ListToolbar
 * - Click to select
 * - Delete button
 *
 * leaf_id: COMP-RF-003-RequirementList
 * req_id: REQ-L3-RF003-001, REQ-L3-RF003-004
 *
 * Interfaces implemented:
 * IF-RF-INT-001 ← Activation from NavigationShell
 * IF-RF-INT-003 ← artifact_id URL params
 * IF-RF-EXT-OUT-001 → GET/DELETE /api/v1/requirements/
 */

import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { ListToolbar } from '../shared/ListToolbar';
import { Requirement, RequirementType, UUID } from '../../types';
import { REQ_CATEGORIES, WORKFLOW_STATES } from '../../types';

/**
 * Props for RequirementList component.
 */
interface RequirementListProps {
  requirements: Requirement[];
  selectedId?: string;
  onSelect: (id: UUID) => void;
  onDelete: (id: UUID) => void;
  onCreateNew: () => void;
  isCreating?: boolean;
}

/**
 * Get badge styling based on requirement status.
 */
function getStatusBadgeStyle(status: string): React.CSSProperties {
  const base: React.CSSProperties = {
    borderRadius: 'var(--radius-full)',
    fontSize: 'var(--font-size-sm)',
    padding: '2px 8px',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  };
  switch (status) {
    case 'approved':
      return {
        ...base,
        background: 'var(--color-badge-approved)',
        color: 'var(--color-badge-approved-text)',
      };
    case 'review':
      return {
        ...base,
        background: '#bee3f8',
        color: '#2c5282',
      };
    case 'rejected':
    case 'deprecated':
      return {
        ...base,
        background: '#fed7d7',
        color: '#9b2c2c',
      };
    default:
      return {
        ...base,
        background: 'var(--color-badge-draft)',
        color: 'var(--color-badge-draft-text)',
      };
  }
}

/**
 * Get badge color for requirement type.
 */
function getTypeColor(type?: RequirementType): string {
  switch (type) {
    case 'SyReq':
      return '#10B981'; // Green
    case 'SWReq':
      return '#8B5CF6'; // Purple
    case 'HWReq':
      return '#F59E0B'; // Amber
    default:
      return '#6B7280'; // Gray
  }
}

/**
 * Sorting key type for requirements list.
 */
type ReqSortKey = 'default' | 'title' | 'status' | 'updated';

/**
 * Sort requirements based on the selected key.
 */
function sortRequirements(
  list: Requirement[],
  sortKey: ReqSortKey
): Requirement[] {
  const sorted = [...list];
  switch (sortKey) {
    case 'title':
      sorted.sort((a, b) =>
        a.title.localeCompare(b.title)
      );
      break;
    case 'status':
      sorted.sort((a: Requirement, b: Requirement) => {
        const ai = WORKFLOW_STATES.indexOf(a.status);
        const bi = WORKFLOW_STATES.indexOf(b.status);
        const av = ai === -1 ? WORKFLOW_STATES.length : ai;
        const bv = bi === -1 ? WORKFLOW_STATES.length : bi;
        return av - bv || a.title.localeCompare(b.title);
      });
      break;
    case 'updated':
      sorted.sort((a, b) =>
        b.updated_at.localeCompare(a.updated_at)
      );
      break;
    default:
      break;
  }
  return sorted;
}

/**
 * RequirementList — Left panel component showing filterable list of requirements.
 */
export const RequirementList: React.FC<RequirementListProps> = ({
  requirements,
  selectedId,
  onSelect,
  onDelete,
  onCreateNew,
  isCreating = false,
}) => {
  const { t } = useTranslation();
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [listSearch, setListSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortKey, setSortKey] = useState<ReqSortKey>('default');

  // Compute visible requirements after search/filter/sort
  const visibleRequirements = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    const filtered = requirements.filter((req) => {
      if (q && !req.title.toLowerCase().includes(q) && !req.id.toLowerCase().includes(q)) {
        return false;
      }
      if (categoryFilter && req.category !== categoryFilter) {
        return false;
      }
      if (statusFilter && req.status !== statusFilter) {
        return false;
      }
      return true;
    });
    return sortRequirements(filtered, sortKey);
  }, [requirements, listSearch, categoryFilter, statusFilter, sortKey]);

  const hasActiveListControls = Boolean(listSearch || categoryFilter || statusFilter);

  return (
    <div>
      {/* Toolbar: Search, Filter, Sort */}
      <ListToolbar
        testIdPrefix="req-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t('editor.searchPlaceholder')}
        filters={[
          {
            id: 'category',
            allLabel: t('editor.allCategories'),
            value: categoryFilter,
            options: REQ_CATEGORIES.map((cat) => ({ value: cat, label: cat })),
            onChange: setCategoryFilter,
          },
          {
            id: 'status',
            allLabel: t('editor.allStatuses'),
            value: statusFilter,
            options: WORKFLOW_STATES.map((state) => ({ value: state, label: state })),
            onChange: setStatusFilter,
          },
        ]}
        sortValue={sortKey}
        sortOptions={[
          { value: 'default', label: t('editor.sortDefault') },
          { value: 'title', label: t('editor.sortTitleAsc') },
          { value: 'status', label: t('editor.sortStatus') },
          { value: 'updated', label: t('editor.sortUpdatedDesc') },
        ]}
        onSortChange={(value) => setSortKey(value as ReqSortKey)}
        sortLabel={t('editor.sortLabel')}
        countLabel={
          hasActiveListControls
            ? t('editor.filteredCount', {
                shown: visibleRequirements.length,
                total: requirements.length,
              })
            : null
        }
      />

      {/* Create button */}
      <button
        data-testid="create-req-btn"
        onClick={onCreateNew}
        style={{
          marginBottom: 'var(--space-3)',
          background: 'var(--color-primary)',
          color: 'white',
          border: 'none',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--space-2) var(--space-4)',
          fontSize: 'var(--font-size-sm)',
          cursor: 'pointer',
          transition: 'var(--transition-fast)',
          fontWeight: 600,
        }}
      >
        {isCreating ? t('actions.creating') : `+ ${t('actions.new')}`}
      </button>

      {/* Empty state */}
      {requirements.length === 0 ? (
        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)' }}>
          {t('editor.empty')}
        </p>
      ) : visibleRequirements.length === 0 ? (
        <p
          data-testid="req-list-no-matches"
          style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)' }}
        >
          {t('editor.noMatches')}
        </p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {visibleRequirements.map((req) => {
            const isActive = req.id === selectedId;
            const isHovered = hoveredId === req.id;

            const cardStyle: React.CSSProperties = {
              background: isActive
                ? '#eef2ff'
                : isHovered
                ? 'var(--color-surface-raised)'
                : 'var(--color-surface)',
              borderRadius: 'var(--radius-md)',
              boxShadow: isHovered || isActive ? 'var(--shadow-card)' : 'var(--shadow-sm)',
              padding: 'var(--space-3) var(--space-4)',
              marginBottom: 'var(--space-2)',
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'flex-start',
              cursor: 'pointer',
              color: 'var(--color-primary)',
              transition: 'var(--transition-fast)',
              wordWrap: 'break-word',
              wordBreak: 'break-word',
              margin: 0,
            };

            return (
              <li key={req.id} style={cardStyle}>
                <div
                  style={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 'var(--space-2)',
                  }}
                  onMouseEnter={() => setHoveredId(req.id)}
                  onMouseLeave={() => setHoveredId(null)}
                  onClick={() => onSelect(req.id)}
                >
                  <span
                    style={{
                      fontWeight: 600,
                      fontSize: 'var(--font-size-base)',
                      color: 'var(--color-text)',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                    }}
                  >
                    {req.suspect && <span title="Needs review due to upstream changes">⚠️</span>}
                    {req.title || t('editor.untitled')}
                  </span>
                  <div
                    style={{
                      display: 'flex',
                      gap: 'var(--space-2)',
                      alignItems: 'center',
                      flexWrap: 'wrap',
                    }}
                  >
                    {/* Type badge */}
                    {req.type && (
                      <span
                        style={{
                          background: getTypeColor(req.type),
                          color: 'white',
                          padding: '2px 8px',
                          borderRadius: 'var(--radius-full)',
                          fontSize: 'var(--font-size-xs)',
                          fontWeight: 600,
                        }}
                      >
                        {req.type}
                      </span>
                    )}
                    {/* Status badge */}
                    <span style={getStatusBadgeStyle(req.status)}>
                      {req.status}
                    </span>
                  </div>
                </div>
                {/* Delete button */}
                <button
                  data-testid="req-delete-btn"
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(req.id);
                  }}
                  style={{
                    marginLeft: 'var(--space-4)',
                    background: 'none',
                    border: 'none',
                    color: 'var(--color-danger)',
                    cursor: 'pointer',
                    fontSize: 'var(--font-size-base)',
                    fontWeight: 700,
                    padding: 0,
                    minWidth: '24px',
                    textAlign: 'center',
                  }}
                  title={t('actions.delete')}
                >
                  ×
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

RequirementList.displayName = 'RequirementList';
