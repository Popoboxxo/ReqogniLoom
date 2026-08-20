import { useCallback, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { Dialog } from '../shared/Dialog';
import { AdrList } from './AdrList';
import { AdrForm } from './AdrForm';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { TraceLinkPanel } from '../shared/TraceLinkPanel';
import { TraceSpine, useDerivationChain } from '../shared/TraceSpine';
import type { ChainArtifact } from '../shared/TraceSpine';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import { useAdrData } from './useAdrData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { adrsApi } from '../../api/adrs';
// F-04 (code review, 2026-08-19): shared create-form field styles (see
// frontend/src/components/shared/FieldHints.module.css header comment) —
// keeping them in one shared place instead of duplicating them per component.
import fieldHints from '../shared/FieldHints.module.css';

export default function AdrEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { items, item, isLoading, error, refresh } = useAdrData(selectedId);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  // BUG-11 (Systemaudit 2026-08-18, §4): `description` is an ordinary
  // adrsApi.create() field the backend already accepts — it had no editor
  // in this create dialog.
  const [newDescription, setNewDescription] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);

  // 12.1/14.2: named after the result ("New ADR"), not the gesture ("+ New");
  // also the dialog title, matching ch. 12.8 ("dialog title repeats the
  // label of the button that opened it").
  const newAdrLabel = t('adrs.newAdr', 'New ADR');

  const openCreateDialog = useCallback((): void => {
    setCreateError(null);
    setNewTitle('');
    setNewDescription('');
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
      const resp = await adrsApi.create({
        workspace_id: activeWorkspace.id,
        title: newTitle.trim(),
        // BUG-11: only send what was actually typed.
        ...(newDescription.trim() ? { description: newDescription.trim() } : {}),
      });
      setNewTitle('');
      setNewDescription('');
      setShowCreateDialog(false);
      refresh();
      navigate(`/adrs/${resp.id}`);
    } catch (e) {
      console.error(e);
      const msg = (e as { error?: { message?: string } })?.error?.message ?? t('adrs.createFailed');
      setCreateError(msg);
    } finally {
      setIsCreating(false);
    }
  };

  const handleSaved = () => { refresh(); };
  const handleDeleted = () => { navigate('/adrs'); refresh(); };

  // Trace spine (Task 3.3 — UI concept ch. 5).
  const derivationChain = useDerivationChain(
    item?.artifact_id ?? item?.id ?? null,
    'Adr',
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
        <button className="btn-secondary" onClick={refresh} data-testid="adr-reload-btn">
          {t('actions.retry')}
        </button>
      </div>
    );
  }

  return (
    <div data-testid="adrs-page" style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* 12.1: exactly one <h1>, always-visible summary, one primary action —
          replaces the bare <h3> that used to live inside AdrList (issue: the
          "+ New" button sat in the list toolbar, in violation of 12.2). */}
      <PageHeader
        title={t('nav.adrs')}
        summary={t('adrs.summary', { count: items.length })}
        primaryAction={{
          label: newAdrLabel,
          onClick: openCreateDialog,
          testId: 'create-adr-btn',
        }}
        secondaryActions={[
          {
            label: t('interviews.startCta'),
            onClick: () => navigate('/interviews?start=Adr'),
            disabled: !activeWorkspace,
            testId: 'interview-start-cta',
          },
        ]}
      />

      <div style={{ flex: '1 1 auto', minHeight: '60vh' }}>
        <SplitView
          leftPanel={
            <AdrList
              items={items}
              selectedId={selectedId}
              onSelect={(id) => navigate(`/adrs/${id}`)}
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
                <AdrForm adr={item} onSaved={handleSaved} onDeleted={handleDeleted} />
                {/* TraceLinkPanel stays: it is the create/delete CRUD surface
                    for trace links (Task 3.3 decision — the Spine above is a
                    read-only derivation-chain view, not a link editor). */}
                {item && activeWorkspace && (
                  <TraceLinkPanel workspaceId={activeWorkspace.id} artifactId={item.id} />
                )}
              </div>
              {item && (() => {
                const ver: VersionRef = { version: item.version, label: `v${item.version}`, createdAt: null, baselineIds: [] };
                return <RightSidebar kind="adr" artifactId={item.id} currentVersion={ver} hideTraceLinks />;
              })()}
            </div>
          }
          initialLeftWidth={350}
          moduleType="adrs"
        />
      </div>

      {showCreateDialog && (
        <Dialog
          title={newAdrLabel}
          onClose={closeCreateDialog}
          testId="adr-create-dialog"
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
                form="adr-create-form"
                data-testid="adr-new-save-btn"
                className="btn-primary"
                disabled={isCreating || !newTitle.trim()}
              >
                {isCreating ? t('actions.saving', 'Saving...') : t('actions.create', 'Create')}
              </button>
            </>
          }
        >
          <form
            id="adr-create-form"
            onSubmit={(e) => { e.preventDefault(); void handleCreateNew(); }}
          >
            <label
              htmlFor="adr-new-title"
              style={{ display: 'block', fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--color-text)', marginBottom: 'var(--space-1)' }}
            >
              {t('editor.title', 'Title')}
            </label>
            <input
              ref={titleInputRef}
              id="adr-new-title"
              data-testid="adr-new-title-input"
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder={t('editor.newNeedTitle', 'e.g. As a user, I need...')}
              style={{
                width: '100%', boxSizing: 'border-box', padding: 'var(--space-2) var(--space-3)',
                borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border)',
                fontSize: 'var(--font-size-sm)', background: 'var(--color-surface)', color: 'var(--color-text)',
              }}
            />

            {/* BUG-11: description — an ordinary adrsApi.create() field the
                backend already accepts, previously missing here. */}
            <label htmlFor="adr-new-description" className={fieldHints.createLabel}>
              {t('editor.description', 'Description')}
            </label>
            <textarea
              id="adr-new-description"
              data-testid="adr-new-description-input"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              rows={3}
              className={fieldHints.createInput}
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
