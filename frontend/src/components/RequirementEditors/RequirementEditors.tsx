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
 * - RequirementForm (right panel) — type-dependent form with Moscow/Fibonacci/Verification fields
 * - EntityTypeProvider for context-aware field rendering
 */

import { useState, useCallback, useEffect, useMemo } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useRequirementData } from './useRequirementData';
import { useCreateRequirement, useDeleteRequirement } from '../../queries/requirements';
import { workspacesApi } from '../../api/workspaces';
import { requirementsApi } from '../../api/requirements';
import { extractApiErrorMessage } from '../../api/client';
import { useWorkspace } from '../../context/WorkspaceContext';
import { EntityTypeProvider } from '../../context/EntityTypeContext';
import { attributeVisibilityApi } from '../../api';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { RequirementList } from './RequirementList';
import { RequirementForm } from './RequirementForm';
import { ReqTraceLinkPanel } from './ReqTraceLinkPanel';
import { SimilarRequirementsPanel } from './SimilarRequirementsPanel';
import { DeriveTestCasePanel } from '../TestCaseEditors/DeriveTestCasePanel';
import { Dialog } from '../shared/Dialog';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { TraceSpine, useDerivationChain } from '../shared/TraceSpine';
import type { ChainArtifact } from '../shared/TraceSpine';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import type { RequirementType } from '../../types';
import styles from './RequirementEditors.module.css';

/**
 * RequirementEditors — main view with SplitView (list | detail)
 */
export default function RequirementEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  // GH-443: opt-in to soft-deleted requirements (status="outdated").
  const [includeDeleted, setIncludeDeleted] = useState(false);
  const {
    requirements,
    requirement,
    upstreamLinks,
    downstreamLinks,
    linkedTitles,
    linkedRoutes,
    isLoading,
    error,
    refresh,
  } = useRequirementData(selectedId, { includeDeleted });

  const createRequirement = useCreateRequirement();
  const deleteRequirement = useDeleteRequirement();

  // Create form state
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  // #340: a rejected create (e.g. the free-text guard refusing markup in the
  // title) must be visible in the create form itself — this used to be a bare
  // console.error, which reads as "Save did nothing" to the user.
  const [createError, setCreateError] = useState<string | null>(null);
  // #340: same for the list-level actions that have no form of their own
  // (delete, PDF export) — rendered as a banner under the page header.
  const [actionError, setActionError] = useState<string | null>(null);

  // PDF export state
  const [isExportingPdf, setIsExportingPdf] = useState(false);

  // REQ-008: AI-derive state for Anforderungen view
  const [isAiDeriving, setIsAiDeriving] = useState(false);
  const [aiDeriveStatus, setAiDeriveStatus] = useState<string | null>(null);
  const [aiDeriveIsError, setAiDeriveIsError] = useState(false);

  // SysEng 2.0 N5 (test.derive_from_requirement): AI TestCase-draft copilot
  const [showDeriveTestcasePanel, setShowDeriveTestcasePanel] = useState(false);

  // Dynamic attribute configurations
  const [attributeVisibility, setAttributeVisibility] = useState<Record<string, boolean>>({
    complexity_fibonacci: true,
    verification_method: true,
  });
  const [requiredFields, setRequiredFields] = useState<Record<string, boolean>>({});

  useEffect(() => {
    let isMounted = true;
    attributeVisibilityApi.list()
      .then((data) => {
        if (!isMounted) return;
        const vMap: Record<string, boolean> = {};
        const rMap: Record<string, boolean> = {};
        data.filter(cfg => cfg.entity_type === 'requirement').forEach(cfg => {
          vMap[cfg.attribute_name] = cfg.is_visible;
          rMap[cfg.attribute_name] = cfg.is_required || false;
        });
        
        if (!('complexity_fibonacci' in vMap)) vMap['complexity_fibonacci'] = true;
        if (!('verification_method' in vMap)) vMap['verification_method'] = true;
        
        setAttributeVisibility(vMap);
        setRequiredFields(rMap);
      })
      // An empty config set is a valid, expected state (no seed data by
      // design); only genuine HTTP/network failures reach here — log them as a
      // warning, not an error (REQ-136).
      .catch(err => console.warn('Could not load attribute configs; using defaults', err));
    return () => { isMounted = false; };
  }, []);

  // Split-view state for localStorage persistence
  
  /**
   * Handle create new requirement.
   */
  const handleCreate = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    const title = newTitle.trim() || t('editor.newRequirementTitle');
    setIsCreating(true);
    setCreateError(null);
    try {
      const created = await createRequirement.mutateAsync({
        workspace_id: activeWorkspace.id,
        title,
      });
      setShowCreateForm(false);
      setNewTitle('');
      navigate(`/requirements/${created.id}`);
    } catch (err: unknown) {
      // #340: the server rejects e.g. `<script>alert(1)</script>` as a title
      // with a 400 whose `error.details[0].errors[0]` names the offending
      // field. Swallowing that into console.error left the form open with no
      // visible reason, i.e. an apparent silent no-op. The form deliberately
      // stays open so the typed title is preserved and can be corrected.
      setCreateError(extractApiErrorMessage(err) ?? t('req.createFailed'));
    } finally {
      setIsCreating(false);
    }
  }, [activeWorkspace, createRequirement, navigate, newTitle, t]);

  /** Open/close the inline create form, discarding any stale error. */
  const toggleCreateForm = useCallback((): void => {
    setCreateError(null);
    setShowCreateForm((open) => !open);
  }, []);

  /**
   * Handle delete requirement with confirmation.
   */
  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      if (!activeWorkspace) return;
      setActionError(null);
      try {
        await deleteRequirement.mutateAsync({ id, workspaceId: activeWorkspace.id });
        navigate('/requirements');
      } catch (err: unknown) {
        // #340: a refused delete (permission, workflow gate) must not look
        // like the row simply stayed where it was.
        setActionError(extractApiErrorMessage(err) ?? t('req.deleteFailed'));
      }
    },
    [activeWorkspace, deleteRequirement, navigate, t]
  );

  /**
   * Handle PDF export of requirements.
   */
  const handleExportPdf = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsExportingPdf(true);
    setActionError(null);
    try {
      const blob = await workspacesApi.downloadPdfReport(activeWorkspace.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `requirement_document_${activeWorkspace.id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err: unknown) {
      // #340: a failed export produced no download and no message at all.
      setActionError(extractApiErrorMessage(err) ?? t('req.pdfExportFailed'));
    } finally {
      setIsExportingPdf(false);
    }
  }, [activeWorkspace, t]);

  /**
   * REQ-008: AI-assisted decomposition of the selected requirement to
   * next-level drafts via POST /requirements/{id}/decompose-next-level/.
   */
  const handleAiDerive = useCallback(async (): Promise<void> => {
    if (!requirement) return;
    setIsAiDeriving(true);
    setAiDeriveIsError(false);
    setAiDeriveStatus(t('needs.deriveStarting'));
    try {
      const result = await requirementsApi.aiDecomposeNextLevel(requirement.id);
      const count = result.drafts?.length ?? 0;
      // Issue #311: both branches used to render the same success message, so
      // a run that produced zero drafts reported "derived successfully" and
      // left no trace of the fact that nothing had happened.
      if (count > 0) {
        setAiDeriveStatus(t('needs.deriveSuccess'));
        refresh();
        return;
      }
      setAiDeriveIsError(true);
      setAiDeriveStatus(t('req.aiDeriveEmpty'));
    } catch (err: unknown) {
      const apiErr = err as { error?: { message?: string } };
      setAiDeriveIsError(true);
      setAiDeriveStatus(apiErr?.error?.message ?? t('needs.deriveFailed'));
    } finally {
      setIsAiDeriving(false);
    }
  }, [requirement, t, refresh]);

  const currentVersion: VersionRef | undefined = useMemo(() => {
    if (!requirement) return undefined;
    return {
      version: requirement.version,
      label: `v${requirement.version}`,
      createdAt: requirement.updated_at ?? requirement.created_at,
      baselineIds: [],
    };
  }, [requirement]);

  // Trace spine (Task 3.3 — UI concept ch. 5). Uses the resolve-endpoint
  // backed isOpenable/resolveEntry from the hook itself; unlike Architecture
  // (Task 3.2's pilot, which predates the resolve endpoint) this page has no
  // cheaper local id mapping to fall back on.
  const derivationChain = useDerivationChain(
    requirement?.artifact_id ?? requirement?.id ?? null,
    'Requirement',
    null,
    { enabled: !!requirement },
  );

  const handleOpenChainArtifact = useCallback(
    (artifact: ChainArtifact): void => {
      const entry = derivationChain.resolveEntry(artifact);
      if (entry) navigate(getArtifactRoute(entry.entityType, entry.entityId));
    },
    [derivationChain, navigate],
  );

  // Loading state
  if (isLoading) {
    return <p role="status">{t('loading')}</p>;
  }

  // Error state
  if (error) {
    return (
      <div role="alert">
        <p style={{ color: 'var(--color-danger)' }}>{error}</p>
        <button onClick={refresh}>{t('actions.reload')}</button>
      </div>
    );
  }

  /**
   * Left panel: Requirements list + toolbar
   */
  const leftPanel = (
    <div>
      {/* Page header — title, live count and primary/secondary actions
          (issue #172: was a bare <h3> with the primary action buried under
          the filters below; now matches the Architecture/Glossary pattern). */}
      <PageHeader
        title={t('nav.requirements')}
        // This header sits INSIDE the narrow split-view panel, not at page
        // level, so it keeps the smaller heading until the Requirements
        // route is migrated in its own step (UI concept ch. 6.1/17 step 3).
        density="compact"
        count={{ shown: requirements.length, total: requirements.length }}
        primaryAction={{
          label: `+ ${t('actions.new')}`,
          onClick: toggleCreateForm,
          testId: 'create-req-btn',
        }}
        secondaryActions={[
          {
            label: 'PDF',
            onClick: () => void handleExportPdf(),
            disabled: isExportingPdf || requirements.length === 0,
            testId: 'export-pdf-btn',
          },
          {
            label: t('import.upload', 'CSV'),
            onClick: () => navigate('/import'),
            disabled: !activeWorkspace,
            testId: 'csv-import-toolbar-btn',
          },
        ]}
      />

      {/* #340: failures of the header actions (PDF export) and of the list's
          row actions (delete) have no form to attach to — they surface here,
          right under the header that triggered them. */}
      {actionError && (
        <p role="alert" data-testid="req-action-error" className={styles.actionError}>
          {actionError}
        </p>
      )}

      {/* Create form */}
      {showCreateForm && (
        <form
          data-testid="create-req-form"
          onSubmit={(e) => {
            e.preventDefault();
            void handleCreate();
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
            htmlFor="new-req-title"
            style={{
              fontSize: 'var(--font-size-sm)',
              fontWeight: 600,
              color: 'var(--color-text)',
            }}
          >
            {t('editor.title')}
          </label>
          <input
            id="new-req-title"
            data-testid="req-new-title-input"
            type="text"
            value={newTitle}
            onChange={(e) => {
              setNewTitle(e.target.value);
              // The message described the *previous* attempt; keep it until
              // the user actually starts correcting the input.
              if (createError) setCreateError(null);
            }}
            autoFocus
            disabled={isCreating}
            placeholder={t('editor.newRequirementTitle')}
            style={{
              padding: 'var(--space-2) var(--space-3)',
              borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)',
              fontSize: 'var(--font-size-sm)',
              background: 'var(--color-surface)',
              color: 'var(--color-text)',
              fontFamily: 'var(--font-sans)',
              boxSizing: 'border-box',
            }}
          />
          {/* #340: the server's own reason (e.g. "contains disallowed
              content: HTML markup is not permitted in free-text fields")
              belongs directly under the field that produced it — see
              docs/architecture/UI_STYLE_GUIDE.md §5.2. */}
          {createError && (
            <p role="alert" data-testid="req-create-error" className={styles.formError}>
              {createError}
            </p>
          )}
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button
              data-testid="req-new-cancel-btn"
              type="button"
              onClick={() => {
                setShowCreateForm(false);
                setCreateError(null);
                setNewTitle('');
              }}
              disabled={isCreating}
              style={{
                background: 'var(--color-surface)',
                color: 'var(--color-text)',
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-2) var(--space-3)',
                fontSize: 'var(--font-size-sm)',
                cursor: isCreating ? 'not-allowed' : 'pointer',
                fontWeight: 600,
              }}
            >
              {t('actions.cancel')}
            </button>
            <button
              data-testid="req-new-save-btn"
              type="submit"
              disabled={isCreating}
              style={{
                background: 'var(--color-primary)',
                color: 'white',
                border: 'none',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-2) var(--space-3)',
                fontSize: 'var(--font-size-sm)',
                cursor: isCreating ? 'not-allowed' : 'pointer',
                opacity: isCreating ? 0.6 : 1,
                fontWeight: 600,
              }}
            >
              {isCreating ? t('actions.saving') : t('actions.save')}
            </button>
          </div>
        </form>
      )}

      {/*
        GH-443: DELETE is a soft-delete — the requirement survives with
        status="outdated" and the list endpoint hides it by default. Without
        this opt-in a deleted requirement would be unreachable from the UI and
        the list's status filter could never offer "outdated" at all, since its
        options are derived from the loaded items.
      */}
      <label
        data-testid="req-list-include-deleted-label"
        className={styles.includeDeletedToggle}
      >
        <input
          type="checkbox"
          data-testid="req-list-include-deleted"
          checked={includeDeleted}
          onChange={(e) => setIncludeDeleted(e.target.checked)}
        />
        {t('editor.showDeleted', 'Show deleted')}
      </label>

      {/* Requirement list */}
      <RequirementList
        requirements={requirements}
        selectedId={selectedId}
        onSelect={(id) => navigate(`/requirements/${id}`)}
        onDelete={handleDelete}
        onCreateNew={() => {
          setCreateError(null);
          setShowCreateForm(true);
        }}
      />
    </div>
  );

  /**
   * Right panel: Requirement detail form
   */
  const rightPanel = requirement ? (
    <div style={{ display: 'flex', height: '100%', minHeight: 0, gap: 'var(--space-3)' }}>
      <div style={{ flex: '1 1 auto', minWidth: 0, overflow: 'auto' }}>
      <TraceSpine
        stations={derivationChain.stations}
        isLoading={derivationChain.isLoading}
        error={derivationChain.error}
        onOpenArtifact={handleOpenChainArtifact}
        isOpenable={derivationChain.isOpenable}
      />
      <EntityTypeProvider
        entityType="requirement"
        entitySubType={(requirement.type || 'SyReq') as RequirementType}
        visibleFields={attributeVisibility}
        requiredFields={requiredFields}
      >
        <RequirementForm
          requirement={requirement}
          upstreamLinks={upstreamLinks}
          downstreamLinks={downstreamLinks}
          linkedTitles={linkedTitles}
          linkedRoutes={linkedRoutes}
          requirements={requirements}
          workspaceId={activeWorkspace!.id}
          onSaved={refresh}
          onCancel={() => navigate('/requirements')}
        />
      </EntityTypeProvider>

      {/* TraceLink management incl. "Ableiten" (REQ-L2-RF-006) — restored
          after the SplitView refactor dropped this panel. The read-only
          trace view lives in the ArtifactInspector inside RequirementForm. */}
      {activeWorkspace && (
        <ReqTraceLinkPanel
          workspaceId={activeWorkspace.id}
          requirementId={requirement.id}
          requirements={requirements}
          onLinksChanged={refresh}
          onAiDerive={handleAiDerive}
          isAiDeriving={isAiDeriving}
        />
      )}
      {aiDeriveStatus && (
        <div
          role={aiDeriveIsError ? 'alert' : 'status'}
          data-testid="req-ai-derive-status"
          style={{
            marginTop: 'var(--space-2)',
            fontSize: 'var(--font-size-sm)',
            color: aiDeriveIsError ? 'var(--color-danger)' : 'var(--color-text)',
          }}
        >
          {aiDeriveStatus}
        </div>
      )}

      {/* SysEng 2.0 N5: AI-generate a TestCase draft for this requirement */}
      <div style={{ marginTop: 'var(--space-2)' }}>
        <button
          type="button"
          onClick={() => setShowDeriveTestcasePanel(true)}
          data-testid="req-derive-testcase-btn"
        >
          {t('deriveTestcase.trigger')}
        </button>
      </div>

      {/* REQ-L2-VS-004: semantic similarity search */}
      <SimilarRequirementsPanel
        requirementId={requirement.id}
        onSelect={(id) => navigate(`/requirements/${id}`)}
      />
      </div>
      {currentVersion && (
        <RightSidebar
          kind="requirement"
          artifactId={requirement.id}
          currentVersion={currentVersion}
          hideTraceLinks
        />
      )}
    </div>
  ) : (
    <p
      style={{
        color: 'var(--color-text-muted)',
        fontSize: 'var(--font-size-lg)',
        textAlign: 'center',
        padding: 'var(--space-8)',
      }}
    >
      {t('editor.selectRequirement')}
    </p>
  );

  return (
    <>
      {showDeriveTestcasePanel && requirement && activeWorkspace && (
        <Dialog
          title={t('deriveTestcase.title')}
          description={requirement.title}
          onClose={() => setShowDeriveTestcasePanel(false)}
          size="lg"
          testId="derive-testcase-dialog"
        >
          <DeriveTestCasePanel
            workspaceId={activeWorkspace.id}
            requirement={{ id: requirement.id, title: requirement.title }}
            onCreated={() => setShowDeriveTestcasePanel(false)}
          />
        </Dialog>
      )}
      <SplitView
        leftPanel={leftPanel}
        rightPanel={rightPanel}
        leftMinWidth={260}
        leftMaxWidthPercent={70}
        moduleType="requirements"
      />
    </>
  );
}
