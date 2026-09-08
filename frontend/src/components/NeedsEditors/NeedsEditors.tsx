/**
 * NeedsEditors — split-view editor for stakeholder needs.
 *
 * leaf_id: COMP-RF-003 (split-view editors)
 * req_id:  REQ-L1-095 (ArtifactInspector adoption — 10 artifact types),
 *          REQ-L2-RF-034 (ArtifactInspector RightSidebar shell)
 *
 * Layout: SplitView (left = NeedList, right = NeedArtifactForm). When a
 * detail is selected, the right pane becomes a flex container that hosts
 * both the editor and the ArtifactInspector (Version / Diff / Trace). The
 * inspector is hidden when the user is browsing the list (no detail).
 *
 * Task 23 (rollout wave 2c): migrated the editor itself onto the
 * definition-driven `NeedArtifactForm` (`ArtifactForm`, spec section 6.2).
 * `DeriveRequirementsPanel`/`TraceLinkPanel`/the manual-derive form are not
 * attributes and now live here as siblings of the form (scope boundary
 * shared with the ADR/ArchitectureElement waves) — moved up verbatim from
 * the deleted `NeedForm.tsx`, which owned them before. `attributeVisibility`
 * (the legacy `AttributeVisibilityConfig` prop chain) is dropped entirely:
 * `NeedForm` was its only consumer, and field visibility now comes from the
 * resolved attribute definition like every other migrated type.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { SplitView } from '../SplitView/SplitView';
import { PageHeader } from '../shared/PageHeader';
import { useInterviewStartCta } from '../shared/useInterviewStartCta';
import { ConfirmDialog } from '../shared/ConfirmDialog';
import { NeedList } from './NeedList';
import { NeedArtifactForm } from './NeedArtifactForm';
import { CustomFieldsEditor } from '../shared/CustomFieldsEditor';
import { RightSidebar } from '../shared/ArtifactInspector';
import type { VersionRef } from '../shared/ArtifactInspector';
import { TraceLinkPanel } from '../shared/TraceLinkPanel';
import { DeriveRequirementsPanel } from './DeriveRequirementsPanel';
import { DeriveRequirementForm } from '../shared/DeriveRequirementForm';
import { TraceSpine, useDerivationChain } from '../shared/TraceSpine';
import type { ChainArtifact } from '../shared/TraceSpine';
import { getArtifactRoute } from '../../utils/artifactRoutes';
import { useEntityReset } from '../../hooks/use-entity-reset';
import { useFormDirty } from '../../hooks/use-form-dirty';
import { useNeedData } from './useNeedData';
import { useWorkspace } from '../../context/WorkspaceContext';
import { stakeholderNeedApi } from '../../api/stakeholder-need';
import type { DerivedRequirementDraft } from '../../api/stakeholder-need';
import { requirementsApi } from '../../api/requirements';
import { architectureApi } from '../../api/architecture';
import { tracelinksApi } from '../../api/tracelinks';
import type { ArchitectureElement, Requirement } from '../../types';

export default function NeedsEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace, workspaces } = useWorkspace();
  // Shared with the other artifact routes so the CTA cannot drift.
  const interviewCta = useInterviewStartCta('StakeholderNeed');
  const { needs, need, isLoading, error, refresh } = useNeedData(selectedId);
  const [showCreate, setShowCreate] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  // BUG-11 (Systemaudit 2026-08-18, §4): description/category are ordinary
  // stakeholderNeedApi.create() fields the backend already accepts — they
  // had no editor in this create form.
  const [newDescription, setNewDescription] = useState('');
  const [newCategory, setNewCategory] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);

  // Systemaudit 2026-08-27 UI-06: does the currently-open form have unsaved
  // local edits? Reported by NeedArtifactForm via onDirtyChange.
  // `pendingSelectId` holds a tree-node click that arrived while dirty, so
  // it can be confirmed or discarded instead of silently overwriting the
  // open edit — mirrors RequirementEditors' issue #672 handling.
  const [formDirty, setFormDirty] = useState(false);
  const [pendingSelectId, setPendingSelectId] = useState<string | null>(null);

  // R-1 (Task 23 fix round): custom_fields is a free-form JSON blob the
  // definition-driven NeedArtifactForm cannot render (no `kind: "extended"`
  // attribute exists for StakeholderNeed), so the CustomFieldsEditor lives
  // here as a sibling — same scope boundary as DeriveRequirementsPanel/
  // TraceLinkPanel below. Reset on need switch, not on every refetch of the
  // same need (useEntityReset), matching changeReason's own reset in
  // NeedArtifactForm.
  const [customFieldsDraft, setCustomFieldsDraft] = useState<Record<string, unknown>>({});
  // N-1 (Task 23 fix round 3): customFieldsDraft must feed the same dirty
  // gate `formDirty` does, or editing only a custom field and switching to
  // another need silently discards the edit with no unsaved-changes dialog
  // — the CustomFieldsEditor is a sibling of NeedArtifactForm, not wired
  // into its own useFormDirty/onDirtyChange at all. Value-diff against
  // need.custom_fields (not a non-empty check), same primitive S-2 already
  // uses inside NeedArtifactForm for changeReason.
  const { isDirty: customFieldsDirty, markClean: markCustomFieldsClean } = useFormDirty(
    customFieldsDraft,
    need?.custom_fields ?? {},
  );
  const isFormDirty = formDirty || customFieldsDirty;
  useEntityReset(need?.id ?? '__none__', () => {
    const baseline = need?.custom_fields ?? {};
    setCustomFieldsDraft(baseline);
    markCustomFieldsClean(baseline);
  });

  // Manual "Ableiten": create a Requirement derived from this need, with an
  // optional architecture allocation (SE: Req --derives-from--> Need,
  // Req --allocated-to--> ArchitectureElement). Moved up from the deleted
  // NeedForm.tsx (Task 23) — not an attribute, stays a sibling of the form.
  const [showDeriveForm, setShowDeriveForm] = useState(false);
  const [deriveTitle, setDeriveTitle] = useState('');
  const [deriveArchId, setDeriveArchId] = useState('');
  const [isManualDeriving, setIsManualDeriving] = useState(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);
  const [archElements, setArchElements] = useState<ArchitectureElement[]>([]);

  // AI-assisted derive (REQ-L2-AI-001/002) — draft/accept flow, also moved
  // up from NeedForm.tsx.
  const [isDeriving, setIsDeriving] = useState(false);
  const [derivationStatus, setDerivationStatus] = useState<string | null>(null);
  const [derivationIsError, setDerivationIsError] = useState(false);
  const [derivedDrafts, setDerivedDrafts] = useState<DerivedRequirementDraft[] | null>(null);

  useEffect(() => {
    if (!showDeriveForm || !need) return;
    let cancelled = false;
    architectureApi
      .listAll(need.workspace_id)
      .then((els) => { if (!cancelled) setArchElements(els); })
      .catch(() => { if (!cancelled) setArchElements([]); });
    return () => { cancelled = true; };
  }, [showDeriveForm, need]);

  const handleManualDerive = async () => {
    if (!need) return;
    if (!deriveTitle.trim()) {
      setDeriveError(t('traceability.deriveTitleRequired'));
      return;
    }
    setIsManualDeriving(true);
    setDeriveError(null);
    // UI-33 (Systemaudit 2026-08-27 AP-5): this is three independent REST
    // calls (create Requirement, create 'derives-from' link, optionally
    // create 'allocated-to' link), not one DB transaction — a failure on
    // either link call used to leave `created` as an orphaned Requirement
    // (persisted, but never linked back to the Need) while the user only
    // saw a generic "derive failed" message with no indication anything had
    // been written at all.
    let created: Requirement | null = null;
    try {
      created = await requirementsApi.create({
        workspace_id: need.workspace_id,
        title: deriveTitle.trim(),
      });
      await tracelinksApi.create({
        source_id: created.id,
        target_id: need.artifact_id,
        link_type: 'derives-from',
      });
      if (deriveArchId) {
        await tracelinksApi.create({
          source_id: created.id,
          target_id: deriveArchId,
          link_type: 'allocated-to',
        });
      }
      setShowDeriveForm(false);
      setDeriveTitle('');
      setDeriveArchId('');
      refresh();
      navigate(`/requirements/${created.id}`);
    } catch (err) {
      console.error(err);
      const apiErr = err as { error?: { message?: string } };
      const baseMessage = apiErr?.error?.message ?? t('needs.deriveFailed');
      if (created) {
        // Best-effort compensating action: soft-delete the orphan instead
        // of leaving it silently in the working set, and tell the user
        // explicitly whether that cleanup succeeded — never just "derive
        // failed" once something was actually persisted.
        try {
          await requirementsApi.delete(created.id);
          setDeriveError(
            t('needs.deriveRolledBack', {
              message: baseMessage,
              defaultValue: `${baseMessage} The already-created requirement was rolled back (archived).`,
            }),
          );
        } catch (rollbackErr) {
          console.error(rollbackErr);
          setDeriveError(
            t('needs.derivePartialFailure', {
              message: baseMessage,
              id: created.id,
              defaultValue: `${baseMessage} Warning: a requirement was already created, but linking it to the need failed and the automatic rollback failed too. Please check manually (requirement id: ${created.id}).`,
            }),
          );
        }
      } else {
        setDeriveError(baseMessage);
      }
    } finally {
      setIsManualDeriving(false);
    }
  };

  const handleDerive = async () => {
    if (!need) return;
    setIsDeriving(true);
    setDerivationIsError(false);
    setDerivationStatus(t('needs.deriveStarting'));
    setDerivedDrafts(null);
    try {
      const res = await stakeholderNeedApi.deriveRequirements(need.id);
      const drafts = res.drafts ?? [];
      if (drafts.length === 0) {
        setDerivationStatus(t('needs.deriveEmpty'));
        return;
      }
      setDerivedDrafts(drafts);
      setDerivationStatus(null);
    } catch (err) {
      console.error(err);
      const apiErr = err as { error?: { message?: string } };
      setDerivationIsError(true);
      setDerivationStatus(apiErr?.error?.message ?? t('needs.deriveFailed'));
    } finally {
      setIsDeriving(false);
    }
  };

  const handleDraftsAccepted = (count: number) => {
    setDerivedDrafts(null);
    setDerivationIsError(false);
    setDerivationStatus(t('needs.deriveCreated', { count }));
    // Task 23: NeedForm previously wired this to an `onNeedsChanged` prop
    // that no call site ever passed a value for (dead — `refresh()` never
    // actually ran after an accepted derive). Now that this handler lives
    // directly in NeedsEditors, it can call the real local `refresh`.
    refresh();
  };

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
    // F-2 (Task 23 fix round 4): a save that touched customFieldsDraft left
    // customFieldsDirty stuck `true` forever — markCustomFieldsClean was only
    // ever called from useEntityReset/confirmPendingSelect, never after a
    // successful save, so the very next need-switch showed a false
    // unsaved-changes dialog. Re-anchor the baseline to the just-saved
    // draft, mirroring how NeedArtifactForm's own formDirty/changeReason
    // halves already clear on save.
    markCustomFieldsClean(customFieldsDraft);
    refresh();
  };

  const handleDeleted = () => {
    navigate('/needs');
    refresh();
  };

  /**
   * Systemaudit 2026-08-27 UI-06: mirrors RequirementEditors'
   * `selectRequirement` (issue #672) — a tree-row click used to call
   * `navigate()` directly, which swaps the URL (and therefore the `need`
   * prop the open form is bound to) immediately, discarding any unsaved
   * edit with no warning. Unsaved edits now gate the navigation behind a
   * confirmation instead.
   */
  const selectNeed = useCallback(
    (id: string): void => {
      if (isFormDirty && id !== selectedId) {
        setPendingSelectId(id);
        return;
      }
      navigate(`/needs/${id}`);
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
    // target need's own useEntityReset callback fires after navigation.
    markCustomFieldsClean(customFieldsDraft);
    navigate(`/needs/${target}`);
  }, [pendingSelectId, navigate, customFieldsDraft, markCustomFieldsClean]);

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
      {pendingSelectId && (
        <ConfirmDialog
          title={t('editor.unsavedChangesTitle')}
          message={t('editor.unsavedChangesMessage')}
          confirmLabel={t('editor.discardChanges')}
          onConfirm={confirmPendingSelect}
          onCancel={() => setPendingSelectId(null)}
          testId="need-unsaved-changes-dialog"
        />
      )}
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
        secondaryActions={[interviewCta]}
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
          onSelect={selectNeed}
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
            {need ? (
              <>
                <NeedArtifactForm
                  need={need}
                  onSaved={handleSaved}
                  onDeleted={handleDeleted}
                  onDirtyChange={setFormDirty}
                  customFields={customFieldsDraft}
                />
                {/* R-1: sibling of the definition-driven form, not inside it
                    — see NeedArtifactForm's docstring for why. */}
                <div style={{ marginTop: 'var(--space-4)' }}>
                  <h3 style={{ fontSize: 'var(--font-size-md)', marginBottom: 'var(--space-4)', borderBottom: '1px solid var(--color-border)', paddingBottom: 'var(--space-2)' }}>
                    {t('customFields.section')}
                  </h3>
                  <CustomFieldsEditor
                    key={need.id}
                    value={need.custom_fields}
                    onChange={setCustomFieldsDraft}
                  />
                </div>
              </>
            ) : (
              <p style={{ color: 'var(--color-text-muted)', fontSize: 'var(--font-size-lg)', textAlign: 'center', padding: 'var(--space-8)' }}>
                {t('needs.selectNeed')}
              </p>
            )}

            {need && (
              <TraceLinkPanel
                workspaceId={need.workspace_id}
                artifactId={need.artifact_id}
                onDerive={handleDerive}
                isDeriving={isDeriving}
              />
            )}
            {derivationStatus && (
              <div
                role={derivationIsError ? 'alert' : 'status'}
                data-testid="need-derive-status"
                style={{
                  marginTop: 'var(--space-2)',
                  fontSize: 'var(--font-size-sm)',
                  color: derivationIsError ? 'var(--color-danger)' : 'var(--color-text)',
                }}
              >
                {derivationStatus}
              </div>
            )}
            {need && derivedDrafts && (
              <div style={{ marginTop: 'var(--space-3)' }}>
                <DeriveRequirementsPanel
                  workspaceId={need.workspace_id}
                  needArtifactId={need.artifact_id}
                  drafts={derivedDrafts}
                  onAccepted={handleDraftsAccepted}
                  onDiscard={() => setDerivedDrafts(null)}
                />
              </div>
            )}

            {/* Manual derive: Requirement from this need + optional
                architecture allocation — same flow as in the requirements
                mask. */}
            {need && (
              <div style={{ marginTop: 'var(--space-4)' }}>
                <DeriveRequirementForm
                  isOpen={showDeriveForm}
                  onOpen={() => setShowDeriveForm(true)}
                  onCancel={() => { setShowDeriveForm(false); setDeriveError(null); }}
                  onSubmit={(e) => { e.preventDefault(); void handleManualDerive(); }}
                  title={deriveTitle}
                  onTitleChange={setDeriveTitle}
                  architectureElements={archElements}
                  architectureElementId={deriveArchId}
                  onArchitectureElementChange={setDeriveArchId}
                  isSubmitting={isManualDeriving}
                  error={deriveError}
                  testIdPrefix="need"
                />
              </div>
            )}
          </div>
          {/* ArtifactInspector — REQ-L1-095, REQ-L2-RF-034 (detail only).
              hideTraceLinks: <TraceLinkPanel> above owns trace-link CRUD
              (Task 3.3). */}
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
