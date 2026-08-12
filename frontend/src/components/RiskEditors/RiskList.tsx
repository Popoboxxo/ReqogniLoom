/**
 * RiskList — left-panel navigation for risks (REQ-003).
 *
 * Task 2.2 remodel: rows are <ArtifactRow> (ch. 12.3 — id/level on top,
 * title below, status + version badges) instead of a WorkspaceTree node, and
 * the empty list vs. empty filter result render through <EmptyState> with
 * distinct text and actions (ch. 12.7/13.3). The page title, always-visible
 * summary and "New Risk" primary action now live in <PageHeader> at the
 * RiskEditors level (ch. 12.1/12.2) — this component only owns
 * search/filter/sort and the row list. Mirrors AdrList (Task 2.1).
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ListToolbar } from '../shared/ListToolbar';
import { ArtifactRow } from '../shared/ArtifactRow';
import { EmptyState } from '../shared/EmptyState';
import type { Risk } from '../../types';
import {
  buildStatusFilterOptions,
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from '../../utils/workflowStatus';
import styles from './RiskList.module.css';

interface RiskListProps {
  items: Risk[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onCreateNew: () => void;
}

type SortKey = 'default' | 'title' | 'status' | 'updated';

function sortItems(list: Risk[], sortKey: SortKey): Risk[] {
  const sorted = [...list];
  switch (sortKey) {
    case 'title': sorted.sort((a, b) => a.title.localeCompare(b.title)); break;
    case 'status': {
      sorted.sort(
        (a, b) => compareWorkflowStatus(a.status, b.status) || a.title.localeCompare(b.title),
      );
      break;
    }
    case 'updated': sorted.sort((a, b) => (b.updated_at || '').localeCompare(a.updated_at || '')); break;
  }
  return sorted;
}

export function RiskList({ items, selectedId, onSelect, onCreateNew }: RiskListProps): JSX.Element {
  const { t } = useTranslation();
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

  // GH-453: options are derived from the loaded items, so their values are
  // exactly what `it.status !== statusFilter` compares against — the shared
  // hardcoded list never matched Risk's vocabulary.
  const statusOptions = useMemo(
    () => buildStatusFilterOptions(items, statusFilter),
    [items, statusFilter],
  );

  const hasActiveListControls = Boolean(listSearch || statusFilter);

  const resetFilters = (): void => {
    setListSearch('');
    setStatusFilter('');
  };

  return (
    <div data-testid="risk-list">
      <ListToolbar
        testIdPrefix="risk-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t('editor.searchPlaceholder', 'Search...')}
        filters={[{
          id: 'status', allLabel: t('editor.allStatuses', 'All Statuses'), value: statusFilter,
          options: statusOptions, onChange: setStatusFilter,
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
        countLabel={hasActiveListControls ? t('editor.filteredCount', { shown: visible.length, total: items.length }) : String(items.length)}
      />

      {items.length === 0 ? (
        // ch. 13.3: "there is nothing" — offer the create action, not a
        // filter reset.
        <EmptyState
          variant="empty"
          testId="risk-list-empty"
          title={t('risks.emptyTitle', 'No risks yet')}
          description={t(
            'risks.emptyDescription',
            'Risks capture what could go wrong and how it is being mitigated.',
          )}
          actions={[{ label: t('risks.newRisk', 'New Risk'), onClick: onCreateNew, testId: 'risk-list-empty-create' }]}
        />
      ) : visible.length === 0 ? (
        // ch. 13.3: "there is something, just not under this filter" — offer
        // only a filter reset, never a create action.
        <EmptyState variant="no-match" testId="risk-list-no-match" onResetFilters={resetFilters} />
      ) : (
        <div className={styles.rows} data-testid="risk-list-rows">
          {visible.map((risk) => (
            <ArtifactRow
              key={risk.id}
              id={risk.uid}
              idFallback={risk.id.slice(0, 8)}
              title={risk.title || t('risks.untitled', 'Untitled')}
              status={risk.status}
              statusLabel={getWorkflowStatusLabel(risk.status)}
              version={risk.version}
              selected={risk.id === selectedId}
              onClick={() => onSelect(risk.id)}
              testId={`risk-row-${risk.id}`}
            />
          ))}
        </div>
      )}
    </div>
  );
}

RiskList.displayName = 'RiskList';
