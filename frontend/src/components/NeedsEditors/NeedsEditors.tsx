/**
 * NeedsEditors — split-view editor for stakeholder needs.
 *
 * leaf_id: COMP-RF-003 (split-view editors)
 * req_id:  REQ-L1-095 (ArtifactInspector adoption — 10 artifact types),
 *          REQ-L2-RF-034 (ArtifactInspector RightSidebar shell)
 *
 * Layout: SplitView (left = NeedList, right = NeedForm). When a detail
 * is selected, the right pane becomes a flex container that hosts both
 * the editor and the ArtifactInspector (Version / Diff / Trace). The
 * inspector is hidden when the user is browsing the list (no detail).
 */
import React, { useCallback, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { NeedList } from './NeedList';
import { NeedForm } from './NeedForm';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { TraceSpine, useDerivationChain } from '../shared/TraceSpine';
import type { ChainArtifact } from '../shared/TraceSpine';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import { useNeedData } from './useNeedData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { stakeholderNeedApi } from '../../api/stakeholder-need';
import { attributeVisibilityApi } from '../../api';

export default function NeedsEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace, workspaces } = useWorkspace();
  const { needs, need, isLoading, error, refresh } = useNeedData(selectedId);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  // BUG-11 (Systemaudit 2026-08-18, §4): description/category are ordinary
  // stakeholderNeedApi.create() fields the backend already accepts — they
  // had no editor in this create form.
  const [newDescription, setNewDescription] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);

  const [attributeVisibility, setAttributeVisibility] = useState<Record<string, boolean>>({
    moscow_priority: true,
  });

  React.useEffect(() => {
    let isMounted = true;
    attributeVisibilityApi.list()
      .then((data) => {
        if (!isMounted) return;
        const vMap: Record<string, boolean> = {};
        data.filter(cfg => cfg.entity_type === 'stakeholder_need').forEach(cfg => {
          vMap[cfg.attribute_name] = cfg.is_visible;
        });
        if (!('moscow_priority' in vMap)) vMap['moscow_priority'] = true;
        setAttributeVisibility(vMap);
      })
      // An empty config set is a valid, expected state (no seed data by
      // design); only genuine HTTP/network failures reach here — log them as a
      // warning, not an error (REQ-136).
      .catch(err => console.warn('Could not load attribute configs; using defaults', err));
    return () => { isMounted = false; };
  }, []);

  const handleCreateNew = async () => {
    // Guard against firing a create with the placeholder DEFAULT_WORKSPACE id
    // (null-UUID) before reloadWorkspaces() has populated the real workspaces.
    if (!activeWorkspace || workspaces.length === 0) return;
    if (!newTitle.trim()) return;
    setCreateError(null);
    try {
      const resp = await stakeholderNeedApi.create(activeWorkspace.id, {
        title: newTitle.trim(),
        // BUG-11: only send what was actually typed.
        ...(newDescription.trim() ? { description: newDescription.trim() } : {}),
        ...(newCategory.trim() ? { category: newCategory.trim() } : {}),
      });
      setNewTitle('');
      setNewDescription('');
      setNewCategory('');
      setShowCreate(false);
      refresh();
      navigate(`/needs/${resp.id}`);
    } catch (e) {
      console.error(e);
      const msg = (e as { error?: { message?: string } })?.error?.message ?? t('needs.createFailed');
      setCreateError(msg);
    }
  };

  // Shared by the PageHeader primary action and (formerly) the NeedList
  // "+ New" button — do not open the create form until real workspaces are
  // loaded, preventing a POST against the null-UUID placeholder workspace.
  const handleCreateNewClick = () => {
    if (workspaces.length === 0) return;
    setCreateError(null);
    setNewDescription('');
    setNewCategory('');
    setShowCreate(true);
  };

  // ch. 12.1 — always-visible summary: total plus the number already
  // approved, which is the figure a reviewer actually asks for.
  const needsSummary = React.useMemo(() => {
    const approved = needs.filter(
      (n) => (n.status ?? '').toLowerCase() === 'approved',
    ).length;
    return [
      t('needs.summary', { count: needs.length, defaultValue: `${needs.length}` }),
      t('needs.approvedSuffix', {
        count: approved,
        defaultValue: `${approved} approved`,
      }),
    ].join(' · ');
  }, [needs, t]);

  const handleSaved = () => {
    refresh();
  };

  const handleDeleted = () => {
    navigate('/needs');
    refresh();
  };

  // Trace spine (Task 3.3 — UI concept ch. 5).
  const derivationChain = useDerivationChain(
    need?.artifact_id ?? need?.id ?? null,
    'StakeholderNeed',
    null,
    { enabled: !!need },
  );

  const handleOpenChainArtifact = useCallback(
    (artifact: ChainArtifact): void => {
      const entry = derivationChain.resolveEntry(artifact);
      if (entry) navigate(getArtifactRoute(entry.entityType, entry.entityId));
    },
    [derivationChain, navigate],
  );

  // Page-level loading / error states — only gate the full view on the
  // initial load (no data yet). Once the list is populated, keep it visible
  // while the detail pane reloads (UI standards §1.4).
  if (isLoading && needs.length === 0) {
    return (
      <p role="status" style={{ padding: 'var(--space-8)', color: 'var(--color-text-muted)' }}>
        {t('loading', 'Laden...')}
      </p>
    );
  }

  if (error && needs.length === 0) {
    return (
      <div role="alert" style={{ padding: 'var(--space-8)' }}>
        <p style={{ color: 'var(--color-danger)', marginBottom: 'var(--space-4)' }}>
          {error.message}
        </p>
        <button className="btn-secondary" onClick={refresh} data-testid="need-reload-btn">
          {t('actions.retry')}
        </button>
      </div>
    );
  }

  return (
    <>
      {/* Page header — issue #172 / #315: this page previously had no
          heading at all and buried "+ New" under the filter row (and then
          in the list's ListToolbar); now matches the Architecture/Glossary/
          Adr/Risk/Issue/TestCase pattern (title + summary + primary action
          in the PageHeader per UI_KONZEPT.md §12.2). */}
      <PageHeader
        title={t('nav.needs')}
        // ch. 12.1: the summary is always visible — it answers "how many do
        // we have?" and makes a silently truncated list noticeable. It
        // replaces the counter that only appeared under an active filter.
        summary={needsSummary}
        primaryAction={{
          label: t('needs.newNeed'),
          prefixWithPlus: true,
          // #678: distinct accessible name from the empty-state's own
          // "create" action and the create form's submit button — all three
          // can be present in the DOM at once (empty list + open form), and
          // sharing the visible "Neuer Bedarf"/"New Need" wording made them
          // ambiguous to a11y trees and getByRole queries.
          ariaLabel: t('needs.openCreateFormLabel', 'Bedarf-Formular öffnen'),
          onClick: handleCreateNewClick,
          disabled: showCreate,
          testId: 'create-need-btn',
        }}
        secondaryActions={[
          {
            label: t('interviews.startCta'),
            onClick: () => navigate('/interviews?start=StakeholderNeed'),
            disabled: !activeWorkspace,
            testId: 'interview-start-cta',
          },
        ]}
      />
      <SplitView
      leftPanel={
        <NeedList
          needs={needs}
          selectedId={selectedId}
          showCreateForm={showCreate}
          setShowCreateForm={(show: boolean) => { if (!show) setCreateError(null); setShowCreate(show); }}
          newTitle={newTitle}
          setNewTitle={setNewTitle}
          newDescription={newDescription}
          setNewDescription={setNewDescription}
          newCategory={newCategory}
          setNewCategory={setNewCategory}
          onSubmitCreate={handleCreateNew}
          createError={createError}
          onCreateClick={handleCreateNewClick}
        />
      }
      rightPanel={
        <div
          style={{
            display: 'flex',
            height: '100%',
            minHeight: 0,
            gap: 'var(--space-3)',
          }}
        >
          <div style={{ flex: '1 1 auto', minWidth: 0, overflow: 'auto' }}>
            {need && (
              <TraceSpine
                stations={derivationChain.stations}
                isLoading={derivationChain.isLoading}
                error={derivationChain.error}
                onOpenArtifact={handleOpenChainArtifact}
                isOpenable={derivationChain.isOpenable}
              />
            )}
            <NeedForm
              need={need}
              onSaved={handleSaved}
              onDeleted={handleDeleted}
              attributeVisibility={attributeVisibility}
            />
          </div>
          {/* ArtifactInspector — REQ-L1-095, REQ-L2-RF-034 (detail only).
              hideTraceLinks: the <TraceSpine> above now owns trace-link
              display (Task 3.3). */}
          {need && (() => {
            const needCurrentVersion: VersionRef = {
              version: need.version,
              label: `v${need.version}`,
              createdAt: null,
              baselineIds: [],
            };
            return (
              <RightSidebar
                kind="stakeholderNeed"
                artifactId={need.id}
                currentVersion={needCurrentVersion}
                hideTraceLinks
              />
            );
          })()}
        </div>
      }
      initialLeftWidth={350}
      />
    </>
  );
}
