import { useCallback, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { Dialog } from '../shared/Dialog';
import { TestCaseList } from './TestCaseList';
import { TestCaseForm } from './TestCaseForm';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { TraceSpine, useDerivationChain } from '../shared/TraceSpine';
import type { ChainArtifact } from '../shared/TraceSpine';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import { useTestCaseData } from './useTestCaseData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { testcasesApi } from '../../api/testcases';

export default function TestCaseEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { items, item, isLoading, error, refresh } = useTestCaseData(selectedId);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);

  // 12.1/14.2: named after the result ("New Test Case"), not the gesture
  // ("+ New"); also the dialog title, matching ch. 12.8 ("dialog title
  // repeats the label of the button that opened it").
  const newTestCaseLabel = t('testcases.newTestCase', 'New Test Case');

  const openCreateDialog = useCallback((): void => {
    setCreateError(null);
    setNewTitle('');
    setShowCreateDialog(true);
  }, []);

  // Stable identity is required here, not just tidiness: <Dialog>'s focus
  // trap re-runs its setup effect whenever `onClose` changes identity
  // (useFocusTrap depends on it to keep `onEscape` current), which
  // re-focuses the dialog's first element on every call. An inline arrow
  // here would recreate on every keystroke in the title input below and
  // fight the user for focus after each character.
  const closeCreateDialog = useCallback((): void => {
    setShowCreateDialog(false);
    setCreateError(null);
  }, []);

  const handleCreateNew = async (): Promise<void> => {
    if (!activeWorkspace) return;
    if (!newTitle.trim()) return;
    setCreateError(null);
    setIsCreating(true);
    try {
      const resp = await testcasesApi.create({ workspace_id: activeWorkspace.id, title: newTitle.trim() });
      setNewTitle('');
      setShowCreateDialog(false);
      refresh();
      navigate(`/testcases/${resp.id}`);
    } catch (e) {
      console.error(e);
      const msg = (e as { error?: { message?: string } })?.error?.message ?? t('testcases.createFailed');
      setCreateError(msg);
    } finally {
      setIsCreating(false);
    }
  };

  const handleSaved = () => { refresh(); };
  const handleDeleted = () => { navigate('/testcases'); refresh(); };

  // Trace spine (Task 3.3 — UI concept ch. 5). Test cases are not their own
  // station type in the derivation-chain model (useDerivationChain docs) —
  // they attach to the station of whatever they verify — but the currently
  // opened test case still gets its own "current" station showing what it
  // verifies/derives from.
  const derivationChain = useDerivationChain(
    // TestCase has no separate `artifact_id` field on the frontend type
    // (unlike Requirement/Adr/Risk/Issue) — its own id is the Artifact id.
    item?.id ?? null,
    'TestCase',
    null,
    { enabled: !!item },
  );

  const handleOpenChainArtifact = useCallback(
    (artifact: ChainArtifact): void => {
      const entry = derivationChain.resolveEntry(artifact);
      if (entry) navigate(getArtifactRoute(entry.entityType, entry.entityId));
    },
    [derivationChain, navigate],
  );

  // Page-level loading / error states — only gate the full view on the
  // initial load (no data yet), keeping the list visible on detail reloads.
  if (isLoading && items.length === 0) {
    return (
      <p role="status" style={{ padding: 'var(--space-8)', color: 'var(--color-text-muted)' }}>
        {t('loading', 'Laden...')}
      </p>
    );
  }

  if (error && items.length === 0) {
    return (
      <div role="alert" style={{ padding: 'var(--space-8)' }}>
        <p style={{ color: 'var(--color-danger)', marginBottom: 'var(--space-4)' }}>
          {error.message}
        </p>
        <button className="btn-secondary" onClick={refresh} data-testid="testcase-reload-btn">
          {t('actions.reload', 'Erneut versuchen')}
        </button>
      </div>
    );
  }

  return (
    <div data-testid="testcases-page" style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* 12.1: exactly one <h1>, always-visible summary, one primary action —
          replaces the bare "+ New" button that used to live inside
          TestCaseList (issue: the create action sat in the list toolbar, in
          violation of 12.2). */}
      <PageHeader
        title={t('nav.testCases')}
        summary={t('testcases.summary', { count: items.length })}
        primaryAction={{
          label: newTestCaseLabel,
          onClick: openCreateDialog,
          testId: 'create-tc-btn',
        }}
      />

      <div style={{ flex: '1 1 auto', minHeight: '60vh' }}>
        <SplitView
          leftPanel={
            <TestCaseList
              items={items}
              selectedId={selectedId}
              onSelect={(id) => navigate(`/testcases/${id}`)}
              onCreateNew={openCreateDialog}
            />
          }
          rightPanel={
            <div style={{ display: 'flex', height: '100%', minHeight: 0, gap: 'var(--space-3)' }}>
              <div style={{ flex: '1 1 auto', minWidth: 0, overflow: 'auto' }}>
                {item && (
                  <TraceSpine
                    stations={derivationChain.stations}
                    isLoading={derivationChain.isLoading}
                    error={derivationChain.error}
                    onOpenArtifact={handleOpenChainArtifact}
                    isOpenable={derivationChain.isOpenable}
                  />
                )}
                <TestCaseForm testCase={item} onSaved={handleSaved} onDeleted={handleDeleted} />
              </div>
              {item && (() => {
                const ver: VersionRef = { version: item.version, label: `v${item.version}`, createdAt: null, baselineIds: [] };
                return <RightSidebar kind="testCase" artifactId={item.id} currentVersion={ver} hideTraceLinks />;
              })()}
            </div>
          }
          initialLeftWidth={350}
          moduleType="testcases"
        />
      </div>

      {showCreateDialog && (
        <Dialog
          title={newTestCaseLabel}
          onClose={closeCreateDialog}
          testId="tc-create-dialog"
          // The dialog's own focusable-order default would land on the close
          // (×) button, not the title field — same as CreateWorkspaceModal,
          // point the trap at the field the user actually wants to type into.
          initialFocusRef={titleInputRef}
          footer={
            <>
              <button
                type="button"
                className="btn-secondary"
                onClick={closeCreateDialog}
                disabled={isCreating}
              >
                {t('actions.cancel', 'Cancel')}
              </button>
              <button
                type="submit"
                form="tc-create-form"
                data-testid="tc-new-save-btn"
                className="btn-primary"
                disabled={isCreating || !newTitle.trim()}
              >
                {isCreating ? t('actions.saving', 'Saving...') : t('create', 'Create')}
              </button>
            </>
          }
        >
          <form
            id="tc-create-form"
            onSubmit={(e) => { e.preventDefault(); void handleCreateNew(); }}
          >
            <label
              htmlFor="tc-new-title"
              style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--color-text)', marginBottom: 'var(--space-1)' }}
            >
              {t('editor.title', 'Title')}
            </label>
            <input
              ref={titleInputRef}
              id="tc-new-title"
              data-testid="tc-new-title-input"
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder={t('editor.newNeedTitle', 'e.g. Test case title...')}
              style={{
                width: '100%', boxSizing: 'border-box', padding: 'var(--space-2) var(--space-3)',
                borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)',
                fontSize: 'var(--font-size-sm)', background: 'var(--color-surface)', color: 'var(--color-text)',
              }}
            />
            {createError && (
              <p role="alert" style={{ color: 'var(--color-danger)', fontSize: 'var(--font-size-sm)', marginTop: 'var(--space-2)' }}>
                {createError}
              </p>
            )}
          </form>
        </Dialog>
      )}
    </div>
  );
}
