/**
 * ARCH-L1-001 ReactFrontend — ArchitectureEditors (COMP-RF-004).
 *
 * leaf_id: COMP-RF-004
 * req_id:  REQ-L2-RF-004 (Architecture-Editor),
 *          REQ-L3-RF004-001 (CRUD-Operationen — Create/Read/Update/Delete),
 *          REQ-L3-RF004-002 (Markdown-Description-Editing mit Toggle),
 *          REQ-L3-RF004-003 (Verknüpfte Requirements in Seitenleiste)
 *
 * Interfaces implemented:
 *   IF-RF-INT-001  ← NavigationShell activates this view
 *   IF-RF-INT-002  ← I18nService via useTranslation
 *   IF-RF-INT-003  ← artifact_id from URL params
 *   IF-RF-EXT-OUT-001 → CRUD on /api/v1/architecture/
 */

import { useState, useCallback, useMemo, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useArchitectureData } from "./useArchitectureData";
import { SplitView } from "../SplitView/SplitView";
import { WorkspaceTree } from "../shared/WorkspaceTree";
import type { WorkspaceTreeNode } from "../shared/WorkspaceTree";
import { useWorkspaceLocks } from "../shared/WorkspaceTree/useWorkspaceLocks";
import { EmptyState } from "../shared/EmptyState";
import { PageHeader } from "../shared/PageHeader";
import { ArtifactId } from "../shared/ArtifactId";
import { StatusBadge } from "../shared/StatusBadge";
import { useInterviewStartCta } from "../shared/useInterviewStartCta";
import { IncludeDeletedToggle } from "../shared/IncludeDeletedToggle/IncludeDeletedToggle";
import { ListToolbar } from "../shared/ListToolbar";
import { TraceSpine, useDerivationChain } from "../shared/TraceSpine";
import type { ChainArtifact } from "../shared/TraceSpine";
import { ArchitectureArtifactForm } from "./ArchitectureArtifactForm";
import { ArchitectureLegend } from "./ArchitectureLegend";
import { Dialog } from "../shared/Dialog";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { SAVE_SHORTCUT_ARIA } from "../../hooks/useSaveShortcut";
import { useRequiredValidation } from "../shared/useRequiredValidation";
import { TraceLinkPanel } from "../shared/TraceLinkPanel";
import { DeriveRequirementForm } from "../shared/DeriveRequirementForm";
import { ArchitectureDecomposePanel } from "../ArchitectureDecompose/ArchitectureDecomposePanel";
import { AiActionSection, type AiActionDescriptor } from "../shared/AiActions";
import { AiDerivationDialog } from "../shared/AiDerivationDialog";
import { RequirementBundleExportPanel } from "../RequirementBundleExport/RequirementBundleExportPanel";
import { InspectorShell } from "../shared/ArtifactInspector";
import type { VersionRef } from "../shared/ArtifactInspector";
import { EntityTypeProvider } from "../../context/EntityTypeContext";
import { architectureApi } from "../../api/architecture";
import { useRiskDerivation } from "./use-risk-derivation";
import { useArchitectureListFilters } from "./use-architecture-list-filters";
import { useArchitectureCreate } from "./use-architecture-create";
import { useArchitectureDerive } from "./use-architecture-derive";
import { useArchitectureDecompose } from "./use-architecture-decompose";
import { artifactsApi } from "../../api/artifacts";
import { extractApiErrorMessage } from "../../api/client";
import { useWorkspace } from "../../context/WorkspaceContext";
import type {
  ArchitectureElement,
} from "../../types";
import styles from "./ArchitectureEditors.module.css";
// F-04 (code review, 2026-08-19): shared create-form field styles.
import fieldHints from "../shared/FieldHints.module.css";
import { FormField } from "../shared/FormField";
import { useFieldContract } from "../../hooks/useFieldContract";

// (Style helpers and dialog moved to ArchitectureForm component)

// REQ-175: ArchitectureElement.lifecycle_status values (see types/index.ts).
// 'deleted' is intentionally omitted — deleted elements are hidden in
// normal views (REQ-006).
const ARCH_LIFECYCLE_STATUSES = ['active', 'outdated', 'deprecated'] as const;

// ---------------------------------------------------------------------------
// ArchitectureEditors — main view with SplitView integration
// ---------------------------------------------------------------------------

/**
 * ARCH-L1-001 ReactFrontend — ArchitectureEditors (COMP-RF-004).
 *
 * Refactored to use SplitView component (REQ-L1-084) for generic
 * split-panel layout. Uses WorkspaceTree (left, REQ-003) and
 * ArchitectureForm (right) for cleaner composition.
 *
 * Dynamic field visibility via EntityTypeProvider + ASIL/Make-or-Buy
 * dropdowns + UID/Version read-only header (REQ-L3-RF004-004).
 */

export default function ArchitectureEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  // Shared with the other artifact routes so the CTA cannot drift.
  const interviewCta = useInterviewStartCta("ArchitectureElement");
  const {
    includeDeleted,
    setIncludeDeleted,
    listSearch,
    setListSearch,
    statusFilter,
    setStatusFilter,
    resetFilters: resetListFilters,
  } = useArchitectureListFilters();

  const { elements, element, isLoading, error, refresh } =
    useArchitectureData(selectedId, includeDeleted);
  // P4.4: one batch read for the whole tree. Keys are ArchitectureElement.id —
  // the id this tree already uses as node id. A failed read degrades to "no
  // markers"; the backend still rejects a move of a frozen element with 409.
  const locks = useWorkspaceLocks(activeWorkspace?.id ?? null, "architecture");

  // Feed the ArtifactInspector with the current version
  // (REQ-L2-RF-035). The full /versions/ list is fetched inside
  // VersionPanel; we only hand it the current row to anchor the
  // diff baseline (UI standards §4.1).
  const currentVersion: VersionRef | undefined = useMemo(() => {
    if (!element) return undefined;
    return {
      version: element.version,
      label: `v${element.version}`,
      createdAt: element.updated_at ?? element.created_at,
      baselineIds: [],
    };
  }, [element]);

  // Inline create + search state
  // BUG-11 (Systemaudit 2026-08-18, §4): `description` is an ordinary
  // architectureApi.create() field the backend already accepts — it had no
  // editor in this quick-create form.
  // REQ-175: lifecycle-status filter. ArchitectureElement has no denormalized
  // workflow status, so we filter on the available lifecycle_status field —
  // sourced from the backing Artifact since the Datenmodell-Konsolidierung.

  // Delete-confirmation target from list context menu
  const [deleteTarget, setDeleteTarget] = useState<ArchitectureElement | null>(null);

  // Issue #672: does the currently-open ArchitectureForm have unsaved local
  // edits? Reported by the form itself via onDirtyChange. `pendingSelectId`
  // holds a tree-node click that arrived while dirty, so it can be
  // confirmed or discarded instead of silently overwriting the open edit.
  const [isFormDirty, setIsFormDirty] = useState(false);
  const [pendingSelectId, setPendingSelectId] = useState<string | null>(null);

  // #340: rejected create/delete calls used to end in a bare console.error,
  // leaving the list unchanged and the user without any reason. One banner in
  // the list panel serves both — they are the only two list-level writes.
  const [listActionError, setListActionError] = useState<string | null>(null);
  // GitHub #1392: per-field half of a rejected create (`details[].field`).
  // #1732: replaces the #1595 "disabled + hint" decision. The Create button
  // stays active, a click validates, the field is marked and focused.
  const {
    errors: requiredErrors,
    validate,
    focusFirstInvalid,
    clearError,
  } = useRequiredValidation();

  const {
    showCreateForm,
    newTitle,
    newDescription,
    isCreating,
    createFieldErrors,
    setNewTitle,
    setNewDescription,
    createFormRef,
    handleCreate,
    handleInlineCreate,
    handleCancelCreate,
    openCreateForm,
  } = useArchitectureCreate({
    workspaceId: activeWorkspace?.id,
    t,
    refresh,
    navigate,
    validation: { validate, focusFirstInvalid },
    onError: setListActionError,
  });

  // GitHub #1393/#1392: required + `maxLength` from the workspace's own
  // configuration (`ArchitectureElement.title` is required, 500 characters).
  const { field } = useFieldContract('ArchitectureElement', {
    enabled: showCreateForm,
  });

  // "Ableiten": create a Requirement allocated to the selected element
  // (SE: Req --allocated-to--> ArchitectureElement). Own module (#598 S2).
  const {
    showDeriveForm,
    deriveTitle,
    isDeriving,
    deriveError,
    openDeriveForm,
    closeDeriveForm,
    setDeriveTitle,
    handleDeriveRequirement,
  } = useArchitectureDerive({
    element: element ?? null,
    workspaceId: activeWorkspace?.id,
    t,
    navigate,
  });

  // AI Decompose panel state (own module, #598 S2).
  const {
    showDecomposePanel,
    showDecomposeCloseConfirm,
    openDecomposePanel,
    setDecomposeHasPendingWork,
    requestCloseDecomposePanel,
    confirmCloseDecomposePanel,
    cancelCloseDecomposePanel,
    handleCommitted: handleDecomposeCommitted,
  } = useArchitectureDecompose();

  // #1360 (W12c): AI risk derivation state (the shared review dialog).
  const {
    riskOpen,
    riskDrafts,
    riskLoading,
    riskLoadError,
    riskSaving,
    riskSubmitError,
    riskStatus,
    openRiskDialog,
    closeRiskDialog,
    decide: handleRiskDecision,
  } = useRiskDerivation(element ?? null, t);

  /**
   * Issue #1092: the route's AI-action set, in one list — the AI Decompose
   * trigger is this route's only one, and it now shares the section, the flat
   * icon and the button variant with the Requirements and Needs routes. Empty
   * when no element is selected, and an empty list renders no section at all.
   *
   * #1360 (W12c): the risk derivation (#1358's `derive-risks` REST parity, no
   * UI entry before this) joins the same section — it is the element-scoped
   * derivation, so the element route is its natural home.
   */
  const aiActions = useMemo<AiActionDescriptor[]>(() => {
    if (!element) return [];
    return [
      {
        label: t("archDecompose.trigger"),
        hint: t("archDecompose.triggerHint"),
        onClick: openDecomposePanel,
        testId: "arch-decompose-btn",
      },
      {
        label: t("aiDerivation.riskAction"),
        hint: t("aiActions.hint"),
        onClick: () => void openRiskDialog(),
        disabled: riskLoading,
        testId: "arch-derive-risks-btn",
      },
    ];
  }, [element, t, openRiskDialog, riskLoading]);

  // Requirement Bundle Export panel state
  const [showBundleExportPanel, setShowBundleExportPanel] = useState(false);

  // Legend (help) dialog. Requested after a live test: the page shows five
  // badge families and nothing said which of them carries the colour.
  const [showLegend, setShowLegend] = useState(false);

  // F-08: preserve the previous `autoFocus` UX — Dialog's focus trap
  // defaults to the first focusable element (its own × close button).
  const newTitleInputRef = useRef<HTMLInputElement | null>(null);
  // #1278: `create-arch-btn` is disabled while the create dialog is open — the
  // browser blurs it in the commit that mounts the dialog, so the dialog needs
  // this explicit trigger ref to return focus on close (see useFocusTrap).
  const createTriggerRef = useRef<HTMLButtonElement | null>(null);

  /**
   * Drag & drop reordering/reparenting from the tree (P1 Task 1.7).
   *
   * WorkspaceTree reports only the move (drop, Alt+↑/↓ or the "Move…"
   * dialog); the tree applies it optimistically and rolls back on rejection.
   * It refuses cycle-forming moves itself (self, current parent, own subtree)
   * using the same `collectSelfAndDescendantIds` helper that keeps descendants
   * out of `ArchitectureForm`'s parent dropdown, so both ways of changing a
   * parent forbid exactly the same set. That guard is deliberate rather than
   * redundant: server-side invariant I1 (circular parent reference) only runs
   * at Standard/Extended rigor (`RIGOR_INVARIANT_PRESETS`,
   * backend/application/validators.py) while a workspace defaults to Minimal,
   * where a cycle would be persisted and would take the whole subtree out of
   * the tree view.
   *
   * Residual risk, unchanged by this: the guard is browser-side only. A REST
   * or MCP client calling the move endpoint on a Minimal-rigor workspace can
   * still create a cycle. Closing that needs I1 enabled for every tier
   * server-side.
   *
   * The move endpoint keys on the backing Artifact id, while the tree's nodes
   * carry the ArchitectureElement id (`el.id`, used by the route/selection),
   * so every id in the triple is translated here. The rejection path is the
   * tree's toast, which is why this handler lets the error propagate.
   */
  const artifactIdByElementId = useMemo(
    () =>
      new Map<string, string>(
        elements.map((el) => [el.id, el.artifact_id ?? el.id]),
      ),
    [elements],
  );

  const handleReorder = useCallback(
    async (
      id: string,
      newParentId: string | null,
      afterId: string | null | undefined,
    ): Promise<void> => {
      setListActionError(null);
      const toArtifactId = (nodeId: string | null): string | null =>
        nodeId === null
          ? null
          : (artifactIdByElementId.get(nodeId) ?? nodeId);
      const artifactId = toArtifactId(id);
      if (artifactId === null) return;
      try {
        await artifactsApi.move(artifactId, {
          parent_id: toArtifactId(newParentId),
          ...(afterId === undefined
            ? {}
            : { after_id: toArtifactId(afterId) }),
        });
        refresh();
      } catch (err: unknown) {
        // Keep the inline banner (#340) for a refused move while the tree
        // rolls its optimistic order back; rethrow so the tree also surfaces
        // the failure.
        setListActionError(
          extractApiErrorMessage(err) ?? t("arch.reparentFailed"),
        );
        throw err;
      }
    },
    [artifactIdByElementId, refresh, t],
  );

  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      setListActionError(null);
      try {
        await architectureApi.delete(id);
        refresh();
        navigate("/architecture");
      } catch (err: unknown) {
        // #340: a refused delete used to leave the element in the tree with
        // no explanation. Shares the list-panel banner with create.
        setListActionError(extractApiErrorMessage(err) ?? t("arch.deleteFailed"));
      }
    },
    [refresh, navigate, t]
  );

  /**
   * Issue #672: the tree's onSelect used to call `navigate()` directly,
   * which swaps the URL — and therefore the `element` prop the open
   * ArchitectureForm is bound to — immediately, discarding any unsaved edit
   * with no warning. Unsaved edits now gate the navigation behind a
   * confirmation instead.
   */
  const selectElement = useCallback(
    (id: string): void => {
      if (isFormDirty && id !== selectedId) {
        setPendingSelectId(id);
        return;
      }
      navigate(`/architecture/${id}`);
    },
    [isFormDirty, navigate, selectedId]
  );

  const confirmPendingSelect = useCallback((): void => {
    if (!pendingSelectId) return;
    const target = pendingSelectId;
    setPendingSelectId(null);
    setIsFormDirty(false);
    navigate(`/architecture/${target}`);
  }, [pendingSelectId, navigate]);

  // Filter elements by search and convert to WorkspaceTreeNode[] (REQ-003).
  // Must be declared before any early return for stable hook order.
  const filteredElements = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    return elements.filter((el) => {
      if (statusFilter && (el.lifecycle_status ?? 'active') !== statusFilter) {
        return false;
      }
      if (!q) return true;
      return (
        el.title.toLowerCase().includes(q) ||
        Boolean(el.uid && el.uid.toLowerCase().includes(q))
      );
    });
  }, [elements, listSearch, statusFilter]);

  const archTreeNodes = useMemo((): WorkspaceTreeNode[] =>
    filteredElements.map((el) => ({
      id: el.id,
      name: el.title || t('editor.untitled'),
      // Issue #932: show the readable local uid in the tree, not just in search.
      identifier: el.uid,
      parentId: el.parent_id ?? null,
      level: el.level != null ? `L${el.level}` : 'L0',
      outdated:
        el.lifecycle_status === 'outdated' || el.lifecycle_status === 'deprecated',
      // P4.4: workflow lock — disables drag, Alt+↑/↓ and "Move…" for this row.
      locked: locks[el.id] ? { state: locks[el.id] } : null,
    })),
  [filteredElements, locks, t]);

  // UI concept ch. 12.1: always-visible summary. `lifecycle_status` defaults
  // to 'active' server-side, so an absent value counts as active here too.
  const archSummary = useMemo(() => {
    const active = elements.filter(
      (el) => (el.lifecycle_status ?? 'active') === 'active',
    ).length;
    return [
      t('arch.summary', { count: elements.length, defaultValue: `${elements.length}` }),
      t('arch.activeSuffix', { count: active, defaultValue: `${active} active` }),
    ].join(' · ');
  }, [elements, t]);

  // Trace spine (ch. 5, ch. 12.10). The chain is composed client-side from
  // the existing /tracelinks/impact/ neighbourhood query — no new backend
  // endpoint. `elements` is already loaded exhaustively by
  // useArchitectureData, so architecture station depths resolve without an
  // extra round trip.
  const derivationChain = useDerivationChain(
    element?.artifact_id ?? element?.id ?? null,
    'ArchitectureElement',
    element?.level ?? 0,
    { architectureElements: elements, enabled: !!element },
  );

  // The trace graph is keyed by Artifact id, the detail routes take the
  // domain-entity id. For architecture the mapping is available locally
  // (the exhaustive element list carries both). For requirements, needs and
  // test cases there is no client-side mapping and no endpoint that resolves
  // an Artifact id to its entity — so those entries are shown but not
  // navigable. See the PR description: closing this needs a backend
  // resolver, which this change deliberately does not add.
  const archElementByArtifactId = useMemo(() => {
    const map = new Map<string, string>();
    for (const el of elements) {
      if (el.artifact_id) map.set(el.artifact_id, el.id);
      map.set(el.id, el.id);
    }
    return map;
  }, [elements]);

  const isChainArtifactOpenable = useCallback(
    (artifact: ChainArtifact): boolean =>
      artifact.artifactType === 'ArchitectureElement' &&
      archElementByArtifactId.has(artifact.id),
    [archElementByArtifactId],
  );

  const handleOpenChainArtifact = useCallback(
    (artifact: ChainArtifact): void => {
      const elementId = archElementByArtifactId.get(artifact.id);
      if (artifact.artifactType === 'ArchitectureElement' && elementId) {
        navigate(`/architecture/${elementId}`);
      }
    },
    [archElementByArtifactId, navigate],
  );

  // #1762 (M3, mirrors M2): the inspector's programmatic focus targets live in
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

  if (isLoading) {
    return (
      <p
        role="status"
        className={styles.loadingText}
      >
        {t("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        className={styles.errorPanel}
      >
        <p className={styles.errorText}>{error}</p>
        <button
          onClick={refresh}
          className={`btn-primary ${styles.reloadButton}`}
        >
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  // Build list panel with header
  const listPanel = (
    <div className={styles.listPanel}>
      {/* UI concept ch. 12.2: search / filter / sort come from the shared
          ListToolbar instead of a hand-built input + select pair. The
          heading and the primary action moved up into the page-level
          <PageHeader> (ch. 12.1) — a toolbar carries no primary action.
          The status filter is now `arch-filter-status` (was
          `arch-status-filter`); it is not referenced by any e2e spec. */}
      <div className={styles.toolbarSlot}>
        <ListToolbar
          testIdPrefix="arch"
          searchValue={listSearch}
          onSearchChange={setListSearch}
          searchPlaceholder={t('editor.searchPlaceholder', 'Search...')}
          filters={[
            {
              // REQ-175: lifecycle-status filter. ArchitectureElement has no
              // denormalized workflow status, so this filters lifecycle_status
              // (backing-Artifact soft-delete flag, not a workflow state).
              id: 'status',
              allLabel: t('editor.allStatuses', 'All Statuses'),
              value: statusFilter,
              options: ARCH_LIFECYCLE_STATUSES.map((s) => ({
                value: s,
                label: t(`arch.lifecycleStatus.${s}`, s),
              })),
              onChange: setStatusFilter,
            },
          ]}
          countLabel={
            listSearch || statusFilter
              ? t('editor.filteredCount', { shown: filteredElements.length, total: elements.length })
              : String(elements.length)
          }
        />
      </div>

      {/* #340: server rejection of a list-level write (create/delete). */}
      {listActionError && (
        <p role="alert" data-testid="arch-action-error" className={styles.actionError}>
          {listActionError}
        </p>
      )}

      {/* Inline create form — F-08: wrapped in the shared Dialog primitive
          (GESAMTTEST_BERICHT 2026-08-21 §5 finding 8); form markup unchanged. */}
      {showCreateForm && (
        <Dialog
          title={t('arch.newElementTitle')}
          onClose={handleCancelCreate}
          initialFocusRef={newTitleInputRef}
          triggerRef={createTriggerRef}
          testId="arch-new-dialog"
        >
        <form
          ref={createFormRef}
          // Native `required` on the controls (via `field(...).controlProps`)
          // carries the `:required` semantics; `noValidate` keeps the browser
          // bubble from pre-empting the app's own `details[].field` error flow.
          noValidate
          onSubmit={(e) => { e.preventDefault(); void handleInlineCreate(); }}
          className={styles.createForm}
        >
          {/* #955: the input carried no id/name/aria-label and this label had
              no `htmlFor`, so the field had no accessible name — only a
              placeholder. Mirrors the description field's `htmlFor`/`id` pair
              right below. */}
          {/* #1393: required marker + #1392: `maxLength` from the server
              contract (`ArchitectureElement.title` is 500 characters). */}
          <FormField
            htmlFor="arch-new-title"
            label={t('editor.title', 'Title')}
            required={field('title').required}
            // #1732: the empty-title refusal is a click-time message at the
            // field (role="alert" via FormField), not a disabled button with
            // a standing hint.
            error={requiredErrors.title ?? createFieldErrors.title?.join(', ')}
            labelClassName={styles.createTitleLabel}
          >
            <input
              id="arch-new-title"
              data-testid="arch-new-title-input"
              ref={newTitleInputRef}
              type="text" value={newTitle} onChange={(e) => {
                setNewTitle(e.target.value);
                clearError('title');
              }}
              placeholder={t('arch.newElementTitle')}
              className={styles.createTitleInput}
              {...field('title').controlProps}
            />
          </FormField>
          {/* BUG-11: description — an ordinary architectureApi.create() field
              the backend already accepts, previously missing here. */}
          <FormField
            htmlFor="arch-new-description"
            label={t('editor.description')}
            required={field('description').required}
            error={createFieldErrors.description?.join(', ')}
            labelClassName={fieldHints.createLabelInline}
          >
            <textarea
              id="arch-new-description"
              data-testid="arch-new-description-input"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              rows={3}
              className={fieldHints.createInput}
              {...field('description').controlProps}
            />
          </FormField>

          <div className={styles.createActions}>
            {/* issue #719: shared btn-secondary/btn-primary pair, same as the
                Adr/Risk/Issue/TestCase/Requirement create dialogs. The inline
                styles this replaces had no disabled treatment at all, so the
                submit button looked enabled while `!newTitle.trim()` blocked
                it. */}
            <button
              data-testid="arch-new-cancel-btn"
              type="button"
              className="btn-secondary"
              onClick={handleCancelCreate}
            >
              {t('actions.cancel', 'Cancel')}
            </button>
            <button
              data-testid="arch-new-save-btn"
              type="submit"
              className="btn-primary"
              disabled={isCreating}
              aria-keyshortcuts={SAVE_SHORTCUT_ARIA}
              title={t('artifactForm.saveShortcutHint', 'Speichern (Strg/Cmd+S)')}
            >
              {isCreating ? t('actions.saving', 'Saving...') : t('actions.create', 'Erstellen')}
            </button>
          </div>
        </form>
        </Dialog>
      )}

      {/* WorkspaceTree — unified navigation panel (REQ-003).
          showLevelBadge renders the shared, neutral <LevelBadge> per row
          (issue #674 — a level is not a state, UI concept ch. 3.3/8.3, so it
          is deliberately not colour-ramped by depth anymore).
          onAddChild surfaces the "+ child" button on each tree row.
          showSearch=false: search is handled by the input above.
          onReorder: drag & drop moves an element under a new parent or above/
          below a sibling, Alt+↑/↓ steps it one place, and the "Move…" dialog
          picks a parent by search. Reinstated on 2026-08-15, reversing the
          2026-07-13 "won't do" note that stood here before. */}
      <div className={styles.treeSlot}>
        <IncludeDeletedToggle
          checked={includeDeleted}
          onChange={setIncludeDeleted}
          testIdPrefix="arch-list"
        />
        {/* GESAMTTEST_BERICHT_2026-08-21.md §6 "Architecture empty-state":
            this route used to fall through to WorkspaceTree's built-in plain
            muted-text emptyLabel/noMatchesLabel instead of the shared
            <EmptyState> headline+description+CTA pattern every sibling list
            page (Needs, ADRs, Risks, ...) already uses — see NeedList.tsx's
            identical wiring, which this mirrors (#179 / ch. 13.3: "nothing
            exists" wants a create action, "nothing matches the filter"
            only wants a filter reset). */}
        {elements.length === 0 ? (
          <EmptyState
            variant="empty"
            testId="arch-tree-empty"
            title={t('arch.emptyTitle', 'No architecture elements yet')}
            description={t(
              'arch.emptyDescription',
              'Architecture elements map system, subsystems and components onto the V-model hierarchy.',
            )}
            actions={[
              { label: t('arch.newElement', 'New Architecture Element'), prefixWithPlus: true, onClick: openCreateForm, testId: 'arch-tree-empty-create' },
            ]}
          />
        ) : archTreeNodes.length === 0 ? (
          <EmptyState
            variant="no-match"
            testId="arch-tree-no-match"
            onResetFilters={resetListFilters}
          />
        ) : (
          <WorkspaceTree
            data-testid="arch-tree"
            nodes={archTreeNodes}
            selectedId={selectedId}
            onSelect={selectElement}
            onAddChild={(parentId) => void handleCreate(parentId)}
            onReorder={handleReorder}
            rootDropzoneLabel={t('arch.tree.dropRoot', 'Drop here to make root (L0)')}
            showLevelBadge={true}
            showSearch={false}
            // Issue #1257: resolve the configured field selection for this
            // artifact type in this workspace (user > workspace > global).
            itemType="ArchitectureElement"
            workspaceId={activeWorkspace?.id ?? null}
            // Issue #665: remember which branches were open so a sidebar
            // section switch (which unmounts this tree) does not reset it.
            stateKey="architecture"
            virtualize
          />
        )}
      </div>
    </div>
  );

  // Build detail panel (form + inspector) — #1762/M3: the detail area is a
  // scroll container plus the tabbed inspector, the spine lives in SplitView's
  // own slot so scrolling the form cannot move it.
  const detailPanel = (
    <div className={styles.rightPane}>
      <div className={styles.detailScroll} ref={detailScrollRef}>
        {element ? (
          <>
            {/* Spec §5.1 #1: the skip link is the first focusable element of
                the detail area and the only way into the inspector that does
                not require walking the form first (#1762 M3). */}
            <a
              href="#inspector-heading"
              className={`btn-ghost ${styles.inspectorSkipLink}`}
              data-testid="inspector-skip-link"
              onClick={(event) => {
                event.preventDefault();
                focusInspectorHeading();
              }}
            >
              {t("sidebar.inspector.skipLink", "Direkt zum Inspektor")}
            </a>
            {/* DoD 2 (#1762/M3): identity and workflow status have exactly one
                place — the artifact head of the route, never the inspector
                (spec §2.2). Architecture had neither in its head until now. */}
            <div className={styles.artifactHead} data-testid="arch-artifact-head">
              <ArtifactId
                value={element.uid}
                fallback={element.id.slice(0, 8)}
                testId="arch-detail-id"
              />
              {element.status ? (
                <StatusBadge status={element.status} testId="arch-detail-status" />
              ) : null}
            </div>

            {/* Main form wrapper */}
            <div className={styles.detailFormCard}>
              <EntityTypeProvider
                entityType="architecture_element"
                entitySubType={element.element_type}
                visibleFields={{
                  asil_level: true,
                  make_or_buy: true,
                }}
              >
                <ArchitectureArtifactForm
                  key={element.id}
                  element={element}
                  onSaved={refresh}
                  // Task 24: ArchitectureArtifactForm deletes through
                  // `architectureApi.delete` itself (ArtifactForm's own confirm
                  // dialog) — routing through the shared `handleDelete(id)`
                  // here would call the delete endpoint a second time. Mirrors
                  // `RiskEditors`/`IssueEditors`' `onDeleted` convention: only
                  // the post-delete navigation/refresh side effects, not the
                  // delete call itself (that still lives in `handleDelete` for
                  // the list-context-menu delete flow below).
                  onDeleted={() => {
                    refresh();
                    navigate("/architecture");
                  }}
                  onDirtyChange={setIsFormDirty}
                />
              </EntityTypeProvider>

              {/* Issue #1092: the AI Decompose trigger's new, single home on
                  this route. It used to be a lone `btn-secondary` wedged
                  between the spine and the form (Task 24), which read as
                  another form action rather than an AI action. Same panel,
                  same `showDecomposePanel` state, same `arch-decompose-btn`
                  test id. */}
              <AiActionSection
                title={t("aiActions.heading")}
                hint={t("aiActions.hint")}
                actions={aiActions}
              />

              {/* #1360: the derivation's outcome, once the dialog is closed. */}
              {riskStatus && (
                <p
                  role="status"
                  data-testid="arch-derive-risks-status"
                  className={styles.selectPrompt}
                >
                  {riskStatus}
                </p>
              )}

              {/* TraceLink panel — carries the e2e test-id since the old
                  placeholder aside ("See the Inspector sidebar") was removed:
                  the linked-requirements CRUD lives HERE, the read-only trace
                  view is split between the spine (derivation/verification)
                  and the inspector's Links tab (every other type). */}
              {(activeWorkspace?.id || element.workspace_id) && (
                <div data-testid="arch-linked-reqs-panel">
                  <TraceLinkPanel
                    workspaceId={activeWorkspace?.id ?? element.workspace_id}
                    artifactId={element.id}
                  />
                </div>
              )}

              {/* Derive requirement allocated to this element */}
              <div className="detail-action-zone">
                <DeriveRequirementForm
                  isOpen={showDeriveForm}
                  onOpen={openDeriveForm}
                  onCancel={closeDeriveForm}
                  onSubmit={(e) => { e.preventDefault(); void handleDeriveRequirement(); }}
                  title={deriveTitle}
                  onTitleChange={setDeriveTitle}
                  architectureElements={[]}
                  architectureElementId=""
                  onArchitectureElementChange={() => {}}
                  showArchitectureField={false}
                  isSubmitting={isDeriving}
                  error={deriveError}
                  testIdPrefix="arch"
                />
              </div>
            </div>
          </>
        ) : (
          <p className={styles.selectPrompt}>{t("arch.selectElement")}</p>
        )}
      </div>

      {/* #1762/M3: the tabbed inspector replaces the stacked RightSidebar.
          #1763: two id spaces — `element.id` drives the versions/diff routes,
          `element.artifact_id` (the backing Artifact) is the only id the
          comments route accepts. */}
      {element && (
        <InspectorShell
          kind="architecture"
          entityId={element.id}
          artifactPk={element.artifact_id ?? null}
          currentVersion={currentVersion}
          coveredRef={detailScrollRef}
          onShowInSpine={focusSpine}
        />
      )}
    </div>
  );

  return (
    <>
      {pendingSelectId && (
        <ConfirmDialog
          title={t("editor.unsavedChangesTitle")}
          message={t("editor.unsavedChangesMessage")}
          confirmLabel={t("editor.discardChanges")}
          onConfirm={confirmPendingSelect}
          onCancel={() => setPendingSelectId(null)}
          testId="arch-unsaved-changes-dialog"
        />
      )}
      {/* Issue #670: the list-level delete used to hand-build its own footer
          buttons on top of <Dialog> (their `btn-danger`/`btn-secondary`
          equivalents inlined as `style={{ }}`), which is exactly the drift
          <ConfirmDialog> exists to prevent. The `confirm-delete-btn` testid is
          preserved verbatim — the Playwright suite selects on it. */}
      {deleteTarget && (
        <ConfirmDialog
          title={t("arch.deleteTitle")}
          message={t("actions.deleteConfirmPromptNamed", { name: deleteTarget.title })}
          confirmLabel={t("actions.delete")}
          onConfirm={() => {
            setDeleteTarget(null);
            void handleDelete(deleteTarget.id);
          }}
          onCancel={() => setDeleteTarget(null)}
          testId="arch-delete-dialog"
          confirmTestId="confirm-delete-btn"
        />
      )}

      {showDecomposePanel && element && activeWorkspace && (
        <Dialog
          title={t("archDecompose.title")}
          description={element.title}
          onClose={requestCloseDecomposePanel}
          size="lg"
          testId="arch-decompose-dialog"
        >
          <ArchitectureDecomposePanel
            workspaceId={activeWorkspace.id}
            element={{ id: element.id, title: element.title }}
            onPendingWorkChange={setDecomposeHasPendingWork}
            onCommitted={() => {
              handleDecomposeCommitted();
              refresh();
            }}
          />
        </Dialog>
      )}

      {/* UI-24: interposed before an Escape/backdrop close would otherwise
          silently discard a generated-but-not-yet-committed decompose draft
          (or one currently being committed). */}
      {showDecomposeCloseConfirm && (
        <ConfirmDialog
          title={t("archDecompose.discardDraftTitle")}
          message={t("archDecompose.discardDraftMessage")}
          confirmLabel={t("archDecompose.discardDraftConfirm")}
          onConfirm={confirmCloseDecomposePanel}
          onCancel={cancelCloseDecomposePanel}
          testId="arch-decompose-discard-confirm"
        />
      )}

      {showBundleExportPanel && element && activeWorkspace && (
        <Dialog
          title={t("bundleExport.title")}
          description={element.title}
          onClose={() => setShowBundleExportPanel(false)}
          size="lg"
          testId="arch-bundle-export-dialog"
        >
          <RequirementBundleExportPanel
            elementId={element.id}
            elementTitle={element.title}
          />
        </Dialog>
      )}

      {/* #1360 (W12c): the shared review dialog for the risk derivation. */}
      {riskOpen && element && (
        <AiDerivationDialog
          open
          title={t("aiDerivation.riskDialogTitle")}
          sourceLabel={t("aiDerivation.riskSource", { title: element.title })}
          drafts={riskDrafts}
          isLoading={riskLoading}
          loadError={riskLoadError}
          isSubmitting={riskSaving}
          submitError={riskSubmitError}
          onConfirm={() => void handleRiskDecision(false)}
          onReviewLater={() => void handleRiskDecision(true)}
          onDiscard={closeRiskDialog}
          testIdPrefix="arch-derive-risks"
        />
      )}

      {/* UI concept ch. 12.1: exactly one <h1> per route, always-visible
          summary, one primary action top right, everything rare in the
          overflow menu. Replaces the <h3> + "+ New" pair that used to sit
          inside the narrow list panel. `create-arch-btn` keeps its test id —
          it is referenced by nine e2e specs.
          The issue #314 width constraint that used to live in a wrapper div
          here now belongs to <PageHeader> itself, so every route gets it.
          The wrapper's extra `padding: 0 var(--space-4)` went with it: it was
          unique to this route and inset the Architecture header by 16px
          against the six other artifact routes, which is exactly the
          divergence this header is supposed to remove. */}
      <PageHeader
        title={t("nav.architecture")}
        summary={archSummary}
        primaryAction={{
          label: t("arch.newElement"),
          prefixWithPlus: true,
          onClick: openCreateForm,
          disabled: showCreateForm,
          testId: "create-arch-btn",
          triggerRef: createTriggerRef,
        }}
        // #797: the guided-interview start is a second *create path*, not a
        // variant of the primary one — as a visible secondary button it made
        // this route show two create buttons where Glossary/ICD/Diagram show
        // one. Secondary actions belong in the overflow menu (ch. 12.1), so
        // it moved there: same action, same `interview-start-cta` testid,
        // exactly one visible create CTA per route.
        overflowActions={[
          interviewCta,
          {
            label: t("archDecompose.trigger", "KI-Zerlegung"),
            onClick: openDecomposePanel,
            disabled: !element || !activeWorkspace,
            testId: "arch-decompose-overflow-btn",
          },
          {
            label: t("bundleExport.trigger", "Requirement-Bundle exportieren"),
            onClick: () => setShowBundleExportPanel(true),
            disabled: !element || !activeWorkspace,
            testId: "arch-bundle-export-overflow-btn",
          },
          {
            // ch. 12.8: the dialog title repeats this label verbatim.
            label: t("archLegend.trigger", "Legende"),
            onClick: () => setShowLegend(true),
            testId: "arch-legend-btn",
          },
        ]}
      />

      {/* Legend — the first user of the real <Dialog> primitive
          (ch. 12.8): portal, focus trap, Escape, focus back to the
          overflow trigger. The two hand-built overlays above still use the
          old pattern; converting them is a separate change. */}
      {showLegend && (
        <Dialog
          title={t("archLegend.trigger", "Legende")}
          description={t(
            "archLegend.dialogDescription",
            "Was die Farben, Kennzeichen und Symbole dieser Ansicht bedeuten.",
          )}
          size="lg"
          onClose={() => setShowLegend(false)}
          testId="arch-legend-dialog"
        >
          <ArchitectureLegend />
        </Dialog>
      )}

      {/* #1762/M3: concept contract (UI_KONZEPT ch. 12.6) — `list`/`detail`/
          `spine` with no drag divider. The tree keeps its 250 px floor and the
          detail content keeps the 448 px floor the concept prescribes. */}
      <SplitView
        list={listPanel}
        detail={detailPanel}
        spine={
          element ? (
            <TraceSpine
              stations={derivationChain.stations}
              isLoading={derivationChain.isLoading}
              error={derivationChain.error}
              onOpenArtifact={handleOpenChainArtifact}
              isOpenable={isChainArtifactOpenable}
            />
          ) : null
        }
        ratio={[40, 60]}
        minWidths={[250, 448]}
        containerClassName={styles.splitWrapper}
      />
    </>
  );
}
