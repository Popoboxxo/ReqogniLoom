import { useCallback, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { Dialog } from '../shared/Dialog';
import { IssueList } from './IssueList';
import { IssueForm } from './IssueForm';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { TraceLinkPanel } from '../shared/TraceLinkPanel';
import { TraceSpine, useDerivationChain } from '../shared/TraceSpine';
import type { ChainArtifact } from '../shared/TraceSpine';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import { useIssueData } from './useIssueData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { issuesApi } from '../../api/issues';
import { CATEGORY_OPTIONS } from './IssueForm';
// F-04 (code review, 2026-08-19): shared create-form field styles (see
// frontend/src/components/shared/FieldHints.module.css header comment) —
// keeping them in one shared place instead of duplicating them per component.
import fieldHints from '../shared/FieldHints.module.css';

export default function IssueEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { items, item, isLoading, error, refresh } = useIssueData(selectedId);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  // BUG-11 (Systemaudit 2026-08-18, §4): description/category are ordinary
  // issuesApi.create() fields the backend already accepts — they had no
  // editor in this create dialog.
  const [newDescription, setNewDescription] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);

  // 12.1/14.2: named after the result ("New Issue"), not the gesture ("+ New");
  // also the dialog title, matching ch. 12.8 ("dialog title repeats the
  // label of the button that opened it").
  const newIssueLabel = t('issues.newIssue', 'New Issue');

  const openCreateDialog = useCallback((): void => {
    setCreateError(null);
    setNewTitle('');
    setNewDescription('');
    setNewCategory('');
    setShowCreateDialog(true);
  }, []);

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
      const resp = await issuesApi.create({
        workspace_id: activeWorkspace.id,
        title: newTitle.trim(),
        // BUG-11: only send what was actually typed.
        ...(newDescription.trim() ? { description: newDescription.trim() } : {}),
        ...(newCategory ? { category: newCategory } : {}),
      });
      setNewTitle('');
      setNewDescription('');
      setNewCategory('');
      setShowCreateDialog(false);
      refresh();
      navigate(`/issues/${resp.id}`);
    } catch (e) {
      console.error(e);
      const msg = (e as { error?: { message?: string } })?.error?.message ?? t('issues.createFailed');
      setCreateError(msg);
    } finally {
      setIsCreating(false);
    }
  };

  const handleSaved = () => { refresh(); };
  const handleDeleted = () => { navigate('/issues'); refresh(); };

  // Trace spine (Task 3.3 — UI concept ch. 5).
  const derivationChain = useDerivationChain(
    item?.artifact_id ?? item?.id ?? null,
    'Issue',
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
        <button className="btn-secondary" onClick={refresh} data-testid="issue-reload-btn">
          {t('actions.retry')}
        </button>
      </div>
    );
  }

  return (
    <div data-testid="issues-page" style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* 12.1: exactly one <h1>, always-visible summary, one primary action. */}
      <PageHeader
        title={t('nav.issues')}
        summary={t('issues.summary', { count: items.length })}
        primaryAction={{
          label: newIssueLabel,
          prefixWithPlus: true,
          onClick: openCreateDialog,
          testId: 'create-issue-btn',
        }}
        secondaryActions={[
          {
            label: t('interviews.startCta'),
            onClick: () => navigate('/interviews?start=Issue'),
            disabled: !activeWorkspace,
            testId: 'interview-start-cta',
          },
        ]}
      />

      <div style={{ flex: '1 1 auto', minHeight: '60vh' }}>
        <SplitView
          leftPanel={
            <IssueList
              items={items}
              selectedId={selectedId}
              onSelect={(id) => navigate(`/issues/${id}`)}
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
                <IssueForm issue={item} onSaved={handleSaved} onDeleted={handleDeleted} />
                {/* Task 2.3: the "Neue Verknüpfung" button used to float under
                    the form as an inline-styled one-off, wired to its own
                    CreateTraceLinkDialog instance. TraceLinkPanel already
                    owns a "new link" action in its own header (same as
                    AdrEditors/RiskEditors), so relocating here both fixes the
                    placement and removes the duplicate dialog wiring
                    IssueEditors used to carry on its own. TraceLinkPanel
                    stays as the CRUD surface alongside the read-only Spine
                    above (Task 3.3 decision). */}
                {item && activeWorkspace && (
                  <TraceLinkPanel workspaceId={activeWorkspace.id} artifactId={item.id} />
                )}
              </div>
              {item && (() => {
                const ver: VersionRef = { version: item.version, label: `v${item.version}`, createdAt: null, baselineIds: [] };
                return <RightSidebar kind="issue" artifactId={item.id} currentVersion={ver} hideTraceLinks />;
              })()}
            </div>
          }
          initialLeftWidth={350}
          moduleType="issues"
        />
      </div>

      {showCreateDialog && (
        <Dialog
          title={newIssueLabel}
          onClose={closeCreateDialog}
          testId="issue-create-dialog"
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
                form="issue-create-form"
                data-testid="issue-new-save-btn"
                className="btn-primary"
                disabled={isCreating || !newTitle.trim()}
              >
                {isCreating ? t('actions.saving', 'Saving...') : t('actions.create', 'Erstellen')}
              </button>
            </>
          }
        >
          <form
            id="issue-create-form"
            onSubmit={(e) => { e.preventDefault(); void handleCreateNew(); }}
          >
            <label
              htmlFor="issue-new-title"
              style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--color-text)', marginBottom: 'var(--space-1)' }}
            >
              {t('editor.title', 'Title')}
            </label>
            <input
              ref={titleInputRef}
              id="issue-new-title"
              data-testid="issue-new-title-input"
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder={t('editor.newNeedTitle', 'e.g. Issue title...')}
              style={{
                width: '100%', boxSizing: 'border-box', padding: 'var(--space-2) var(--space-3)',
                borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)',
                fontSize: 'var(--font-size-sm)', background: 'var(--color-surface)', color: 'var(--color-text)',
              }}
            />

            {/* BUG-11: description/category — ordinary issuesApi.create()
                fields the backend already accepts, previously missing
                here. */}
            <label htmlFor="issue-new-description" className={fieldHints.createLabel}>
              {t('editor.description', 'Description')}
            </label>
            <textarea
              id="issue-new-description"
              data-testid="issue-new-description-input"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              rows={3}
              className={fieldHints.createInput}
            />

            <label htmlFor="issue-new-category" className={fieldHints.createLabel}>
              {t('editor.category', 'Category')}
            </label>
            <select
              id="issue-new-category"
              data-testid="issue-new-category-select"
              value={newCategory}
              onChange={(e) => setNewCategory(e.target.value)}
              className={fieldHints.createInput}
            >
              <option value="">{t('editor.categoryPlaceholder', 'Select')} --</option>
              {CATEGORY_OPTIONS.map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>

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
