import { useCallback, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { useInterviewStartCta } from '../shared/useInterviewStartCta';
import { IncludeDeletedToggle } from '../shared/IncludeDeletedToggle/IncludeDeletedToggle';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { EditorPageShell } from '../shared/EditorPageShell';
import { FormField } from '../shared/FormField';
import { fieldErrorsFromException } from '../shared/ArtifactForm/field-errors';
import { useFieldContract } from '../../hooks/useFieldContract';
import { extractApiErrorMessage } from '../../api/client';
import { TestCaseList } from './TestCaseList';
import { TestCaseArtifactForm } from './TestCaseArtifactForm';
import { CustomFieldsEditor } from '../shared/CustomFieldsEditor';
import { BaselineDriftBadge } from '../shared/BaselineDriftBadge/BaselineDriftBadge';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { TraceSpine, useDerivationChain } from '../shared/TraceSpine';
import type { ChainArtifact } from '../shared/TraceSpine';
import { TraceLinkPanel } from '../shared/TraceLinkPanel';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import { useTestCaseData } from './useTestCaseData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { useEntityReset } from '../../hooks/use-entity-reset';
import { useFormDirty } from '../../hooks/use-form-dirty';
import { testcasesApi, type TestCaseType } from '../../api/testcases';
// F-04 (code review, 2026-08-19): shared create-form field styles (see
// frontend/src/components/shared/FieldHints.module.css header comment) —
// keeping them in one shared place instead of duplicating them per component.
import fieldHints from '../shared/FieldHints.module.css';
import styles from './TestCaseEditors.module.css';

/**
 * #864: the real `TestCase.test_type` values (mirror of backend
 * `TestCaseType`). The create form offers them explicitly; the empty string
 * stands for "not specified" (backend column left NULL).
 */
const TEST_TYPE_OPTIONS: readonly TestCaseType[] = [
  'system',
  'integration',
  'unit',
  'inspection',
  'analysis',
  'demonstration',
];

/**
 * #953: the documented create default (REST/MCP schema: "Test type (default
 * 'Unit')", canonical column value `unit`). The dialog preselects it so an
 * untouched form no longer stores `test_type = null` — which used to make the
 * traceability coverage surface look like the requirement had no test at all.
 * The user can still pick "Not specified" explicitly.
 */
const DEFAULT_TEST_TYPE: TestCaseType = 'unit';

export default function TestCaseEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  // Shared with the other artifact routes so the CTA cannot drift.
  const interviewCta = useInterviewStartCta('TestCase');
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const { items, item, isLoading, error, refresh } = useTestCaseData(selectedId, includeDeleted);
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  // BUG-11 (Systemaudit 2026-08-18, §4): `description` is an ordinary
  // testcasesApi.create() field the backend already accepts — it had no
  // editor in this create dialog.
  const [newDescription, setNewDescription] = useState('');
  // #864: real `TestCase.test_type` column. #953: preselected to the
  // documented default; empty string = "Not specified" (column left NULL).
  const [newTestType, setNewTestType] = useState<TestCaseType | ''>(DEFAULT_TEST_TYPE);
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
  const { field } = useFieldContract('TestCase', { enabled: showCreateDialog });

  // Systemaudit 2026-08-27 UI-07: does the currently-open TestCaseForm have
  // unsaved local edits? Reported by the form itself via onDirtyChange.
  // `pendingSelectId` holds a list-row click that arrived while dirty, so it
  // can be confirmed or discarded instead of silently overwriting the open
  // edit — mirrors RequirementEditors' issue #672 handling.
  const [formDirty, setFormDirty] = useState(false);
  const [pendingSelectId, setPendingSelectId] = useState<string | null>(null);

  // Task 22: custom_fields is a free-form JSON blob the definition-driven
  // TestCaseArtifactForm cannot render (no `kind: "extended"` attribute
  // exists for TestCase), so the CustomFieldsEditor lives here as a sibling
  // — same scope boundary as NeedsEditors' customFieldsDraft (Task 23).
  // Reset on test-case switch, not on every refetch of the same one.
  const [customFieldsDraft, setCustomFieldsDraft] = useState<Record<string, unknown>>({});
  // customFieldsDraft must feed the same dirty gate isFormDirty does, or
  // editing only a custom field and switching to another test case silently
  // discards the edit with no unsaved-changes dialog — the CustomFieldsEditor
  // is a sibling of TestCaseArtifactForm, not wired into its own
  // useFormDirty/onDirtyChange at all.
  const { isDirty: customFieldsDirty, markClean: markCustomFieldsClean } = useFormDirty(
    customFieldsDraft,
    item?.custom_fields ?? {},
  );
  useEntityReset(item?.id ?? '__none__', () => {
    const baseline = item?.custom_fields ?? {};
    setCustomFieldsDraft(baseline);
    markCustomFieldsClean(baseline);
  });
  const isFormDirty = formDirty || customFieldsDirty;

  // 12.1/14.2: named after the result ("New Test Case"), not the gesture
  // ("+ New"); also the dialog title, matching ch. 12.8 ("dialog title
  // repeats the label of the button that opened it").
  const newTestCaseLabel = t('testcases.newTestCase', 'New Test Case');

  const openCreateDialog = useCallback((): void => {
    setCreateError(null);
    setCreateFieldErrors({});
    setNewTitle('');
    setNewDescription('');
    // #953: every newly opened dialog starts on the documented default again.
    setNewTestType(DEFAULT_TEST_TYPE);
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
      const resp = await testcasesApi.create({
        workspace_id: activeWorkspace.id,
        title: newTitle.trim(),
        // BUG-11: only send what was actually typed.
        ...(newDescription.trim() ? { description: newDescription.trim() } : {}),
        // #864: only send the real test_type column when a type was chosen.
        ...(newTestType ? { test_type: newTestType } : {}),
      });
      setNewTitle('');
      setNewDescription('');
      setNewTestType('');
      setShowCreateDialog(false);
      refresh();
      navigate(`/testcases/${resp.id}`);
    } catch (e) {
      console.error(e);
      const msg = extractApiErrorMessage(e) ?? t('testcases.createFailed');
      // The banner keeps the overall reason (a failure with no field
      // detail must stay visible); the per-field half renders under the
      // control that was named.
      setCreateError(msg);
      setCreateFieldErrors(fieldErrorsFromException(e, msg));
    } finally {
      setIsCreating(false);
    }
  };

  // F-2 (Task 23 fix round 4, reintroduced here — see NeedsEditors'
  // handleSaved for the original fix): a save that touched
  // customFieldsDraft left customFieldsDirty stuck `true` forever without
  // this — markCustomFieldsClean was only ever called from
  // useEntityReset/confirmPendingSelect, never after a successful save, so
  // the very next test-case switch showed a false unsaved-changes dialog.
  const handleSaved = () => {
    markCustomFieldsClean(customFieldsDraft);
    refresh();
  };
  const handleDeleted = () => { navigate('/testcases'); refresh(); };

  /**
   * Systemaudit 2026-08-27 UI-07: mirrors RequirementEditors'
   * `selectRequirement` (issue #672) — a list-row click used to call
   * `navigate()` directly, which swaps the URL (and therefore the
   * `testCase` prop the open TestCaseForm is bound to) immediately,
   * discarding any unsaved edit with no warning. Unsaved edits now gate the
   * navigation behind a confirmation instead.
   */
  const selectTestCase = useCallback(
    (id: string): void => {
      if (isFormDirty && id !== selectedId) {
        setPendingSelectId(id);
        return;
      }
      navigate(`/testcases/${id}`);
    },
    [isFormDirty, navigate, selectedId]
  );

  const confirmPendingSelect = useCallback((): void => {
    if (!pendingSelectId) return;
    const target = pendingSelectId;
    setPendingSelectId(null);
    setFormDirty(false);
    // Discarding: re-anchor the custom-fields baseline to whatever is
    // currently drafted so isFormDirty drops immediately, not just once the
    // target test case's own useEntityReset callback fires after navigation.
    markCustomFieldsClean(customFieldsDraft);
    navigate(`/testcases/${target}`);
  }, [pendingSelectId, navigate, customFieldsDraft, markCustomFieldsClean]);

  // Trace spine (Task 3.3 — UI concept ch. 5). Test cases are not their own
  // station type in the derivation-chain model (useDerivationChain docs) —
  // they attach to the station of whatever they verify — but the currently
  // opened test case still gets its own "current" station showing what it
  // verifies/derives from.
  const derivationChain = useDerivationChain(
    // #399: `TestCase.artifact_id` is now exposed by the read path (the drift
    // badge below binds to it). This spine call keeps the TestCase entity pk —
    // its existing behaviour, out of scope for the artifact-id fix.
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
        <button className="btn-secondary" onClick={refresh} data-testid="testcase-reload-btn">
          {t('actions.retry')}
        </button>
      </div>
    );
  }

  return (
    <div data-testid="testcases-page" className={styles.page}>
      {pendingSelectId && (
        <ConfirmDialog
          title={t('editor.unsavedChangesTitle')}
          message={t('editor.unsavedChangesMessage')}
          confirmLabel={t('editor.discardChanges')}
          onConfirm={confirmPendingSelect}
          onCancel={() => setPendingSelectId(null)}
          testId="tc-unsaved-changes-dialog"
        />
      )}
      {/* 12.1: exactly one <h1>, always-visible summary, one primary action —
          replaces the bare "+ New" button that used to live inside
          TestCaseList (issue: the create action sat in the list toolbar, in
          violation of 12.2). */}
      <PageHeader
        title={t('nav.testCases')}
        summary={t('testcases.summary', { count: items.length })}
        primaryAction={{
          label: newTestCaseLabel,
          prefixWithPlus: true,
          onClick: openCreateDialog,
          testId: 'create-tc-btn',
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
            <div>
              <IncludeDeletedToggle
                checked={includeDeleted}
                onChange={setIncludeDeleted}
                testIdPrefix="tc-list"
              />
              <TestCaseList
                items={items}
                selectedId={selectedId}
                onSelect={selectTestCase}
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
                {/* #399 (D7): drift badge + CR shortcut live in the editor
                    header only — never in the list rows (N+1). Bound to the
                    BACKING Artifact id (`artifact_id`): the membership
                    endpoint and `affected_item_ids` key on artifacts, not on
                    the TestCase entity pk. */}
                {item && activeWorkspace && (
                  <BaselineDriftBadge
                    artifactId={item.artifact_id ?? item.id}
                    workspaceId={activeWorkspace.id}
                    artifactTitle={item.title}
                    summary={item.baseline_drift}
                  />
                )}
                {/* Plan C T-C3-1 (PR-C10, ENT-C1 = B): the test case detail area
                    gets the same trace-link CRUD list as Risk/ADR/Issue/Need —
                    the read-only <TraceSpine> above cannot delete a link, and
                    the inspector stays on `hideTraceLinks` below (one CRUD
                    surface per screen). Bound to the BACKING Artifact id
                    (`artifact_id ?? id`): trace links live in the Artifact id
                    space, exactly like the drift badge right above. Placed
                    before the form as the task prescribes (Risk/ADR/Issue/Need
                    render theirs after it), but after the drift badge so that
                    artifact-level warning keeps its place under the spine. */}
                {item && activeWorkspace && (
                  <TraceLinkPanel workspaceId={activeWorkspace.id} artifactId={item.artifact_id ?? item.id} />
                )}
                {/* DEVIATION from the plan brief (same class as Risk/Issue/
                    StakeholderNeed, Tasks 19/20/23): `TestCaseArtifactForm`
                    takes a non-nullable `testCase: TestCase` (unlike the
                    deleted `TestCaseForm`, which accepted `testCase:
                    TestCase | null` and rendered the "select a test case"
                    placeholder itself). `item` here is `TestCase | null` (no
                    row selected yet), so that null-guard moves to this call
                    site instead of being lost. */}
                {item ? (
                  <>
                    <TestCaseArtifactForm
                      testCase={item}
                      onSaved={handleSaved}
                      onDeleted={handleDeleted}
                      onDirtyChange={setFormDirty}
                      customFields={customFieldsDraft}
                      onReviewed={refresh}
                    />
                    {/* Sibling of the definition-driven form, not inside it
                        — see TestCaseArtifactForm's docstring for why. */}
                    <div className={styles.customFieldsSection}>
                      <h3 className={styles.customFieldsSectionHeading}>
                        {t('customFields.section')}
                      </h3>
                      <CustomFieldsEditor
                        key={item.id}
                        value={item.custom_fields}
                        onChange={setCustomFieldsDraft}
                      />
                    </div>
                  </>
                ) : (
                  <p className={styles.selectPlaceholder}>
                    {t('testcases.selectTestCase')}
                  </p>
                )}
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

      <EditorPageShell
        open={showCreateDialog}
        title={newTestCaseLabel}
        testId="tc-create-dialog"
        formId="tc-create-form"
        // The dialog's own focusable-order default would land on the close
        // (×) button, not the title field — same as CreateWorkspaceModal,
        // point the trap at the field the user actually wants to type into.
        initialFocusRef={titleInputRef}
        onClose={closeCreateDialog}
        onSubmit={handleCreateNew}
        isSaving={isCreating}
        canSave={newTitle.trim().length > 0}
        cancelTestId="tc-create-cancel-btn"
        saveTestId="tc-new-save-btn"
        error={createError}
        errorClassName={styles.createError}
      >
        {/* #1393: required marker from the server contract; #1392: `maxLength`
            from the same definition (`TestCase.title` is 500 characters). */}
        <FormField
          htmlFor="tc-new-title"
          label={t('editor.title', 'Title')}
          required={field('title').required}
          error={createFieldErrors.title?.join(', ')}
          labelClassName={styles.createLabel}
        >
          <input
            ref={titleInputRef}
            id="tc-new-title"
            data-testid="tc-new-title-input"
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder={t('testcases.titlePlaceholder')}
            className={styles.createInput}
            {...field('title').controlProps}
          />
        </FormField>

        {/* BUG-11: description — an ordinary testcasesApi.create() field
            the backend already accepts, previously missing here. */}
        <FormField
          htmlFor="tc-new-description"
          label={t('editor.description', 'Description')}
          required={field('description').required}
          error={createFieldErrors.description?.join(', ')}
          labelClassName={fieldHints.createLabel}
        >
          <textarea
            id="tc-new-description"
            data-testid="tc-new-description-input"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            rows={3}
            className={fieldHints.createInput}
            {...field('description').controlProps}
          />
        </FormField>

        {/* #864: real `TestCase.test_type` column — the create contract
            accepts it. #953: preselected to the documented default
            (`unit`); "Not specified" remains an explicit user choice that
            leaves the column NULL. */}
        <FormField
          htmlFor="tc-new-test-type"
          label={t('testcases.testType.label', 'Test Type')}
          required={field('test_type').required}
          error={createFieldErrors.test_type?.join(', ')}
          labelClassName={fieldHints.createLabel}
        >
        <select
          id="tc-new-test-type"
          data-testid="tc-new-test-type-select"
          value={newTestType}
          onChange={(e) => setNewTestType(e.target.value as TestCaseType | '')}
          className={fieldHints.createInput}
          {...field('test_type').selectProps}
        >
          <option value="">{t('testcases.testType.none', 'Not specified')}</option>
          {TEST_TYPE_OPTIONS.map((type) => (
            <option key={type} value={type}>
              {t(`testcases.testType.${type}`, type)}
            </option>
          ))}
        </select>
        </FormField>
      </EditorPageShell>
    </div>
  );
}
