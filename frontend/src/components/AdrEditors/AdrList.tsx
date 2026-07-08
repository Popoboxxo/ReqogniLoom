import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ListToolbar } from '../shared/ListToolbar';
import type { Adr } from '../../types';
import { WORKFLOW_STATES } from '../../types';

interface AdrListProps {
  items: Adr[];
  selectedId?: string;
  onCreateNew: () => void;
  showCreateForm?: boolean;
  setShowCreateForm?: (show: boolean) => void;
  newTitle?: string;
  setNewTitle?: (val: string) => void;
  onSubmitCreate?: () => void;
}

function getStatusBadgeStyle(status: string): React.CSSProperties {
  const base: React.CSSProperties = {
    borderRadius: 'var(--radius-full)',
    fontSize: 'var(--font-size-sm)',
    padding: '2px 8px',
    fontWeight: 500,
    whiteSpace: 'nowrap',
  };
  switch (status) {
    case 'Approved':
      return { ...base, background: 'var(--color-badge-approved)', color: 'var(--color-badge-approved-text)' };
    case 'In Review':
      return { ...base, background: '#bee3f8', color: '#2c5282' };
    case 'Rejected':
    case 'Superseded':
      return { ...base, background: '#fed7d7', color: '#9b2c2c' };
    default:
      return { ...base, background: 'var(--color-badge-draft)', color: 'var(--color-badge-draft-text)' };
  }
}

type SortKey = 'default' | 'title' | 'status' | 'updated';

function sortItems(list: Adr[], sortKey: SortKey): Adr[] {
  const sorted = [...list];
  switch (sortKey) {
    case 'title':
      sorted.sort((a, b) => a.title.localeCompare(b.title));
      break;
    case 'status': {
      sorted.sort((a, b) => {
        const ai = WORKFLOW_STATES.indexOf(a.status);
        const bi = WORKFLOW_STATES.indexOf(b.status);
        return (ai === -1 ? WORKFLOW_STATES.length : ai) - (bi === -1 ? WORKFLOW_STATES.length : bi) || a.title.localeCompare(b.title);
      });
      break;
    }
    case 'updated':
      sorted.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || ''));
      break;
  }
  return sorted;
}

export function AdrList({
  items, selectedId, onCreateNew, showCreateForm, setShowCreateForm, newTitle, setNewTitle, onSubmitCreate,
}: AdrListProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [listSearch, setListSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortKey, setSortKey] = useState<SortKey>('default');

  const visible = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    const filtered = items.filter((it) => {
      if (q && !it.title.toLowerCase().includes(q)) return false;
      if (statusFilter && it.status !== statusFilter) return false;
      return true;
    });
    return sortItems(filtered, sortKey);
  }, [items, listSearch, statusFilter, sortKey]);

  const hasActiveListControls = Boolean(listSearch || statusFilter);

  return (
    <div>
      <ListToolbar
        testIdPrefix="adr-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t('editor.searchPlaceholder', 'Search...')}
        filters={[{
          id: 'status', allLabel: t('editor.allStatuses', 'All Statuses'), value: statusFilter,
          options: WORKFLOW_STATES.map((s) => ({ value: s, label: s })), onChange: setStatusFilter,
        }]}
        sortValue={sortKey}
        sortOptions={[
          { value: 'default', label: t('editor.sortDefault', 'Default') },
          { value: 'title', label: t('editor.sortTitleAsc', 'Title (A-Z)') },
          { value: 'status', label: t('editor.sortStatus', 'Status') },
          { value: 'updated', label: t('editor.sortUpdatedDesc', 'Recently Updated') },
        ]}
        onSortChange={(v) => setSortKey(v as SortKey)}
        sortLabel={t('editor.sortLabel', 'Sort by')}
        countLabel={hasActiveListControls ? t('editor.filteredCount', { shown: visible.length, total: items.length }) : null}
      />
      <button
        data-testid="create-adr-btn"
        onClick={onCreateNew}
        disabled={showCreateForm}
        style={{
          marginBottom: 'var(--space-3)', background: 'var(--color-primary)', color: 'white', border: 'none',
          borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)', fontSize: 'var(--font-size-sm)',
          cursor: showCreateForm ? 'not-allowed' : 'pointer', opacity: showCreateForm ? 0.6 : 1,
          transition: 'var(--transition-fast)', fontWeight: 600,
        }}
      >+ {t('actions.new', 'New')}</button>
      {showCreateForm && setShowCreateForm && setNewTitle && onSubmitCreate && (
        <form
          onSubmit={(e) => { e.preventDefault(); onSubmitCreate(); }}
          style={{
            display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
            padding: 'var(--space-3)', marginBottom: 'var(--space-3)',
            background: 'var(--color-surface-raised)', border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <label style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--color-text)' }}>{t('editor.title', 'Title')}</label>
          <input
            type="text" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} autoFocus
            placeholder={t('editor.newNeedTitle', 'e.g. As a user, I need...')}
            style={{
              padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)', fontSize: 'var(--font-size-sm)',
              background: 'var(--color-surface)', color: 'var(--color-text)',
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button type="button" onClick={() => setShowCreateForm(false)}
              style={{
                background: 'transparent', color: 'var(--color-text)', border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)', cursor: 'pointer',
              }}
            >{t('cancel', 'Cancel')}</button>
            <button type="submit" disabled={!(newTitle || '').trim()}
              style={{
                background: 'var(--color-primary)', color: 'white', border: 'none',
                borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)', cursor: 'pointer',
              }}
            >{t('create', 'Create')}</button>
          </div>
        </form>
      )}
      {items.length === 0 ? (
        <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)' }}>{t('editor.empty', 'No items available.')}</p>
      ) : visible.length === 0 ? (
        <p data-testid="adr-list-no-matches" style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-sm)' }}>
          {t('editor.noMatches', 'No matches found.')}
        </p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {visible.map((it) => {
            const isActive = it.id === selectedId;
            const isHovered = hoveredId === it.id;
            return (
              <li
                key={it.id}
                onMouseEnter={() => setHoveredId(it.id)}
                onMouseLeave={() => setHoveredId(null)}
                style={{
                  background: isActive ? '#eef2ff' : isHovered ? 'var(--color-surface-raised)' : 'var(--color-surface)',
                  borderRadius: 'var(--radius-md)', boxShadow: isHovered || isActive ? 'var(--shadow-card)' : 'var(--shadow-sm)',
                  padding: 'var(--space-3) var(--space-4)', marginBottom: 'var(--space-2)',
                  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                  cursor: 'pointer', color: 'var(--color-primary)', transition: 'var(--transition-fast)',
                  wordWrap: 'break-word', wordBreak: 'break-word',
                }}
              >
                <a
                  href={`/adrs/${it.id}`}
                  onClick={(e) => { e.preventDefault(); navigate(`/adrs/${it.id}`); }}
                  style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', textDecoration: 'none', color: 'inherit' }}
                >
                  <span style={{ fontWeight: 600, fontSize: 'var(--font-size-base)', color: 'var(--color-text)', display: 'flex', alignItems: 'center', gap: '4px' }}>
                    {it.title || t('editor.untitled')}
                  </span>
                  <div style={{ display: 'flex', gap: 'var(--space-2)', alignItems: 'center', flexWrap: 'wrap' }}>
                    
                    <span style={getStatusBadgeStyle(it.status)}>{it.status}</span>
                  </div>
                </a>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

AdrList.displayName = 'AdrList';
