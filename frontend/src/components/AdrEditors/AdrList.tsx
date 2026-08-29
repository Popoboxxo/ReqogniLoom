/**
 * AdrList — left-panel navigation for ADRs (REQ-003).
 *
 * Task 2.1 remodel: rows are <ArtifactRow> (ch. 12.3 — id/level on top,
 * title below, status + version badges), and the empty list vs. empty
 * filter result render through <EmptyState> with distinct text and actions
 * (ch. 12.7/13.3). The page title, always-visible summary and "New ADR"
 * primary action now live in <PageHeader> at the AdrEditors level
 * (ch. 12.1/12.2) — this component only owns search/filter/sort and the
 * row list.
 *
 * Task 4.4 (virtualization ratchet): rows now render through the shared
 * <WorkspaceTree>'s `renderRow` slot (the same pattern `RequirementList`
 * established) instead of a bare `.map()`, so `virtualize` costs one prop
 * — WorkspaceTree owns the row virtualization, ADRs have no hierarchy so
 * every node is a root (`parentId: null`), mirroring `NeedList`.
 */
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ListToolbar } from '../shared/ListToolbar';
import { ArtifactRow } from '../shared/ArtifactRow';
import { EmptyState } from '../shared/EmptyState';
import { WorkspaceTree } from '../shared/WorkspaceTree';
import type { WorkspaceTreeNode } from '../shared/WorkspaceTree';
import type { Adr } from '../../types';
import {
  buildStatusFilterOptions,
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from '../../utils/workflowStatus';

interface AdrListProps {
  items: Adr[];
  selectedId?: string;
  onSelect: (id: string) => void;
  onCreateNew: () => void;
}

type SortKey = 'default' | 'title' | 'status' | 'updated';

function sortItems(list: Adr[], sortKey: SortKey): Adr[] {
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

/** Map an Adr to a WorkspaceTreeNode (flat — no hierarchy). */
function adrToNode(adr: Adr): WorkspaceTreeNode {
  return { id: adr.id, name: adr.title || 'Untitled', parentId: null };
}

export function AdrList({ items, selectedId, onSelect, onCreateNew }: AdrListProps): JSX.Element {
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

  const treeNodes = useMemo(() => visible.map(adrToNode), [visible]);

  // Task 4.4: lookup used by renderRow to hydrate <ArtifactRow> from the
  // WorkspaceTreeNode id — mirrors RequirementList's reqById.
  const adrById = useMemo(() => {
    const map = new Map<string, Adr>();
    for (const adr of visible) map.set(adr.id, adr);
    return map;
  }, [visible]);

  // GH-453: options are derived from the loaded items, so their values are
  // exactly what `it.status !== statusFilter` compares against — the shared
  // hardcoded list never matched Adr's vocabulary.
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
    <div data-testid="adr-list">
      <ListToolbar
        testIdPrefix="adr-list"
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
          testId="adr-list-empty"
          title={t('adrs.emptyTitle', 'No ADRs yet')}
          description={t(
            'adrs.emptyDescription',
            'Architecture decision records capture why the system is built the way it is.',
          )}
          actions={[
            {
              // #594 / issue #719: same "+ " gesture marker as the PageHeader
              // primary action that triggers the identical create flow — the
              // two buttons must not read differently for the same action.
              label: t('adrs.newAdr', 'New ADR'),
              prefixWithPlus: true,
              onClick: onCreateNew,
              testId: 'adr-list-empty-create',
            },
          ]}
        />
      ) : visible.length === 0 ? (
        // ch. 13.3: "there is something, just not under this filter" — offer
        // only a filter reset, never a create action.
        <EmptyState variant="no-match" testId="adr-list-no-match" onResetFilters={resetFilters} />
      ) : (
        // Task 4.4: WorkspaceTree owns virtualization; rows are <ArtifactRow>
        // via renderRow, same as RequirementList.
        <WorkspaceTree
          data-testid="adr-list-rows"
          nodes={treeNodes}
          selectedId={selectedId}
          onSelect={onSelect}
          showSearch={false}
          virtualize
          // <ArtifactRow>'s two-line id/title layout is taller than
          // WorkspaceTree's default single-line row estimate (34px).
          virtualRowHeight={64}
          emptyLabel={t('editor.empty', 'No items.')}
          noMatchesLabel={t('editor.noMatches', 'No matches found.')}
          renderRow={(node, { isSelected }) => {
            const adr = adrById.get(node.id);
            if (!adr) return null;
            return (
              <ArtifactRow
                id={adr.uid}
                idFallback={adr.id.slice(0, 8)}
                title={adr.title || t('adrs.untitled', 'Untitled')}
                status={adr.status}
                statusLabel={getWorkflowStatusLabel(adr.status)}
                version={adr.version}
                selected={isSelected}
                testId={`adr-row-${adr.id}`}
              />
            );
          }}
        />
      )}
    </div>
  );
}

AdrList.displayName = 'AdrList';
