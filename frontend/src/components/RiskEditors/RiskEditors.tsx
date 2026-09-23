import { useCallback, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { useInterviewStartCta } from '../shared/useInterviewStartCta';
import { Dialog } from '../shared/Dialog';
import { RiskList } from './RiskList';
import { RiskArtifactForm } from './RiskArtifactForm';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { TraceLinkPanel } from '../shared/TraceLinkPanel';
import { TraceSpine, useDerivationChain } from '../shared/TraceSpine';
import type { ChainArtifact } from '../shared/TraceSpine';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import { useRiskData } from './useRiskData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { risksApi } from '../../api/risks';
import { CATEGORY_OPTIONS } from './RiskArtifactForm';
// F-04 (code review, 2026-08-19): shared create-form field styles (see
// frontend/src/components/shared/FieldHints.module.css header comment) —
// keeping them in one shared place instead of duplicating them per component.
import fieldHints from '../shared/FieldHints.module.css';
import styles from './RiskEditors.module.css';

export default function RiskEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  // Shared with the other artifact routes so the CTA cannot drift.
  const interviewCta = useInterviewStartCta('Risk');
  const { items, item, isLoading, error, refresh } = useRiskData(selectedId);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  // BUG-11 (Systemaudit 2026-08-18, §4): description/category are ordinary
  // risksApi.create() fields the backend already accepts — they had no
  // editor in this create dialog.
  const [newDescription, setNewDescription] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);

  // 12.1/14.2: named after the result ("New Risk"), not the gesture ("+ New");
  // also the dialog title, matching ch. 12.8 ("dialog title repeats the
  // label of the button that opened it").
  const newRiskLabel = t('risks.newRisk', 'New Risk');

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
      const resp = await risksApi.create({
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
      navigate(`/risks/${resp.id}`);
    } catch (e) {
      console.error(e);
      const msg = (e as { error?: { message?: string } })?.error?.message ?? t('risks.createFailed');
      setCreateError(msg);
    } finally {
      setIsCreating(false);
    }
  };

  const handleSaved = () => { refresh(); };
  const handleDeleted = () => { navigate('/risks'); refresh(); };

  // Trace spine (Task 3.3 — UI concept ch. 5).
  const derivationChain = useDerivationChain(
    item?.artifact_id ?? item?.id ?? null,
    'Risk',
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
      <p role="status" className={styles.loadingStatus}>
        {t('loading', 'Laden...')}
      </p>
    );
  }

  if (error && items.length === 0) {
    return (
      <div role="alert" className={styles.errorContainer}>
        <p className={styles.errorText}>
          {error.message}
        </p>
        <button className="btn-secondary" onClick={refresh} data-testid="risk-reload-btn">
          {t('actions.retry')}
        </button>
      </div>
    );
  }

  return (
    <div data-testid="risks-page" className={styles.page}>
      {/* 12.1: exactly one <h1>, always-visible summary, one primary action. */}
      <PageHeader
        title={t('nav.risks')}
        summary={t('risks.summary', { count: items.length })}
        primaryAction={{
          label: newRiskLabel,
          prefixWithPlus: true,
          onClick: openCreateDialog,
          testId: 'create-risk-btn',
        }}
        // #797: the guided-interview start is a second *create path*, not a
        // variant of the primary one — as a visible secondary button it made
        // this route show two create buttons where Glossary/ICD/Diagram show
        // one. Secondary actions belong in the overflow menu (ch. 12.1), so
        // it moved there: same action, same `interview-start-cta` testid,
        // exactly one visible create CTA per route.
        overflowActions={[interviewCta]}
      />

      <div className={styles.splitWrapper}>
        <SplitView
          leftPanel={
            <RiskList
              items={items}
              selectedId={selectedId}
              onSelect={(id) => navigate(`/risks/${id}`)}
              onCreateNew={openCreateDialog}
            />
          }
          rightPanel={
            <div className={styles.rightPane}>
              <div className={styles.detailScroll}>
                {item && (
                  <TraceSpine
                    stations={derivationChain.stations}
                    isLoading={derivationChain.isLoading}
                    error={derivationChain.error}
                    onOpenArtifact={handleOpenChainArtifact}
                    isOpenable={derivationChain.isOpenable}
                  />
                )}
                {/* DEVIATION from the plan brief: the brief's RiskArtifactForm
                    takes a non-nullable `risk: Risk` (unlike the deleted
                    RiskForm, which accepted `risk: Risk | null` and rendered
                    the "select a risk" placeholder itself). `item` here is
                    `Risk | null` (no row selected yet), so that null-guard
                    moves to this call site instead of being lost. */}
                {item ? (
                  <RiskArtifactForm risk={item} onSaved={handleSaved} onDeleted={handleDeleted} />
                ) : (
                  <p className={styles.selectPlaceholder}>
                    {t('risks.selectRisk')}
                  </p>
                )}
                {/* Task 2.2: the "Neue Verknüpfung" button used to float under
                    the form as an inline-styled one-off. TraceLinkPanel
                    already owns a "new link" action in its own header (same
                    as AdrEditors), so relocating here both fixes the
                    placement and removes the duplicate CreateTraceLinkDialog
                    wiring RiskEditors used to carry on its own. TraceLinkPanel
                    stays as the CRUD surface alongside the read-only Spine
                    above (Task 3.3 decision). */}
                {item && activeWorkspace && (
                  <TraceLinkPanel workspaceId={activeWorkspace.id} artifactId={item.id} />
                )}
              </div>
              {item && (() => {
                const ver: VersionRef = { version: item.version, label: `v${item.version}`, createdAt: null, baselineIds: [] };
                return <RightSidebar kind="risk" artifactId={item.id} currentVersion={ver} hideTraceLinks />;
              })()}
            </div>
          }
          initialLeftWidth={350}
          moduleType="risks"
        />
      </div>

      {showCreateDialog && (
        <Dialog
          title={newRiskLabel}
          onClose={closeCreateDialog}
          testId="risk-create-dialog"
          initialFocusRef={titleInputRef}
          footer={
            <>
              <button
                type="button"
                data-testid="risk-create-cancel-btn"
                className="btn-secondary"
                onClick={closeCreateDialog}
                disabled={isCreating}
              >
                {t('actions.cancel', 'Cancel')}
              </button>
              <button
                type="submit"
                form="risk-create-form"
                data-testid="risk-new-save-btn"
                className="btn-primary"
                disabled={isCreating || !newTitle.trim()}
              >
                {isCreating ? t('actions.saving', 'Saving...') : t('actions.create', 'Erstellen')}
              </button>
            </>
          }
        >
          <form
            id="risk-create-form"
            onSubmit={(e) => { e.preventDefault(); void handleCreateNew(); }}
          >
            <label
              htmlFor="risk-new-title"
              className={styles.createLabel}
            >
              {t('editor.title', 'Title')}
            </label>
            <input
              ref={titleInputRef}
              id="risk-new-title"
              data-testid="risk-new-title-input"
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder={t('risks.titlePlaceholder', 'z. B. Ausfall der Datenbank im Peak-Load')}
              className={styles.createInput}
            />

            {/* BUG-11: description/category — ordinary risksApi.create()
                fields the backend already accepts, previously missing
                here. */}
            <label htmlFor="risk-new-description" className={fieldHints.createLabel}>
              {t('editor.description', 'Description')}
            </label>
            <textarea
              id="risk-new-description"
              data-testid="risk-new-description-input"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              rows={3}
              className={fieldHints.createInput}
            />

            <label htmlFor="risk-new-category" className={fieldHints.createLabel}>
              {t('editor.category', 'Category')}
            </label>
            <select
              id="risk-new-category"
              data-testid="risk-new-category-select"
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
              <p role="alert" className={styles.createError}>
                {createError}
              </p>
            )}
          </form>
        </Dialog>
      )}
    </div>
  );
}
