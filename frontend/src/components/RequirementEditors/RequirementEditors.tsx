/**
 * ARCH-L1-001 ReactFrontend — RequirementEditors (COMP-RF-003)
 *
 * leaf_id: COMP-RF-003
 * req_id: REQ-L2-RF-003 (Requirements-Editor mit Inline-Editing und Markdown),
 * REQ-L3-RF003-001 (Inline-Editing — Title, Description, Category),
 * REQ-L3-RF003-002 (Workflow-State-Anzeige + Transition),
 * REQ-L3-RF003-003 (TraceabilityPanel),
 * REQ-L3-RF003-004 (Editor-Performance < 500ms),
 * REQ-L3-RF003-005 (Type-dependent mask rendering),
 * REQ-003 (skalierbare Listen-Toolbar — Suche/Filter/Sortierung)
 *
 * Interfaces implemented:
 * IF-RF-INT-001 ← NavigationShell activates
 * IF-RF-INT-002 ← I18nService via useTranslation
 * IF-RF-INT-003 ← artifact_id URL params
 * IF-RF-EXT-OUT-001 → GET/POST/PATCH/DELETE /api/v1/requirements/
 *
 * Refactored to use:
 * - SplitView component for resizable list/detail layout
 * - RequirementList (left panel) — searchable list with filtering
 * - RequirementArtifactForm (right panel, Task 25) — definition-driven
 *   `ArtifactForm` renderer (spec section 6.2). Field visibility/order comes
 *   from the resolved attribute definition; the legacy `EntityTypeProvider` /
 *   attribute-visibility prop chain is retired for this type, same as
 *   every other migrated rollout wave.
 */

import { useState, useCallback, useMemo, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  useRequirementData,
  type RequirementAllocationFilter,
  isRequirementAllocationFilter,
  requirementAllocationStorageKey,
  type RequirementLevelFilter,
  isRequirementLevelFilter,
  requirementLevelStorageKey,
} from './useRequirementData';
import { useRequirementAiDerivation } from './use-requirement-ai-derivation';
import { useRequirementCreateForm } from './use-requirement-create-form';
import { useRequirementRouteActions } from './use-requirement-route-actions';
import { useHasRole } from '../../hooks/useHasRole';
import { usePersistedListState } from '../../hooks/usePersistedListState';
import { useCreateRequirement } from '../../queries/requirements';
import { extractApiErrorMessage } from '../../api/client';
import { useWorkspace } from '../../context/WorkspaceContext';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { ArtifactId } from '../shared/ArtifactId';
import { StatusBadge } from '../shared/StatusBadge';
import { useInterviewStartCta } from '../shared/useInterviewStartCta';
import { IncludeDeletedToggle } from '../shared/IncludeDeletedToggle/IncludeDeletedToggle';
import { RequirementList } from './RequirementList';
import { ArtifactTableView } from '../shared/ArtifactTable';
import {
  RequirementViewToggle,
  readRequirementViewMode,
  writeRequirementViewMode,
  type RequirementViewMode,
} from './RequirementViewToggle';
import { GroupManager } from './GroupManager';
import { AddToGroupDialog } from './AddToGroupDialog';
import { useRequirementGroups } from './useRequirementGroups';
import { RequirementArtifactForm, REQUIREMENT_ATTRIBUTE_OVERRIDES } from './RequirementArtifactForm';
import { ArtifactForm, type ArtifactFormValues } from '../shared/ArtifactForm';
import { ReqTraceLinkPanel } from './ReqTraceLinkPanel';
import { AiActionSection, type AiActionDescriptor } from '../shared/AiActions';
import { AiDerivationDialog } from '../shared/AiDerivationDialog';
import { SimilarRequirementsPanel } from './SimilarRequirementsPanel';
import { ArtifactMemoryPanel } from '../Memory/ArtifactMemoryPanel';
import { DeriveTestCasePanel } from '../TestCaseEditors/DeriveTestCasePanel';
import { Dialog } from '../shared/Dialog';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { CustomFieldsEditor } from '../shared/CustomFieldsEditor';
import { InspectorShell } from '../shared/ArtifactInspector';
import { TraceSpineFooter } from '../shared/TraceSpine';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import { useTraceFooterVisible } from '../../hooks/useTraceFooterVisible';
import { useTreeWidth } from '../../hooks/useTreeWidth';
import { BaselineDriftBadge } from '../shared/BaselineDriftBadge/BaselineDriftBadge';
import styles from './RequirementEditors.module.css';
import { RequirementCreateFallbackForm } from './RequirementCreateFallbackForm';
import {
  buildAiActions,
} from './requirement-editors.logic';
import { useRequirementInspector } from './use-requirement-inspector';
import { useRequirementListActions } from './use-requirement-list-actions';
import { useRequirementSelection } from './use-requirement-selection';

/**
 * RequirementEditors — main view with SplitView (list | detail)
 */
export default function RequirementEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  // R2/T1 (systemaudit 2026-09-02): a viewer must not see the "Testfall
  // generieren" trigger or the "KI-Ableitung" button (REQ-008) — only the
  // server rejected those writes before. Both now live in the single
  // `<AiActionSection>` (issue #1092), whose action list this gate empties.
  // Shared with SidebarNavigation/RequirementForm/RequirementList via
  // useHasRole.
  const hasRole = useHasRole();
  // Shared with the other artifact routes so the CTA cannot drift.
  const interviewCta = useInterviewStartCta('Requirement');
  // Task 4.9 (table view): list/table mode persists per browser. A blocked
  // localStorage degrades to list mode instead of failing the page.
  const [viewMode, setViewMode] = useState<RequirementViewMode>(readRequirementViewMode);
  const handleViewModeChange = useCallback((mode: RequirementViewMode) => {
    setViewMode(mode);
    writeRequirementViewMode(mode);
  }, []);
  // GH-443: opt-in to soft-deleted requirements (status="outdated").
  const [includeDeleted, setIncludeDeleted] = useState(false);
  // #1668: allocation filter. It is a **server-side** filter (`?allocated=`),
  // so its state has to live here — next to the data hook — rather than inside
  // RequirementList, which only owns the client-side search/filter controls.
  // Persistence follows the same BUG-19 rule as the other list filters: keyed
  // per workspace, sessionStorage, so a round-trip through a detail view (or a
  // workspace switch) keeps each workspace's own selection.
  const [allocation, setAllocation] = usePersistedListState<RequirementAllocationFilter>(
    requirementAllocationStorageKey(activeWorkspace?.id),
    'all',
    { validate: isRequirementAllocationFilter },
  );
  // V6 (triage 2026-11-10): the level filter is server-side too (`?level=`), so
  // it lives next to the allocation filter and follows the same persistence
  // rule (per workspace, sessionStorage).
  const [level, setLevel] = usePersistedListState<RequirementLevelFilter>(
    requirementLevelStorageKey(activeWorkspace?.id),
    'all',
    { validate: isRequirementLevelFilter },
  );
  const {
    requirements,
    requirement,
    isLoading,
    error,
    refresh,
  } = useRequirementData(selectedId, { includeDeleted, allocation, level });

  // ---- Cohesion hooks (S3.2 WP-5) ----
  // The unsaved-changes guard (form + custom fields), the list-level writes
  // (reparent/delete + their shared error banner) and the trace-spine/inspector
  // focus contract each own one decision.
  const {
    setIsFormDirty,
    pendingSelectId,
    setPendingSelectId,
    customFieldsDraft,
    setCustomFieldsDraft,
    selectRequirement,
    confirmPendingSelect,
    handleSaved,
  } = useRequirementSelection({ selectedId, requirement, refresh });
  const {
    actionError,
    setActionError,
    handleReorder,
    handleDelete,
  } = useRequirementListActions({
    requirements,
    workspaceId: activeWorkspace?.id,
    refresh,
    t,
  });

  // P6 Task 6.3: visual groups. Loaded here (not in RequirementList) so the
  // list itself stays free of group API state and its focused unit tests keep
  // rendering without mocks; viewers get the read-only pseudo-folders, editors
  // additionally get the manager dialog.
  const requirementGroups = useRequirementGroups(
    activeWorkspace?.id ?? null,
    requirements,
  );
  // G1 (spec §4.1/§4.5.1): the group administration is a dialog now, not a
  // permanently mounted box. Closed by default — in the idle state nothing of
  // the manager is in the DOM, so the tree starts directly under the toolbar.
  const [isGroupManagerOpen, setIsGroupManagerOpen] = useState(false);
  // G2 (spec §4.5.3): the row action "Zu Gruppe hinzufügen…" opens a dialog for
  // exactly one requirement. Only the *id* is state — the requirement itself is
  // read from the current list, so a refresh that removes the row (filter,
  // delete) closes the dialog instead of leaving it pointed at a ghost.
  const [addToGroupId, setAddToGroupId] = useState<string | null>(null);
  const addToGroupRequirement = addToGroupId
    ? requirements.find((req) => req.id === addToGroupId)
    : undefined;

  const createRequirement = useCreateRequirement();

  // Create form state
  // BUG-11: `description`/`category` are ordinary create() fields the backend
  // accepts, so the inline form has editors for them (#598 S2 — own module).
  const {
    showCreateForm,
    newTitle,
    newDescription,
    newCategory,
    isCreating,
    createError,
    setNewTitle,
    setNewDescription,
    setNewCategory,
    setCreating,
    setCreateError,
    openCreateForm,
    toggleCreateForm,
    closeCreateForm,
  } = useRequirementCreateForm();
  const {
    isExportingPdf,
    showDeriveTestcasePanel,
    exportPdf,
    openDeriveTestcasePanel,
    closeDeriveTestcasePanel,
  } = useRequirementRouteActions({
    workspaceId: activeWorkspace?.id,
    t,
    onError: setActionError,
  });

  // PDF export state

  // REQ-008: AI-derive state for Anforderungen view (#598 S2 — own module).
  const {
    showAiDeriveDialog,
    aiDrafts,
    aiDraftLoadError,
    aiDraftSubmitError,
    isAiDeriving,
    isAiSaving,
    aiDeriveStatus,
    aiDeriveIsError,
    handleAiDerive,
    handleAiDraftDecision,
    closeAiDeriveDialog,
  } = useRequirementAiDerivation(requirement, t, refresh);

  // SysEng 2.0 N5 (test.derive_from_requirement): AI TestCase-draft copilot

  // Split-view state for localStorage persistence
  
  /**
   * Handle create new requirement.
   */
  const handleCreate = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    // BUG-02 (SYSTEMAUDIT_2026-08-18 §4): title is a required field. This
    // used to silently substitute the placeholder copy for a blank/
    // whitespace-only input and submit that — the save button below is now
    // disabled for the same condition, this guard only protects against a
    // direct form submit (e.g. pressing Enter) bypassing that.
    const title = newTitle.trim();
    if (!title) return;
    setCreating(true);
    setCreateError(null);
    try {
      const created = await createRequirement.mutateAsync({
        workspace_id: activeWorkspace.id,
        title,
        // BUG-11: only send what the user actually typed — an empty string
        // for a field the backend treats as optional should not clobber a
        // server-side default.
        ...(newDescription.trim() ? { description: newDescription.trim() } : {}),
        ...(newCategory ? { category: newCategory } : {}),
      });
      closeCreateForm();
      navigate(`/requirements/${created.id}`);
    } catch (err: unknown) {
      // #340: the server rejects e.g. `<script>alert(1)</script>` as a title
      // with a 400 whose `error.details[0].errors[0]` names the offending
      // field. Swallowing that into console.error left the form open with no
      // visible reason, i.e. an apparent silent no-op. The form deliberately
      // stays open so the typed title is preserved and can be corrected.
      setCreateError(extractApiErrorMessage(err) ?? t('req.createFailed'));
    } finally {
      setCreating(false);
    }
  }, [activeWorkspace, createRequirement, navigate, newTitle, newDescription, newCategory, t, closeCreateForm, setCreating, setCreateError]);

  /** ArtifactForm owns definition validation, nested values and save errors. */
  const handleDefinitionCreate = useCallback(async (values: ArtifactFormValues): Promise<void> => {
    if (!activeWorkspace) throw new Error(t('req.createFailed'));
    const title = typeof values.title === 'string' ? values.title.trim() : '';
    if (!title) throw new Error(t('req.createFailed'));
    const created = await createRequirement.mutateAsync({
      ...values,
      workspace_id: activeWorkspace.id,
      title,
    });
    closeCreateForm();
    navigate(`/requirements/${created.id}`);
  }, [activeWorkspace, createRequirement, navigate, t, closeCreateForm]);

  // F-08: Dialog's focus trap moves focus to the first focusable element in
  // the panel by default — that would be its own × close button, ahead of
  // the title input this form used to `autoFocus`. Pointing initialFocusRef
  // at the title input preserves the previous UX.
  //
  // Issue #800: the native `autoFocus` attribute used to stay on this input
  // *in addition* to `initialFocusRef` — two independent focus-management
  // mechanisms racing on the same element. The native attribute's focusing
  // steps run as a queued task (HTML autofocus processing model), not
  // synchronously during mount, so it could win *after* the focus trap's
  // effect already ran, and — observed in real-browser QA — misdirect
  // initial focus onto the description field instead. `initialFocusRef` is
  // now the single source of truth; `autoFocus` was removed from the input.
  const newTitleInputRef = useRef<HTMLInputElement | null>(null);
  const focusFallbackTitle = useCallback((input: HTMLInputElement | null): void => {
    newTitleInputRef.current = input;
    input?.focus();
  }, []);

  /**
   * Issue #1092: the route's complete AI-action set, in one list. Each entry
   * keeps its own label, hint and test id from before the move; the shared
   * `<AiActionSection>` adds the common AI icon and the button variant, so
   * adding a third AI action here is a data change, never another header
   * button.
   *
   * `canUseAi` is the existing workspace-role gate (R2/T1): a viewer gets an
   * empty list, and an empty list means the section is not rendered at all —
   * the triggers are genuinely absent from the DOM, not merely disabled.
   */
  const canUseAi = hasRole('editor');
  const aiActions = useMemo<AiActionDescriptor[]>(
    () => buildAiActions(canUseAi, t, handleAiDerive, isAiDeriving, openDeriveTestcasePanel),
    [canUseAi, t, handleAiDerive, isAiDeriving, openDeriveTestcasePanel],
  );

  const {
    currentVersion,
    detailScrollRef,
    focusInspectorHeading,
    focusSpine,
  } = useRequirementInspector({ requirement });

  // Task 5 (Schnitt 2b): the derivation chain now lives inside the footer,
  // so this host only decides *whether* it is mounted (and no longer fires
  // chain RPCs on its own).
  const [traceFooterVisible] = useTraceFooterVisible();
  // Task 9 / ADR-030: per-module persisted tree width (min matches minWidths[0]).
  const { treeWidth, defaultTreeWidth, setTreeWidth } = useTreeWidth('requirements', { min: 320 });

  // Loading state
  if (isLoading) {
    return <p role="status">{t('loading')}</p>;
  }

  // Error state
  if (error) {
    return (
      <div role="alert">
        <p className={styles.errorText}>{error}</p>
        <button
          data-testid="requirements-reload-btn"
          onClick={refresh}
          className="btn-secondary"
        >
          {t('actions.reload')}
        </button>
      </div>
    );
  }

  /**
   * Left panel: Requirements list + toolbar
   */
  /**
   * Page header — lives at page level, above the SplitView, exactly like
   * every other artifact route (Adr/Risk/Issue/Needs/TestCase/Architecture).
   *
   * It used to be rendered INSIDE `leftPanel` with `density="compact"`, which
   * is the migration step UI concept ch. 6.1/17 step 3 left open. That made
   * Requirements the one route whose <h1> was 18px instead of 30px and whose
   * header was as narrow as the list panel (~520px) rather than the page
   * (~1160px) — the single most visible header divergence in the app.
   *
   * PDF export, CSV import and the guided-interview start move into
   * `overflowActions`: per this component's own contract they are rare
   * actions, and keeping them as visible buttons would leave Requirements
   * with secondary buttons where every other route has exactly one.
   *
   * #797: the interview CTA used to sit in `secondaryActions` "so it sits in
   * the same place on all seven routes" — but it never did: it was only ever
   * mounted by the seven interview-capable routes, so Requirements showed two
   * visible create buttons (`+ Neue Anforderung` next to it) while Glossary,
   * ICD, Test Runs and Diagrams showed one. It is a second *create path*, not
   * a variant of the primary one, so it belongs in the overflow menu with the
   * other secondary actions (ch. 12.1).
   */
  const pageHeader = (
    <PageHeader
      title={t('nav.requirements')}
      summary={t('requirements.summary', { count: requirements.length })}
      // R2/T1: the route's primary create trigger is a write action — a
      // viewer must not find it in the DOM at all (same gate as Save/Delete/
      // Ableiten below and the list's create/delete triggers).
      primaryAction={
        hasRole('editor')
          ? {
              // Names the result, not the gesture (UI concept ch. 12.1 / 14.2,
              // GH-343): every other artifact route reads "New <Entity>".
              label: t('requirements.newRequirement'),
              prefixWithPlus: true,
              onClick: toggleCreateForm,
              testId: 'create-req-btn',
            }
          : undefined
      }
      overflowActions={[
        interviewCta,
        {
          label: t('requirements.exportPdf', 'PDF-Export'),
          onClick: () => void exportPdf(),
          disabled: isExportingPdf || requirements.length === 0,
          testId: 'export-pdf-btn',
        },
        {
          label: t('requirements.importCsv', 'CSV-Import'),
          onClick: () => navigate('/import'),
          disabled: !activeWorkspace,
          testId: 'csv-import-toolbar-btn',
        },
      ]}
    />
  );

  /**
   * Left panel: Requirements list + toolbar
   */
  const leftPanel = (
    <div>
      {/* #340: failures of the header actions (PDF export) and of the list's
          row actions (delete) have no form to attach to — they surface here,
          right under the header that triggered them. */}
      {actionError && (
        <p role="alert" data-testid="req-action-error" className={styles.actionError}>
          {actionError}
        </p>
      )}

      {/* Create form — F-08: wrapped in the shared Dialog primitive so it
          gets a real focus trap and Escape-to-close (GESAMTTEST_BERICHT
          2026-08-21 §5 finding 8); the form markup itself is unchanged. */}
      {showCreateForm && (
        <Dialog
          title={t('requirements.newRequirement')}
          onClose={closeCreateForm}
          initialFocusRef={newTitleInputRef}
          testId="req-new-dialog"
          size="lg"
        >
        <ArtifactForm
          itemType="Requirement"
          artifactId={null}
          initialValues={{ title: '' }}
          attributeOverrides={REQUIREMENT_ATTRIBUTE_OVERRIDES}
          onSave={handleDefinitionCreate}
          onCancel={closeCreateForm}
          fieldTestIds={{ title: 'req-new-title-input' }}
          saveTestId="req-new-save-btn"
          definitionFallback={
            <RequirementCreateFallbackForm
              title={newTitle}
              description={newDescription}
              category={newCategory}
              createError={createError}
              isCreating={isCreating}
              onTitleChange={setNewTitle}
              onDescriptionChange={setNewDescription}
              onCategoryChange={setNewCategory}
              onSubmit={() => void handleCreate()}
              onCancel={closeCreateForm}
              focusTitle={focusFallbackTitle}
            />
          }
        />
        </Dialog>
      )}

      {/*
        GH-443: DELETE is a soft-delete — the requirement survives with
        status="outdated" and the list endpoint hides it by default. Without
        this opt-in a deleted requirement would be unreachable from the UI and
        the list's status filter could never offer "outdated" at all, since its
        options are derived from the loaded items.
      */}
      <IncludeDeletedToggle
        checked={includeDeleted}
        onChange={setIncludeDeleted}
        testIdPrefix="req-list"
      />

      <RequirementViewToggle mode={viewMode} onChange={handleViewModeChange} />

      {viewMode === 'table' ? (
        <ArtifactTableView itemType="Requirement" />
      ) : (
      /* Requirement list */
      <RequirementList
        requirements={requirements}
        selectedId={selectedId}
        onSelect={selectRequirement}
        onDelete={handleDelete}
        onReorder={handleReorder}
        // #1668: server-side allocation filter (drives the list query).
        allocation={allocation}
        onAllocationChange={setAllocation}
        // V6: server-side level filter (drives the list query, `?level=`).
        level={level}
        onLevelChange={setLevel}
        // P6 Task 6.3: groups as pseudo-folders in the requirement tree. Group
        // administration sits behind `req-list-groups-btn` (G1) — only an
        // editor gets the trigger, and the dialog it opens lives at page level
        // so the list column keeps its full height and width.
        groups={requirementGroups.treeGroups}
        onReorderGroupMember={requirementGroups.reorderMember}
        // G3 (spec §4.5.4/6): dragging a non-member onto a group folder adds
        // the membership through the same hook the group manager uses — no
        // second source, no extra request, and the hook reloads the group list
        // so the folder counter and the row marker update without a route
        // reload. A viewer gets none (spec §4.5.5).
        onAddGroupMember={
          hasRole('editor') ? requirementGroups.addMember : undefined
        }
        onManageGroups={
          hasRole('editor') ? () => setIsGroupManagerOpen(true) : undefined
        }
        // G2 (spec §4.5.3): the per-row "add to group" trigger; page-level
        // dialog below. A viewer gets no trigger at all (§4.5.5).
        onAddToGroup={hasRole('editor') ? setAddToGroupId : undefined}
        onCreateNew={openCreateForm}
      />
      )}
    </div>
  );

  /**
   * Right panel: Requirement detail form
   */
  const rightPanel = requirement ? (
    <div className={styles.rightPane}>
      <div className={styles.detailScroll} ref={detailScrollRef}>
      {/* Spec §5.1 #1: the skip link is the first focusable element of the
          detail area and the only way into the inspector that does not
          require walking the form first (U-14). */}
      {currentVersion && (
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
      {/* DoD 2 (#1762/M1): identity and workflow status have exactly one
          place — the artifact head of the route, never the inspector
          (spec §2.2). Requirements had neither in its head until now. */}
      <div className={styles.artifactHead} data-testid="requirement-artifact-head">
        <ArtifactId
          value={requirement.uid}
          fallback={requirement.id.slice(0, 8)}
          testId="requirement-detail-id"
        />
        <StatusBadge status={requirement.status} testId="requirement-detail-status" />
      </div>

      {/* #399 (D7): drift badge + CR shortcut live in the editor header only.
          Bound to the BACKING Artifact id (`artifact_id`) — the
          baseline-membership endpoint keys on artifacts, not entity pks. */}
      {activeWorkspace && (
        <BaselineDriftBadge
          artifactId={requirement.artifact_id ?? requirement.id}
          workspaceId={activeWorkspace.id}
          artifactTitle={requirement.title}
          summary={requirement.baseline_drift}
        />
      )}
      <RequirementArtifactForm
        key={requirement.id}
        requirement={requirement}
        onSaved={handleSaved}
        onDeleted={() => {
          refresh();
          navigate('/requirements');
        }}
        onDirtyChange={setIsFormDirty}
        customFields={customFieldsDraft}
      />

      {/* Sibling of the definition-driven form, not inside it — see
          RequirementArtifactForm's docstring for why (REQ-L2-AS-037). */}
      <div className={styles.customFieldsSection}>
        <h3 className={styles.customFieldsSectionHeading}>
          {t('customFields.section')}
        </h3>
        <CustomFieldsEditor
          key={requirement.id}
          value={requirement.custom_fields}
          onChange={setCustomFieldsDraft}
        />
      </div>

      {/* TraceLink management (REQ-L2-RF-006) — restored after the SplitView
          refactor dropped this panel. The read-only trace view lives in the
          ArtifactInspector inside RequirementArtifactForm.
          Issue #1092: the AI-derive action moved OUT of this panel's header
          row into the single `<AiActionSection>` below; the panel is
          trace-links only now. */}
      {activeWorkspace && (
        <ReqTraceLinkPanel
          workspaceId={activeWorkspace.id}
          requirementId={requirement.id}
          requirements={requirements}
          onLinksChanged={refresh}
        />
      )}
      {aiDeriveStatus && (
        <div
          role={aiDeriveIsError ? 'alert' : 'status'}
          data-testid="req-ai-derive-status"
          className={
            styles.deriveStatus +
            (aiDeriveIsError ? ' ' + styles.deriveStatusError : '')
          }
        >
          {aiDeriveStatus}
        </div>
      )}

      {/* Issue #1092: ONE AI section per route. Both AI actions used to render
          themselves where they happened to live — the derive action inside
          ReqTraceLinkPanel's header row, the test-case draft in a section of
          its own — so "the AI things on this page" had no single place. Both
          now sit here, each carrying the shared flat AI icon.

          Context awareness: the array is empty for a viewer (R2/T1 — a viewer
          must not find these triggers in the DOM at all, not merely disabled),
          and `<AiActionSection>` renders nothing at all for an empty array. So
          this is the app's existing `useHasRole` capability gate, not a new
          one. */}
      <AiActionSection
        title={t('aiActions.heading')}
        hint={t('aiActions.hint')}
        actions={aiActions}
      />

      {/* REQ-L2-VS-004: semantic similarity search */}
      <SimilarRequirementsPanel
        requirementId={requirement.id}
        onSelect={(id) => navigate(`/requirements/${id}`)}
      />

      {/* RFC #1002 PR D: artifact-scoped memory ("Gedächtnis") for this
          requirement — list + create + forget, driven by the artifact memory
          endpoints. Bound to the BACKING Artifact id (`artifact_id`), not the
          Requirement row's own pk: `/artifacts/<id>/memory/` and
          `MemoryPolicy.resolve_artifact_workspace_id` both resolve an
          `Artifact` row, and the Requirement pk would 403 with
          "cannot read 'artifact'-scoped memory". */}
      {requirement.artifact_id && (
        <ArtifactMemoryPanel artifactId={requirement.artifact_id} />
      )}
      </div>
      {currentVersion && (
        <InspectorShell
          kind="requirement"
          entityId={requirement.id}
          artifactPk={requirement.artifact_id ?? null}
          currentVersion={currentVersion}
          coveredRef={detailScrollRef}
          onShowInSpine={traceFooterVisible ? focusSpine : undefined}
        />
      )}
    </div>
  ) : (
    <p className={styles.selectPlaceholder}>
      {t('editor.selectRequirement')}
    </p>
  );

  return (
    <>
      {pendingSelectId && (
        <ConfirmDialog
          title={t('editor.unsavedChangesTitle')}
          message={t('editor.unsavedChangesMessage')}
          confirmLabel={t('editor.discardChanges')}
          onConfirm={confirmPendingSelect}
          onCancel={() => setPendingSelectId(null)}
          testId="req-unsaved-changes-dialog"
        />
      )}
      {showDeriveTestcasePanel && requirement && activeWorkspace && (
        <Dialog
          title={t('deriveTestcase.title')}
          description={requirement.title}
          onClose={closeDeriveTestcasePanel}
          size="lg"
          testId="derive-testcase-dialog"
        >
          <DeriveTestCasePanel
            workspaceId={activeWorkspace.id}
            requirement={{ id: requirement.id, title: requirement.title }}
            onCreated={closeDeriveTestcasePanel}
          />
        </Dialog>
      )}
      {/* Issue #1368 (W12b): the `decompose-next-level` preview's drafts are
          rendered here, in the app-wide AI review dialog (#1360). Confirm and
          "Review later" persist the selected drafts through the accept seam
          (`proposed`, #1089); Discard writes nothing. */}
      {showAiDeriveDialog && requirement && (
        <AiDerivationDialog
          open
          title={t('actions.deriveAi')}
          sourceLabel={requirement.title}
          drafts={aiDrafts}
          isLoading={isAiDeriving}
          loadError={aiDraftLoadError}
          isSubmitting={isAiSaving}
          submitError={aiDraftSubmitError}
          selectable
          onConfirm={(drafts) => void handleAiDraftDecision(drafts, false)}
          onReviewLater={(drafts) => void handleAiDraftDecision(drafts, true)}
          onDiscard={closeAiDeriveDialog}
          testIdPrefix="req-derive-drafts"
        />
      )}
      {/* G1 (spec §4.2/§4.5.1): group administration as a dialog, rendered on
          purpose at PAGE level — inside `leftPanel` the SplitView column's
          `overflow` would clip it. `GroupManager` itself is unchanged: same
          API, same testids, same per-group search. The shared <Dialog> brings
          the focus trap, Escape and the focus return to the toolbar trigger. */}
      {isGroupManagerOpen && hasRole('editor') && (
        <Dialog
          title={t('groups.title')}
          description={t('groups.dialogHint')}
          size="lg"
          testId="group-manager-dialog"
          onClose={() => setIsGroupManagerOpen(false)}
        >
          <GroupManager
            groups={requirementGroups.managerGroups}
            requirements={requirements}
            isLoading={requirementGroups.isLoading}
            error={requirementGroups.error}
            onCreate={requirementGroups.createGroup}
            onAddMember={requirementGroups.addMember}
            onRemoveMember={requirementGroups.removeMember}
          />
        </Dialog>
      )}
      {/* G2 (spec §4.5.3): "Zu Gruppe hinzufügen…" — page level for the same
          reason as the group manager dialog above (the SplitView column clips
          overflow). The hook owns the write + reload, so the folder counters
          and the "in N Gruppen" marker update without a route reload; the
          dialog itself stays open on a rejected add (role="alert"). */}
      {addToGroupRequirement && hasRole('editor') && (
        <AddToGroupDialog
          requirementId={addToGroupRequirement.id}
          requirementTitle={
            addToGroupRequirement.title || t('editor.untitled')
          }
          groups={requirementGroups.managerGroups}
          isLoading={requirementGroups.isLoading}
          groupsError={requirementGroups.error}
          onAdd={requirementGroups.addMember}
          onCreateGroup={requirementGroups.createGroup}
          onClose={() => setAddToGroupId(null)}
        />
      )}
      {/* Same page shell as RiskEditors/AdrEditors/IssueEditors: header at
          page level, SplitView filling the rest. */}
      <div
        data-testid="requirements-page"
        className={styles.page}
      >
        {pageHeader}

        <div className={styles.splitWrapper}>
          {/* Concept contract (§8 M1-11): the spine gets its own slot between
              list and detail, so it stops scrolling with the form (I-13). */}
          <SplitView
            moduleType="requirements"
            treeWidth={treeWidth}
            onTreeWidthChange={setTreeWidth}
            defaultTreeWidth={defaultTreeWidth}
            list={leftPanel}
            detail={rightPanel}
            ratio={[40, 60]}
            minWidths={[320, 448]}
            containerClassName={styles.splitWrapper}
          />
          {traceFooterVisible && requirement && (
            <TraceSpineFooter
              artifact={{
                artifactId: requirement.artifact_id,
                id: requirement.id,
                artifactType: 'Requirement',
                level: null,
              }}
              onOpenArtifact={(_artifact, entry) => {
                if (entry) navigate(getArtifactRoute(entry.entityType, entry.entityId));
              }}
            />
          )}
        </div>
      </div>
    </>
  );
}
