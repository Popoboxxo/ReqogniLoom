import { useCallback, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { useInterviewStartCta } from '../shared/useInterviewStartCta';
import { IncludeDeletedToggle } from '../shared/IncludeDeletedToggle/IncludeDeletedToggle';
import {
  AiDerivationDialog,
  type AiDerivationDraft,
} from '../shared/AiDerivationDialog';
import { EditorPageShell } from '../shared/EditorPageShell';
import { FormField } from '../shared/FormField';
import { fieldErrorsFromException } from '../shared/ArtifactForm/field-errors';
import { useHasRole } from '../../hooks/useHasRole';
import { useFieldContract } from '../../hooks/useFieldContract';
import { extractApiErrorMessage } from '../../api/client';
import { AdrList } from './AdrList';
import { AdrArtifactForm } from './AdrArtifactForm';
import { AdrSupersedePanel } from './AdrSupersedePanel';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { TraceLinkPanel } from '../shared/TraceLinkPanel';
import { TraceSpine, useDerivationChain } from '../shared/TraceSpine';
import type { ChainArtifact } from '../shared/TraceSpine';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import { useAdrData } from './useAdrData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { adrsApi } from '../../api/adrs';
import type { Adr } from '../../types';
// F-04 (code review, 2026-08-19): shared create-form field styles (see
// frontend/src/components/shared/FieldHints.module.css header comment) —
// keeping them in one shared place instead of duplicating them per component.
import fieldHints from '../shared/FieldHints.module.css';
import styles from './AdrEditors.module.css';

export default function AdrEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  // R2/T1-convention: the derivation is a write action (editor+).
  const hasRole = useHasRole();
  // Shared with the other artifact routes so the CTA cannot drift.
  const interviewCta = useInterviewStartCta('Adr');
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const { items, item, isLoading, error, refresh } = useAdrData(selectedId, includeDeleted);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  // BUG-11 (Systemaudit 2026-08-18, §4): `description` is an ordinary
  // adrsApi.create() field the backend already accepts — it had no editor
  // in this create dialog.
  const [newDescription, setNewDescription] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  // GitHub #1392 (second half): a 400 names the offending field
  // (`details[].field`) — the message belongs next to that input, not only in
  // the dialog's generic banner.
  const [createFieldErrors, setCreateFieldErrors] = useState<Record<string, string[]>>({});
  const [isCreating, setIsCreating] = useState(false);
  const titleInputRef = useRef<HTMLInputElement>(null);
  // GitHub #1393/#1392: `required` and `maxLength` come from the workspace's
  // own configuration (create-form definition first, attribute definition as
  // the documented fallback) — never from a constant in this file.
  const { field } = useFieldContract('Adr', { enabled: showCreateDialog });
  const titleField = field('title');

  // 12.1/14.2: named after the result ("New ADR"), not the gesture ("+ New");
  // also the dialog title, matching ch. 12.8 ("dialog title repeats the
  // label of the button that opened it").
  const newAdrLabel = t('adrs.newAdr', 'New ADR');

  // #1358/#1360 (W12c): AI ADR derivation state. The decision text is part of
  // the dialog's setup step (`drafts === null`), because the preview prompt
  // needs it; `mode="write"` only becomes reachable after a preview.
  const [deriveOpen, setDeriveOpen] = useState(false);
  const [deriveDecision, setDeriveDecision] = useState('');
  const [deriveDrafts, setDeriveDrafts] = useState<AiDerivationDraft[] | null>(null);
  const [deriveLoading, setDeriveLoading] = useState(false);
  const [deriveLoadError, setDeriveLoadError] = useState<string | null>(null);
  const [deriveSaving, setDeriveSaving] = useState(false);
  const [deriveSubmitError, setDeriveSubmitError] = useState<string | null>(null);
  const [deriveStatus, setDeriveStatus] = useState<string | null>(null);

  const openDeriveDialog = useCallback((): void => {
    setDeriveDecision('');
    setDeriveDrafts(null);
    setDeriveLoadError(null);
    setDeriveSubmitError(null);
    setDeriveOpen(true);
  }, []);

  const closeDeriveDialog = useCallback((): void => {
    setDeriveOpen(false);
    setDeriveDrafts(null);
    setDeriveLoadError(null);
    setDeriveSubmitError(null);
  }, []);

  const handleDerivePreview = useCallback(async (): Promise<void> => {
    if (!activeWorkspace || !deriveDecision.trim()) return;
    setDeriveLoading(true);
    setDeriveLoadError(null);
    try {
      const preview = await adrsApi.derivePreview(activeWorkspace.id, deriveDecision.trim());
      const draft = preview.draft;
      setDeriveDrafts([
        {
          title: draft.title,
          // The reviewer sees every part of the draft the write will persist;
          // the dialog's three-part row (title/description/rationale) is the
          // shared shape, so context/consequences are folded into the body.
          description: [
            draft.description,
            draft.context ? `${t('aiDerivation.adrContext')}: ${draft.context}` : null,
            draft.consequences
              ? `${t('aiDerivation.adrConsequences')}: ${draft.consequences}`
              : null,
          ]
            .filter(Boolean)
            .join('\n\n'),
        },
      ]);
    } catch (e) {
      const msg =
        (e as { error?: { message?: string } })?.error?.message ?? t('needs.deriveFailed');
      setDeriveLoadError(msg);
    } finally {
      setDeriveLoading(false);
    }
  }, [activeWorkspace, deriveDecision, t]);

  const handleDeriveDecision = useCallback(
    async (parked: boolean): Promise<void> => {
      if (!activeWorkspace || !deriveDecision.trim()) return;
      setDeriveSaving(true);
      setDeriveSubmitError(null);
      try {
        await adrsApi.deriveWrite(activeWorkspace.id, deriveDecision.trim());
        setDeriveStatus(
          t(parked ? 'aiDerivation.statusParked' : 'aiDerivation.statusCreated', {
            count: 1,
          })
        );
        closeDeriveDialog();
        refresh();
      } catch (e) {
        const msg =
          (e as { error?: { message?: string } })?.error?.message ?? t('needs.deriveFailed');
        setDeriveSubmitError(msg);
      } finally {
        setDeriveSaving(false);
      }
    },
    [activeWorkspace, deriveDecision, t, closeDeriveDialog, refresh]
  );

  const openCreateDialog = useCallback((): void => {
    setCreateError(null);
    setCreateFieldErrors({});
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
      const msg = extractApiErrorMessage(e) ?? t('adrs.createFailed');
      // The banner keeps the overall reason (so a failure with no field detail
      // is still visible); the per-field half renders under the control.
      setCreateError(msg);
      setCreateFieldErrors(fieldErrorsFromException(e, msg));
    } finally {
      setIsCreating(false);
    }
  };

  // UI-LOW-3 (Systemaudit, LOW finding): `updated` is set only by the
  // ADR-Supersede flow (AdrSupersedePanel.handleSupersede) — see
  // useAdrData.refresh's doc comment for why that path needs a synchronous
  // cache write instead of only an invalidate-triggered refetch.
  const handleSaved = (updated?: Adr) => { refresh(updated); };
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
        {/* UI-LOW-3 follow-up (code review): `refresh` now takes an optional
            `updated` entity, so it must NOT be passed as a bare event handler
            — React would hand it the click's SyntheticEvent, which
            `useAdrData.refresh` would then write into the detail cache via
            setQueryData. Explicit zero-arg call instead. */}
        <button
          className="btn-secondary"
          onClick={() => refresh()}
          data-testid="adr-reload-btn"
        >
          {t('actions.retry')}
        </button>
      </div>
    );
  }

  return (
    <div data-testid="adrs-page" className={styles.page}>
      {/* 12.1: exactly one <h1>, always-visible summary, one primary action —
          replaces the bare <h3> that used to live inside AdrList (issue: the
          "+ New" button sat in the list toolbar, in violation of 12.2). */}
      <PageHeader
        title={t('nav.adrs')}
        summary={t('adrs.summary', { count: items.length })}
        primaryAction={{
          label: newAdrLabel,
          prefixWithPlus: true,
          onClick: openCreateDialog,
          testId: 'create-adr-btn',
        }}
        // #797: the guided-interview start is a second *create path*, not a
        // variant of the primary one — as a visible secondary button it made
        // this route show two create buttons where Glossary/ICD/Diagram show
        // one. Secondary actions belong in the overflow menu (ch. 12.1), so
        // it moved there: same action, same `interview-start-cta` testid,
        // exactly one visible create CTA per route.
        //
        // #1358/#1360: the ADR derivation had no UI entry at all — it joins
        // the same overflow menu (editor-only: it is a write action). The
        // interview CTA stays the literal first entry (ch. 12.1 convention,
        // see `action-labels.test.ts`'s overflow-menu check).
        overflowActions={[
          interviewCta,
          ...(hasRole('editor')
            ? [
                {
                  label: t('aiDerivation.adrAction'),
                  onClick: openDeriveDialog,
                  disabled: !activeWorkspace,
                  testId: 'adr-derive-btn',
                },
              ]
            : []),
        ]}
      />

      {deriveStatus && (
        <p role="status" data-testid="adr-derive-status" className={styles.deriveStatus}>
          {deriveStatus}
        </p>
      )}

      <div className={styles.splitWrapper}>
        <SplitView
          leftPanel={
            <div>
              <IncludeDeletedToggle
                checked={includeDeleted}
                onChange={setIncludeDeleted}
                testIdPrefix="adr-list"
              />
              <AdrList
                items={items}
                selectedId={selectedId}
                onSelect={(id) => navigate(`/adrs/${id}`)}
                onCreateNew={openCreateDialog}
                workspaceId={activeWorkspace?.id ?? null}
              />
            </div>
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
                {/* DEVIATION from the plan brief: the brief's AdrArtifactForm
                    takes a non-nullable `adr: Adr` (unlike the deleted
                    AdrForm, which accepted `adr: Adr | null` and rendered the
                    "select an ADR" placeholder itself). `item` here is
                    `Adr | null` (no row selected yet), so that null-guard
                    moves to this call site instead of being lost — same
                    pattern as RiskEditors/IssueEditors (Tasks 19/20). The
                    ADR-Supersede-Flow has no equivalent inside ArtifactForm,
                    so it stays a standalone sibling (see AdrSupersedePanel's
                    doc comment) rendered right below the form. */}
                {item ? (
                  // F-2 (code review, Task 21 fix round): `key` forces
                  // ArtifactForm's internal `useEntityReset` to remount on
                  // status change too, not just `entityId` change — without
                  // it, a Supersede leaves the form showing the pre-Supersede
                  // status (e.g. stale "Approved") because `initialValues`'s
                  // object identity change alone isn't enough to trigger a
                  // reset (regression of UI-LOW-3).
                  <>
                    <AdrArtifactForm key={`${item.id}:${item.status}`} adr={item} onSaved={() => handleSaved()} onDeleted={handleDeleted} />
                    <AdrSupersedePanel adr={item} otherAdrs={items} onSaved={handleSaved} />
                  </>
                ) : (
                  <p className={styles.selectPlaceholder}>
                    {t('adrs.selectAdr')}
                  </p>
                )}
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

      <EditorPageShell
        open={showCreateDialog}
        title={newAdrLabel}
        testId="adr-create-dialog"
        formId="adr-create-form"
        // The dialog's own focusable-order default would land on the close
        // (×) button, not the title field — same as CreateWorkspaceModal,
        // point the trap at the field the user actually wants to type into.
        initialFocusRef={titleInputRef}
        onClose={closeCreateDialog}
        onSubmit={handleCreateNew}
        isSaving={isCreating}
        canSave={newTitle.trim().length > 0}
        cancelTestId="adr-create-cancel-btn"
        saveTestId="adr-new-save-btn"
        error={createError}
        errorClassName={styles.createError}
      >
        {/* #1393: required marker + #1392: `maxLength` straight off the
            server contract (`Adr.title` is 200 characters on both the model and
            the serializer). */}
        <FormField
          htmlFor="adr-new-title"
          label={t('editor.title', 'Title')}
          required={titleField.required}
          error={createFieldErrors.title?.join(', ')}
          labelClassName={styles.createLabel}
        >
          <input
            ref={titleInputRef}
            id="adr-new-title"
            data-testid="adr-new-title-input"
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder={t('adr.newTitlePlaceholder', 'e.g. Use PostgreSQL as the primary datastore')}
            className={styles.createInput}
            {...titleField.controlProps}
          />
        </FormField>

        {/* BUG-11: description — an ordinary adrsApi.create() field the
            backend already accepts, previously missing here. Optional on the
            server, so no marker; a rejected description still gets a
            field-bound message. */}
        <FormField
          htmlFor="adr-new-description"
          label={t('editor.description', 'Description')}
          required={field('description').required}
          error={createFieldErrors.description?.join(', ')}
          labelClassName={fieldHints.createLabel}
        >
          <textarea
            id="adr-new-description"
            data-testid="adr-new-description-input"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            rows={3}
            className={fieldHints.createInput}
            {...field('description').controlProps}
          />
        </FormField>
      </EditorPageShell>

      {/* #1358/#1360 (W12c): the shared AI review dialog. The decision text is
          this flow's setup step (the preview prompt needs it); only after a
          preview exists do Confirm / "Review later" reach the write seam. */}
      {deriveOpen && (
        <AiDerivationDialog
          open
          title={t('aiDerivation.adrDialogTitle')}
          sourceLabel={t('aiDerivation.adrSource')}
          drafts={deriveDrafts}
          isLoading={deriveLoading}
          loadError={deriveLoadError}
          isSubmitting={deriveSaving}
          submitError={deriveSubmitError}
          confirmDisabled={!deriveDecision.trim()}
          intro={
            <label className={styles.createLabel}>
              {t('aiDerivation.adrDecisionLabel')}
              <textarea
                value={deriveDecision}
                onChange={(e) => setDeriveDecision(e.target.value)}
                placeholder={t('aiDerivation.adrDecisionPlaceholder')}
                rows={3}
                className={fieldHints.createInput}
                // Once a preview exists the text is the prompt the shown draft
                // came from; editing it silently would make Confirm persist a
                // different derivation than the one on screen (the write seam
                // regenerates from this text). Discard + reopen to change it.
                disabled={deriveLoading || deriveSaving || deriveDrafts !== null}
                data-testid="adr-derive-decision-input"
              />
            </label>
          }
          onPreview={() => void handleDerivePreview()}
          onConfirm={() => void handleDeriveDecision(false)}
          onReviewLater={() => void handleDeriveDecision(true)}
          onDiscard={closeDeriveDialog}
          testIdPrefix="adr-derive"
        />
      )}
    </div>
  );
}
