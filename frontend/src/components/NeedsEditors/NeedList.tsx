/**
 * NeedList — left-panel navigation for stakeholder needs (REQ-003).
 *
 * Refactored to use the shared WorkspaceTree component for a consistent
 * compact tree-row style across all artifact views (REQ-003).
 *
 * Search + status filter + sort remain in ListToolbar; WorkspaceTree
 * receives the already-filtered list and renders it as compact tree rows.
 */
import { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import { ListToolbar } from '../shared/ListToolbar';
import { EmptyState } from '../shared/EmptyState';
import { getStatusBadgeStyle } from '../../utils/statusBadge';
import { WorkspaceTree } from '../shared/WorkspaceTree';
import type { WorkspaceTreeNode } from '../shared/WorkspaceTree';
import type { StakeholderNeed } from '../../types';
import {
  buildStatusFilterOptions,
  compareWorkflowStatus,
  getWorkflowStatusLabel,
} from '../../utils/workflowStatus';
// F-04 (code review, 2026-08-19): shared create-form field styles (see
// frontend/src/components/shared/FieldHints.module.css header comment) —
// keeping them in one shared place instead of duplicating them per component.
import fieldHints from '../shared/FieldHints.module.css';

interface NeedListProps {
  needs: StakeholderNeed[];
  selectedId?: string;
  showCreateForm?: boolean;
  setShowCreateForm?: (show: boolean) => void;
  newTitle?: string;
  setNewTitle?: (val: string) => void;
  // BUG-11 (Systemaudit 2026-08-18, §4): description/category are ordinary
  // stakeholderNeedApi.create() fields the backend already accepts — they
  // had no editor in this create form.
  newDescription?: string;
  setNewDescription?: (val: string) => void;
  newCategory?: string;
  setNewCategory?: (val: string) => void;
  onSubmitCreate?: () => void;
  createError?: string | null;
  onCreateClick?: () => void;
}

type NeedSortKey = 'default' | 'title' | 'status' | 'updated';

function sortNeeds(
  list: StakeholderNeed[],
  sortKey: NeedSortKey,
): StakeholderNeed[] {
  const sorted = [...list];
  switch (sortKey) {
    case 'title':
      sorted.sort((a, b) => a.title.localeCompare(b.title));
      break;
    case 'status':
      sorted.sort(
        (a, b) => compareWorkflowStatus(a.status, b.status) || a.title.localeCompare(b.title),
      );
      break;
    case 'updated':
      sorted.sort((a, b) => {
        const d1 = a.updated_at || '';
        const d2 = b.updated_at || '';
        return d2.localeCompare(d1);
      });
      break;
    default:
      break;
  }
  return sorted;
}

/** Map a StakeholderNeed to a WorkspaceTreeNode (flat — no hierarchy). */
function needToNode(need: StakeholderNeed): WorkspaceTreeNode {
  const style = getStatusBadgeStyle(need.status);
  return {
    id: need.id,
    name: need.title || 'Untitled',
    parentId: null,
    badge: {
      text: getWorkflowStatusLabel(need.status),
      bg: style.background as string,
      color: style.color as string,
    },
  };
}

export function NeedList({
  needs,
  selectedId,
  showCreateForm,
  setShowCreateForm,
  newTitle,
  setNewTitle,
  newDescription,
  setNewDescription,
  newCategory,
  setNewCategory,
  onSubmitCreate,
  createError,
  onCreateClick,
}: NeedListProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [listSearch, setListSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [sortKey, setSortKey] = useState<NeedSortKey>('default');

  const visibleNeeds = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    const filtered = needs.filter((need) => {
      if (
        q &&
        !need.title.toLowerCase().includes(q) &&
        !(need.uid && need.uid.toLowerCase().includes(q))
      ) {
        return false;
      }
      if (statusFilter && need.status !== statusFilter) return false;
      return true;
    });
    return sortNeeds(filtered, sortKey);
  }, [needs, listSearch, statusFilter, sortKey]);

  const treeNodes = useMemo(
    () => visibleNeeds.map(needToNode),
    [visibleNeeds],
  );

  // GH-453: options are derived from the loaded items, so their values are
  // exactly what `need.status !== statusFilter` compares against — the shared
  // hardcoded list never matched StakeholderNeed's lowercase vocabulary.
  const statusOptions = useMemo(
    () => buildStatusFilterOptions(needs, statusFilter),
    [needs, statusFilter],
  );

  const hasActiveListControls = Boolean(listSearch || statusFilter);

  return (
    <div>
      <ListToolbar
        testIdPrefix="need-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t('editor.searchPlaceholder', 'Search needs...')}
        filters={[
          {
            id: 'status',
            allLabel: t('editor.allStatuses', 'All Statuses'),
            value: statusFilter,
            options: statusOptions,
            onChange: setStatusFilter,
          },
        ]}
        sortValue={sortKey}
        sortOptions={[
          { value: 'default', label: t('editor.sortDefault', 'Default') },
          { value: 'title', label: t('editor.sortTitleAsc', 'Title (A-Z)') },
          { value: 'status', label: t('editor.sortStatus', 'Status') },
          { value: 'updated', label: t('editor.sortUpdatedDesc', 'Recently Updated') },
        ]}
        onSortChange={(value) => setSortKey(value as NeedSortKey)}
        sortLabel={t('editor.sortLabel', 'Sort by')}
        countLabel={
          hasActiveListControls
            ? t('editor.filteredCount', {
                shown: visibleNeeds.length,
                total: needs.length,
              })
            : String(needs.length)
        }
        // #315: the "Neuer Bedarf" primary action now lives in the
        // PageHeader (UI_KONZEPT.md §12.2), not in this list toolbar —
        // matches Adr/Risk/Issue/TestCase editors. `onCreateClick` is still
        // forwarded (below) for the empty-state's own create action.
      />

      {showCreateForm && setShowCreateForm && setNewTitle && onSubmitCreate && (
        <form
          onSubmit={(e) => {
            e.preventDefault();
            onSubmitCreate();
          }}
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-2)',
            padding: 'var(--space-3)',
            marginBottom: 'var(--space-3)',
            background: 'var(--color-surface-raised)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-md)',
          }}
        >
          <label
            style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--color-text)' }}
          >
            {t('editor.title', 'Title')}
          </label>
          <input
            type="text"
            data-testid="need-new-title-input"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            autoFocus
            placeholder={t('editor.newNeedTitle', 'e.g. As a user, I need...')}
            style={{
              padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
              fontSize: 'var(--font-size-sm)',
              background: 'var(--color-surface)',
              color: 'var(--color-text)',
            }}
          />

          {/* BUG-11: description/category — ordinary
              stakeholderNeedApi.create() fields the backend already accepts,
              previously missing here. */}
          {setNewDescription && (
            <>
              {/* F-05 (code review, 2026-08-19): every other one of the 6
                  create-form fields added this round pairs label/input via
                  htmlFor/id — this one was the odd one out. */}
              <label htmlFor="need-new-description" className={fieldHints.createLabelInline}>
                {t('editor.description', 'Description')}
              </label>
              <textarea
                id="need-new-description"
                data-testid="need-new-description-input"
                value={newDescription || ''}
                onChange={(e) => setNewDescription(e.target.value)}
                rows={3}
                className={fieldHints.createInput}
              />
            </>
          )}
          {setNewCategory && (
            <>
              <label htmlFor="need-new-category" className={fieldHints.createLabelInline}>
                {t('editor.category', 'Category')}
              </label>
              <input
                id="need-new-category"
                type="text"
                data-testid="need-new-category-input"
                value={newCategory || ''}
                onChange={(e) => setNewCategory(e.target.value)}
                className={fieldHints.createInput}
              />
            </>
          )}

          {createError && (
            <p
              role="alert"
              style={{ color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)', margin: 0 }}
            >
              {createError}
            </p>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button
              type="button"
              data-testid="need-create-cancel-btn"
              onClick={() => setShowCreateForm(false)}
              style={{
                background: 'transparent',
                color: 'var(--color-text)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)',
                cursor: 'pointer',
              }}
            >
              {t('actions.cancel', 'Cancel')}
            </button>
            <button
              type="submit"
              data-testid="need-create-submit-btn"
              // #678: distinct accessible name from the PageHeader's primary
              // action and the empty-state's create action — those two open
              // this form; this one submits it. All three can be visible at
              // once (empty list + open form), and "Create"/"Erstellen" is
              // generic enough to be worth disambiguating explicitly rather
              // than relying on translation strings staying different.
              aria-label={t('needs.submitCreateLabel', 'Bedarf jetzt erstellen')}
              disabled={!(newTitle || '').trim()}
              style={{
                background: 'var(--color-primary)',
                color: 'white',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)',
                cursor: 'pointer',
              }}
            >
              {t('actions.create', 'Erstellen')}
            </button>
          </div>
        </form>
      )}

      {/* #179: distinct empty vs. no-match states (ch. 13.3) instead of
          WorkspaceTree's built-in plain-text emptyLabel/noMatchesLabel —
          "there is nothing" wants a create action, "there is something,
          just not under this filter" must not offer one. */}
      {needs.length === 0 ? (
        <EmptyState
          variant="empty"
          testId="need-list-empty"
          title={t('needs.emptyTitle', 'Noch keine Bedarfe')}
          description={t(
            'needs.emptyDescription',
            'Stakeholder-Bedarfe beschreiben, was Stakeholder brauchen und warum.',
          )}
          actions={
            onCreateClick
              ? [
                  {
                    label: `+ ${t('needs.newNeed')}`,
                    // #678: same visible wording as the PageHeader's primary
                    // action (both trigger the identical create flow), but a
                    // distinct accessible name — the two buttons coexist in
                    // the DOM whenever the list is empty.
                    ariaLabel: t('needs.emptyCreateLabel', 'Ersten Bedarf anlegen'),
                    onClick: onCreateClick,
                    testId: 'need-list-empty-create',
                  },
                ]
              : undefined
          }
        />
      ) : visibleNeeds.length === 0 ? (
        <EmptyState
          variant="no-match"
          testId="need-list-no-match"
          onResetFilters={() => {
            setListSearch('');
            setStatusFilter('');
          }}
        />
      ) : (
        // Unified tree navigation — REQ-003
        // REQ-091: enable virtualization for this hot-path list (threshold 100).
        <WorkspaceTree
          data-testid="need-list-tree"
          nodes={treeNodes}
          selectedId={selectedId}
          onSelect={(id) => navigate(`/needs/${id}`)}
          showSearch={false}
          virtualize
        />
      )}
    </div>
  );
}

NeedList.displayName = 'NeedList';
