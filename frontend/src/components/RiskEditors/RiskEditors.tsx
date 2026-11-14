import { useCallback, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { ArtifactId } from '../shared/ArtifactId';
import { StatusBadge } from '../shared/StatusBadge';
import { useInterviewStartCta } from '../shared/useInterviewStartCta';
import { IncludeDeletedToggle } from '../shared/IncludeDeletedToggle/IncludeDeletedToggle';
import { EditorPageShell } from '../shared/EditorPageShell';
import { FormField } from '../shared/FormField';
import { fieldErrorsFromException } from '../shared/ArtifactForm/field-errors';
import { useFieldContract } from '../../hooks/useFieldContract';
import { extractApiErrorMessage } from '../../api/client';
import { RiskList } from './RiskList';
import { RiskArtifactForm } from './RiskArtifactForm';
import { InspectorShell } from '../shared/ArtifactInspector';
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
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const { items, item, isLoading, error, refresh } = useRiskData(selectedId, includeDeleted);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  // BUG-11 (Systemaudit 2026-08-18, §4): description/category are ordinary
  // risksApi.create() fields the backend already accepts — they had no
  // editor in this create dialog.
  const [newDescription, setNewDescription] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  // GitHub #1392 (second half): a 400 names the offending field
  // (`details[].field`) — that message belongs next to the control, not
  // only in the dialog's generic banner.
  const [createFieldErrors, setCreateFieldErrors] = useState<Record<string, string[]>>({});
  const [isCreating, setIsCreating] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);
  // GitHub #1393/#1392: `required` and `maxLength` come from the
  // workspace's own configuration (create-form definition first, the
  // attribute definition as the documented fallback) — never from a
  // constant in this file.
  const { field } = useFieldContract('Risk', { enabled: showCreateDialog });

  // 12.1/14.2: named after the result ("New Risk"), not the gesture ("+ New");
  // also the dialog title, matching ch. 12.8 ("dialog title repeats the
  // label of the button that opened it").
  const newRiskLabel = t('risks.newRisk', 'New Risk');

  const openCreateDialog = useCallback((): void => {
    setCreateError(null);
    setCreateFieldErrors({});
    setNewTitle('');
    setNewDescription('');
    setNewCategory('');
    setShowCreateDialog(true);
  }, []);

  const closeCreateDialog = useCallback((): void => {
    setShowCreateDialog(false);
    setCreateError(null);
    setCreateFieldErrors({});
  }, []);

  const handleCreateNew = async (): Promise<void> => {
    // FR-U5-01: the same-tick submit guard for the button and the `Ctrl`/`Cmd`+`S`
    // chord now lives in the shared `EditorPageShell` this page renders.
    if (!activeWorkspace) return;
    if (!newTitle.trim()) return;
    setCreateError(null);
    setCreateFieldErrors({});
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
      const msg = extractApiErrorMessage(e) ?? t('risks.createFailed');
      // The banner keeps the overall reason (a failure with no field
      // detail must stay visible); the per-field half renders under the
      // control that was named.
      setCreateError(msg);
      setCreateFieldErrors(fieldErrorsFromException(e, msg));
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

  // #1762 (M2, mirrors M1): the inspector's programmatic focus targets live in
  // the route, not in the shell — the shell must not know the detail area's DOM
  // (it only receives `coveredRef` for the `inert` bracket).
  const detailScrollRef = useRef<HTMLDivElement | null>(null);

  const focusInspectorHeading = useCallback((): void => {
    document.getElementById('inspector-heading')?.focus();
  }, []);

  // Spec §2.3 rule 1: the Links tab's summary line jumps into the spine. The
  // spine is a separate flex zone now, so this is the one place that knows its
  // first station.
  const focusSpine = useCallback((): void => {
    document
      .querySelector<HTMLElement>('[data-testid="trace-spine-station-button"]')
      ?.focus();
  }, []);

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
          list={
            <div>
              <IncludeDeletedToggle
                checked={includeDeleted}
                onChange={setIncludeDeleted}
                testIdPrefix="risk-list"
              />
              <RiskList
                items={items}
                selectedId={selectedId}
                onSelect={(id) => navigate(`/risks/${id}`)}
                onCreateNew={openCreateDialog}
                workspaceId={activeWorkspace?.id ?? null}
              />
            </div>
          }
          detail={
            <div className={styles.rightPane}>
              <div className={styles.detailScroll} ref={detailScrollRef}>
                {/* Spec §5.1 #1: the skip link is the first focusable element
                    of the detail area (#1762 M2). */}
                {item && (
                  <a
                    href="#inspector-heading"
                    className={`btn-ghost ${styles.inspectorSkipLink}`}
                    data-testid="inspector-skip-link"
                    onClick={(event) => {
                      event.preventDefault();
                      focusInspectorHeading();
                    }}
                  >
                    {t('sidebar.inspector.skipLink', 'Jump to the inspector')}
                  </a>
                )}
                {/* DoD 2 (#1762/M2): identity + workflow status live in the
                    artifact head of the route, never in the inspector
                    (spec §2.2). */}
                {item && (
                  <div className={styles.artifactHead} data-testid="risk-artifact-head">
                    <ArtifactId
                      value={item.uid}
                      fallback={item.id.slice(0, 8)}
                      testId="risk-detail-id"
                    />
                    <StatusBadge status={item.status} testId="risk-detail-status" />
                  </div>
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
                // #1762 (M2): `item.id` is the Risk entity id (versions/diff),
                // the backing Artifact UUID comes from `item.artifact_id` and is
                // what the comments route needs (#1763 publishes it).
                return (
                  <InspectorShell
                    kind="risk"
                    entityId={item.id}
                    artifactPk={item.artifact_id ?? null}
                    currentVersion={ver}
                    coveredRef={detailScrollRef}
                    onShowInSpine={focusSpine}
                  />
                );
              })()}
            </div>
          }
          spine={
            item ? (
              <TraceSpine
                stations={derivationChain.stations}
                isLoading={derivationChain.isLoading}
                error={derivationChain.error}
                onOpenArtifact={handleOpenChainArtifact}
                isOpenable={derivationChain.isOpenable}
              />
            ) : null
          }
          ratio={[40, 60]}
          minWidths={[320, 448]}
          containerClassName={styles.splitWrapper}
        />
      </div>

      <EditorPageShell
        open={showCreateDialog}
        title={newRiskLabel}
        testId="risk-create-dialog"
        formId="risk-create-form"
        initialFocusRef={titleInputRef}
        onClose={closeCreateDialog}
        onSubmit={handleCreateNew}
        isSaving={isCreating}
        canSave={newTitle.trim().length > 0}
        // #1595: the blocked Create button points at the field hint
        // rendered below, so the disabled state is explainable.
        saveHintId={newTitle.trim().length === 0 ? 'risk-new-title-hint' : undefined}
        cancelTestId="risk-create-cancel-btn"
        saveTestId="risk-new-save-btn"
        error={createError}
        errorClassName={styles.createError}
      >
        {/* #1393: required marker from the server contract; #1392: `maxLength`
            from the same definition (the column's own 255-character bound). */}
        <FormField
          htmlFor="risk-new-title"
          label={t('editor.title', 'Title')}
          required={field('title').required}
          hint={
            newTitle.trim().length === 0
              ? t('editor.titleRequired', 'Titel ist erforderlich.')
              : null
          }
          error={createFieldErrors.title?.join(', ')}
          labelClassName={styles.createLabel}
        >
          <input
            ref={titleInputRef}
            id="risk-new-title"
            data-testid="risk-new-title-input"
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder={t('risks.titlePlaceholder', 'z. B. Ausfall der Datenbank im Peak-Load')}
            className={styles.createInput}
            {...field('title').controlProps}
          />
        </FormField>

        {/* BUG-11: description/category — ordinary risksApi.create()
            fields the backend already accepts, previously missing
            here. */}
        <FormField
          htmlFor="risk-new-description"
          label={t('editor.description', 'Description')}
          required={field('description').required}
          error={createFieldErrors.description?.join(', ')}
          labelClassName={fieldHints.createLabel}
        >
          <textarea
            id="risk-new-description"
            data-testid="risk-new-description-input"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            rows={3}
            className={fieldHints.createInput}
            {...field('description').controlProps}
          />
        </FormField>

        <FormField
          htmlFor="risk-new-category"
          label={t('editor.category', 'Category')}
          required={field('category').required}
          error={createFieldErrors.category?.join(', ')}
          labelClassName={fieldHints.createLabel}
        >
          <select
            id="risk-new-category"
            data-testid="risk-new-category-select"
            value={newCategory}
            onChange={(e) => setNewCategory(e.target.value)}
            className={fieldHints.createInput}
            {...field('category').selectProps}
          >
            <option value="">{t('editor.categoryPlaceholder', 'Select')} --</option>
            {CATEGORY_OPTIONS.map((o) => (
              <option key={o} value={o}>{o}</option>
            ))}
          </select>
        </FormField>
      </EditorPageShell>
    </div>
  );
}
