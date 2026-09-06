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
import { EmptyState } from "../shared/EmptyState";
import { PageHeader } from "../shared/PageHeader";
import { useInterviewStartCta } from "../shared/useInterviewStartCta";
import { ListToolbar } from "../shared/ListToolbar";
import { TraceSpine, useDerivationChain } from "../shared/TraceSpine";
import type { ChainArtifact } from "../shared/TraceSpine";
import { ArchitectureForm } from "./ArchitectureForm";
import { ArchitectureLegend } from "./ArchitectureLegend";
import { Dialog } from "../shared/Dialog";
import { ConfirmDialog } from "../shared/ConfirmDialog";
import { TraceLinkPanel } from "../shared/TraceLinkPanel";
import { DeriveRequirementForm } from "../shared/DeriveRequirementForm";
import { ArchitectureDecomposePanel } from "../ArchitectureDecompose/ArchitectureDecomposePanel";
import { RequirementBundleExportPanel } from "../RequirementBundleExport/RequirementBundleExportPanel";
import { requirementsApi } from "../../api/requirements";
import { tracelinksApi } from "../../api/tracelinks";
import { RightSidebar } from "../shared/ArtifactInspector";
import type { VersionRef } from "../shared/ArtifactInspector";
import { EntityTypeProvider } from "../../context/EntityTypeContext";
import { architectureApi } from "../../api/architecture";
import { extractApiErrorMessage } from "../../api/client";
import { useWorkspace } from "../../context/WorkspaceContext";
import type {
  ArchitectureElement,
} from "../../types";
import styles from "./ArchitectureEditors.module.css";
// F-04 (code review, 2026-08-19): shared create-form field styles.
import fieldHints from "../shared/FieldHints.module.css";

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
  const { elements, element, isLoading, error, refresh } =
    useArchitectureData(selectedId);

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
  const [showCreateForm, setShowCreateForm] = useState(false);
  const [newTitle, setNewTitle] = useState('');
  // BUG-11 (Systemaudit 2026-08-18, §4): `description` is an ordinary
  // architectureApi.create() field the backend already accepts — it had no
  // editor in this quick-create form.
  const [newDescription, setNewDescription] = useState('');
  const [listSearch, setListSearch] = useState('');
  // REQ-175: lifecycle-status filter. ArchitectureElement has no denormalized
  // workflow status, so we filter on the available lifecycle_status field —
  // sourced from the backing Artifact since the Datenmodell-Konsolidierung.
  const [statusFilter, setStatusFilter] = useState('');

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

  // "Ableiten": create a Requirement allocated to the selected element
  // (SE: Req --allocated-to--> ArchitectureElement).
  const [showDeriveForm, setShowDeriveForm] = useState(false);
  const [deriveTitle, setDeriveTitle] = useState("");
  const [isDeriving, setIsDeriving] = useState(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);

  // AI Decompose panel state
  const [showDecomposePanel, setShowDecomposePanel] = useState(false);
  // UI-24: an Escape/backdrop close while a generated draft is awaiting
  // review (or a commit is in flight) must not discard it silently.
  const [decomposeHasPendingWork, setDecomposeHasPendingWork] = useState(false);
  const [showDecomposeCloseConfirm, setShowDecomposeCloseConfirm] = useState(false);

  const requestCloseDecomposePanel = useCallback((): void => {
    if (decomposeHasPendingWork) {
      setShowDecomposeCloseConfirm(true);
      return;
    }
    setShowDecomposePanel(false);
  }, [decomposeHasPendingWork]);

  // Requirement Bundle Export panel state
  const [showBundleExportPanel, setShowBundleExportPanel] = useState(false);

  // Legend (help) dialog. Requested after a live test: the page shows five
  // badge families and nothing said which of them carries the colour.
  const [showLegend, setShowLegend] = useState(false);

  const handleDeriveRequirement = useCallback(async (): Promise<void> => {
    if (!element || !activeWorkspace) return;
    if (!deriveTitle.trim()) {
      setDeriveError(t("traceability.deriveTitleRequired"));
      return;
    }
    setIsDeriving(true);
    setDeriveError(null);
    try {
      const created = await requirementsApi.create({
        workspace_id: activeWorkspace.id,
        title: deriveTitle.trim(),
      });
      await tracelinksApi.create({
        source_id: created.id,
        target_id: element.id,
        link_type: "allocated-to",
      });
      setShowDeriveForm(false);
      setDeriveTitle("");
      navigate(`/requirements/${created.id}`);
    } catch (err: unknown) {
      console.error(err);
      const apiErr = err as { error?: { message?: string } };
      setDeriveError(apiErr?.error?.message ?? t("needs.deriveFailed"));
    } finally {
      setIsDeriving(false);
    }
  }, [element, activeWorkspace, deriveTitle, t, navigate]);

  const handleCreate = useCallback(
    async (parentId?: string, customTitle?: string, customDescription?: string): Promise<void> => {
      if (!activeWorkspace) return;
      setListActionError(null);
      try {
        const created = await architectureApi.create({
          workspace_id: activeWorkspace.id,
          title: customTitle || t("arch.newElementTitle"),
          element_type: "component",
          parent_id: parentId ?? undefined,
          // BUG-11: only send what was actually typed.
          ...(customDescription?.trim() ? { description: customDescription.trim() } : {}),
        });
        setShowCreateForm(false);
        setNewTitle('');
        setNewDescription('');
        refresh();
        navigate(`/architecture/${created.id}`);
      } catch (err: unknown) {
        // #340 (same defect class as RequirementEditors): the server rejects
        // markup in a title with a 400 naming the field. Logging that to the
        // console only made a rejected create look like a silent no-op.
        setListActionError(extractApiErrorMessage(err) ?? t("arch.createFailed"));
      }
    },
    [activeWorkspace, t, refresh, navigate]
  );

  const handleInlineCreate = useCallback(async () => {
    if (!newTitle.trim()) return;
    await handleCreate(undefined, newTitle.trim(), newDescription);
  }, [newTitle, newDescription, handleCreate]);

  // F-08 (Dialog migration): Escape / backdrop click / × must discard the
  // draft exactly like the existing Cancel button.
  const handleCancelCreate = useCallback((): void => {
    setShowCreateForm(false);
    setNewTitle('');
    setNewDescription('');
  }, []);

  // F-08: preserve the previous `autoFocus` UX — Dialog's focus trap
  // defaults to the first focusable element (its own × close button).
  const newTitleInputRef = useRef<HTMLInputElement | null>(null);

  /**
   * Drag & drop reparenting from the tree (user decision 2026-08-15).
   *
   * WorkspaceTree only reports the drop. It refuses cycle-forming drops
   * itself (self, current parent, own subtree) using the same
   * `collectSelfAndDescendantIds` helper that keeps descendants out of
   * `ArchitectureForm`'s parent dropdown, so both ways of changing a parent
   * forbid exactly the same set. That guard is deliberate rather than
   * redundant: server-side invariant I1 (circular parent reference) only runs
   * at Standard/Extended rigor (`RIGOR_INVARIANT_PRESETS`,
   * backend/application/validators.py) while a workspace defaults to Minimal,
   * where a cycle would be persisted and would take the whole subtree out of
   * the tree view.
   *
   * Residual risk, unchanged by this: the guard is browser-side only. A REST
   * or MCP client PATCHing `parent_id` directly on a Minimal-rigor workspace
   * can still create a cycle. Closing that needs I1 enabled for every tier
   * server-side.
   *
   * Rejections that do come back from the server (level order I2, single root
   * I5, permissions) share the list-level error banner with create/delete
   * (#340).
   */
  const handleReparent = useCallback(
    async (id: string, newParentId: string | null): Promise<void> => {
      setListActionError(null);
      try {
        await architectureApi.reparent(id, newParentId);
        refresh();
      } catch (err: unknown) {
        setListActionError(
          extractApiErrorMessage(err) ?? t("arch.reparentFailed"),
        );
      }
    },
    [refresh, t],
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
      parentId: el.parent_id ?? null,
      level: el.level != null ? `L${el.level}` : 'L0',
    })),
  [filteredElements, t]);

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

  if (isLoading) {
    return (
      <p
        role="status"
        style={{
          color: "var(--color-text-muted)",
          fontFamily: "var(--font-sans)",
          padding: "var(--space-4)",
        }}
      >
        {t("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <div
        role="alert"
        style={{
          background: "var(--color-surface)",
          borderRadius: "var(--radius-md)",
          boxShadow: "var(--shadow-card)",
          padding: "var(--space-4)",
          fontFamily: "var(--font-sans)",
        }}
      >
        <p style={{ color: "var(--color-danger)", marginTop: 0 }}>{error}</p>
        <button
          onClick={refresh}
          style={{
            background: "var(--color-primary)",
            color: "var(--color-on-primary)",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-4)",
            cursor: "pointer",
          }}
        >
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  // Build list panel with header
  const listPanel = (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        height: "100%",
      }}
    >
      {/* UI concept ch. 12.2: search / filter / sort come from the shared
          ListToolbar instead of a hand-built input + select pair. The
          heading and the primary action moved up into the page-level
          <PageHeader> (ch. 12.1) — a toolbar carries no primary action.
          The status filter is now `arch-filter-status` (was
          `arch-status-filter`); it is not referenced by any e2e spec. */}
      <div style={{ marginBottom: 'var(--space-3)' }}>
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
          testId="arch-new-dialog"
        >
        <form
          onSubmit={(e) => { e.preventDefault(); void handleInlineCreate(); }}
          style={{
            display: 'flex', flexDirection: 'column', gap: 'var(--space-2)',
            padding: 'var(--space-3)', marginBottom: 'var(--space-3)',
            background: 'var(--color-surface-raised)',
            border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)',
          }}
        >
          <label style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, color: 'var(--color-text)' }}>
            {t('editor.title', 'Title')}
          </label>
          <input
            data-testid="arch-new-title-input"
            ref={newTitleInputRef}
            type="text" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} autoFocus
            placeholder={t('arch.newElementTitle')}
            style={{
              padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)', fontSize: 'var(--font-size-sm)',
              background: 'var(--color-surface)', color: 'var(--color-text)',
            }}
          />
          {/* BUG-11: description — an ordinary architectureApi.create() field
              the backend already accepts, previously missing here. */}
          <label htmlFor="arch-new-description" className={fieldHints.createLabelInline}>
            {t('editor.description')}
          </label>
          <textarea
            id="arch-new-description"
            data-testid="arch-new-description-input"
            value={newDescription}
            onChange={(e) => setNewDescription(e.target.value)}
            rows={3}
            className={fieldHints.createInput}
          />

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
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
              disabled={!newTitle.trim()}
            >
              {t('actions.create', 'Erstellen')}
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
          onReparent: drag & drop moves an element under a new parent, or onto
          the root dropzone to detach it to L0. Reinstated on 2026-08-15,
          reversing the 2026-07-13 "won't do" note that stood here before. */}
      <div style={{ flex: 1, overflow: "auto" }}>
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
              { label: t('arch.newElement', 'New Architecture Element'), onClick: () => setShowCreateForm(true), testId: 'arch-tree-empty-create' },
            ]}
          />
        ) : archTreeNodes.length === 0 ? (
          <EmptyState
            variant="no-match"
            testId="arch-tree-no-match"
            onResetFilters={() => {
              setListSearch('');
              setStatusFilter('');
            }}
          />
        ) : (
          <WorkspaceTree
            data-testid="arch-tree"
            nodes={archTreeNodes}
            selectedId={selectedId}
            onSelect={selectElement}
            onAddChild={(parentId) => void handleCreate(parentId)}
            onReparent={(id, newParentId) => void handleReparent(id, newParentId)}
            rootDropzoneLabel={t('arch.tree.dropRoot', 'Drop here to make root (L0)')}
            showLevelBadge={true}
            showSearch={false}
            virtualize
          />
        )}
      </div>
    </div>
  );

  // Build detail panel (form + sidebar)
  const detailPanel = (
    <div
      style={{
        display: "flex",
        gap: "var(--space-6)",
        alignItems: "flex-start",
        padding: "var(--space-4)",
      }}
    >
      {element ? (
        <>
          {/* Main form wrapper */}
          <div
            style={{
              flex: 1,
              background: "var(--color-surface)",
              borderRadius: "var(--radius-lg)",
              boxShadow: "var(--shadow-card)",
              padding: "var(--space-6)",
            }}
          >
            {/* Trace spine — UI concept ch. 5 / ch. 12.10. Architecture is
                the pilot for it because its tree has a genuinely variable
                depth, which is exactly what the dynamic station count has
                to survive (ch. 5.1). */}
            <TraceSpine
              stations={derivationChain.stations}
              isLoading={derivationChain.isLoading}
              error={derivationChain.error}
              onOpenArtifact={handleOpenChainArtifact}
              isOpenable={isChainArtifactOpenable}
            />

            <EntityTypeProvider
              entityType="architecture_element"
              entitySubType={element.element_type}
              visibleFields={{
                asil_level: true,
                make_or_buy: true,
              }}
            >
              <ArchitectureForm
                key={element.id}
                element={element}
                elements={elements}
                onSaved={refresh}
                onDelete={(id) => void handleDelete(id)}
                isExtendedPreset={activeWorkspace?.preset === "extended"}
                onDecompose={() => setShowDecomposePanel(true)}
                onDirtyChange={setIsFormDirty}
              />
            </EntityTypeProvider>

            {/* TraceLink panel — carries the e2e test-id since the old
                placeholder aside ("See the Inspector sidebar") was removed:
                the linked-requirements management lives HERE, the read-only
                trace view lives in the ArtifactInspector. */}
            {(activeWorkspace?.id || element.workspace_id) && (
              <div data-testid="arch-linked-reqs-panel">
                <TraceLinkPanel
                  workspaceId={activeWorkspace?.id ?? element.workspace_id}
                  artifactId={element.id}
                />
              </div>
            )}

            {/* Derive requirement allocated to this element */}
            <div style={{ marginTop: "var(--space-4)" }}>
              <DeriveRequirementForm
                isOpen={showDeriveForm}
                onOpen={() => setShowDeriveForm(true)}
                onCancel={() => { setShowDeriveForm(false); setDeriveError(null); }}
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

          {/* New unified right sidebar (REQ-L2-RF-034). Trace-link display is
              now owned by the <TraceSpine> above (Task 3.3) — hideTraceLinks
              keeps the sidebar to versions/baselines only. */}
          <RightSidebar
            kind="architecture"
            artifactId={element.id}
            currentVersion={currentVersion}
            hideTraceLinks
          />
        </>
      ) : (
        <p style={{ color: "var(--color-text-muted)" }}>{t("arch.selectElement")}</p>
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
              setDecomposeHasPendingWork(false);
              setShowDecomposePanel(false);
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
          onConfirm={() => {
            setShowDecomposeCloseConfirm(false);
            setDecomposeHasPendingWork(false);
            setShowDecomposePanel(false);
          }}
          onCancel={() => setShowDecomposeCloseConfirm(false)}
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
          onClick: () => setShowCreateForm(true),
          disabled: showCreateForm,
          testId: "create-arch-btn",
        }}
        secondaryActions={[interviewCta]}
        overflowActions={[
          {
            label: t("archDecompose.trigger", "KI-Zerlegung"),
            onClick: () => setShowDecomposePanel(true),
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

      <SplitView
        leftPanel={listPanel}
        rightPanel={detailPanel}
        moduleType="architecture"
        leftMinWidth={250}
      />
    </>
  );
}
