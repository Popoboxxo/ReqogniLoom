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

import { useState, useCallback, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useArchitectureData } from "./useArchitectureData";
import { SplitView } from "../SplitView/SplitView";
import { WorkspaceTree } from "../shared/WorkspaceTree";
import type { WorkspaceTreeNode } from "../shared/WorkspaceTree";
import { PageHeader } from "../shared/PageHeader";
import { ListToolbar } from "../shared/ListToolbar";
import { TraceSpine, useDerivationChain } from "../shared/TraceSpine";
import type { ChainArtifact } from "../shared/TraceSpine";
import { ArchitectureForm } from "./ArchitectureForm";
import { ArchitectureLegend } from "./ArchitectureLegend";
import { Dialog } from "../shared/Dialog";
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
import { useWorkspace } from "../../context/WorkspaceContext";
import type {
  ArchitectureElement,
} from "../../types";

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
  const [listSearch, setListSearch] = useState('');
  // REQ-175: lifecycle-status filter. ArchitectureElement has no denormalized
  // workflow status, so we filter on the available lifecycle_status field.
  const [statusFilter, setStatusFilter] = useState('');

  // Delete-confirmation target from list context menu
  const [deleteTarget, setDeleteTarget] = useState<ArchitectureElement | null>(null);

  // "Ableiten": create a Requirement allocated to the selected element
  // (SE: Req --allocated-to--> ArchitectureElement).
  const [showDeriveForm, setShowDeriveForm] = useState(false);
  const [deriveTitle, setDeriveTitle] = useState("");
  const [isDeriving, setIsDeriving] = useState(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);

  // AI Decompose panel state
  const [showDecomposePanel, setShowDecomposePanel] = useState(false);

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
    async (parentId?: string, customTitle?: string): Promise<void> => {
      if (!activeWorkspace) return;
      try {
        const created = await architectureApi.create({
          workspace_id: activeWorkspace.id,
          title: customTitle || t("arch.newElementTitle"),
          element_type: "component",
          parent_id: parentId ?? undefined,
        });
        setShowCreateForm(false);
        setNewTitle('');
        refresh();
        navigate(`/architecture/${created.id}`);
      } catch (err: unknown) {
        console.error("Create failed:", err);
      }
    },
    [activeWorkspace, t, refresh, navigate]
  );

  const handleInlineCreate = useCallback(async () => {
    if (!newTitle.trim()) return;
    await handleCreate(undefined, newTitle.trim());
  }, [newTitle, handleCreate]);

  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      try {
        await architectureApi.delete(id);
        refresh();
        navigate("/architecture");
      } catch (err: unknown) {
        console.error("Delete failed:", err);
      }
    },
    [refresh, navigate]
  );

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
            color: "#ffffff",
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
              // denormalized workflow status, so this filters lifecycle_status.
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

      {/* Inline create form */}
      {showCreateForm && (
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
            type="text" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} autoFocus
            placeholder={t('arch.newElementTitle')}
            style={{
              padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)', fontSize: 'var(--font-size-sm)',
              background: 'var(--color-surface)', color: 'var(--color-text)',
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button data-testid="arch-new-cancel-btn" type="button" onClick={() => { setShowCreateForm(false); setNewTitle(''); }}
              style={{
                background: 'transparent', color: 'var(--color-text)', border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)', cursor: 'pointer',
              }}
            >{t('actions.cancel', 'Cancel')}</button>
            <button data-testid="arch-new-save-btn" type="submit" disabled={!newTitle.trim()}
              style={{
                background: 'var(--color-primary)', color: 'white', border: 'none',
                borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)', cursor: 'pointer',
              }}
            >{t('actions.create', 'Create')}</button>
          </div>
        </form>
      )}

      {/* WorkspaceTree — unified navigation panel (REQ-003).
          showLevelBadge shows L0-L4 colored badges per design doc §6.
          onAddChild surfaces the "+ child" button on each tree row.
          showSearch=false: search is handled by the input above.
          won't do: drag-and-drop reparenting — hierarchy view not needed (user decision 2026-07-13). */}
      <div style={{ flex: 1, overflow: "auto" }}>
        <WorkspaceTree
          data-testid="arch-tree"
          nodes={archTreeNodes}
          selectedId={selectedId}
          onSelect={(id) => navigate(`/architecture/${id}`)}
          onAddChild={(parentId) => void handleCreate(parentId)}
          showLevelBadge={true}
          showSearch={false}
          virtualize
          emptyLabel={t('editor.empty')}
          noMatchesLabel={t('editor.noMatches')}
        />
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
      {deleteTarget && (
        <Dialog
          title={t("arch.deleteTitle")}
          onClose={() => setDeleteTarget(null)}
          size="sm"
          testId="arch-delete-dialog"
          footer={
            <div style={{ display: "flex", gap: "var(--space-3)", justifyContent: "flex-end" }}>
              <button
                onClick={() => setDeleteTarget(null)}
                style={{
                  background: "var(--color-surface-raised)",
                  color: "var(--color-text)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  padding: "var(--space-2) var(--space-4)",
                  cursor: "pointer",
                }}
              >
                {t("actions.cancel")}
              </button>
              <button
                data-testid="confirm-delete-btn"
                onClick={() => {
                  setDeleteTarget(null);
                  void handleDelete(deleteTarget.id);
                }}
                style={{
                  background: "var(--color-danger)",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "var(--radius-md)",
                  padding: "var(--space-2) var(--space-4)",
                  cursor: "pointer",
                }}
              >
                {t("actions.delete")}
              </button>
            </div>
          }
        >
          <p style={{ margin: 0 }}>
            {t("arch.deleteConfirm")}: <strong>{deleteTarget.title}</strong>?
          </p>
        </Dialog>
      )}

      {showDecomposePanel && element && activeWorkspace && (
        <Dialog
          title={t("archDecompose.title")}
          description={element.title}
          onClose={() => setShowDecomposePanel(false)}
          size="lg"
          testId="arch-decompose-dialog"
        >
          <ArchitectureDecomposePanel
            workspaceId={activeWorkspace.id}
            element={{ id: element.id, title: element.title }}
            onCommitted={() => {
              setShowDecomposePanel(false);
              refresh();
            }}
          />
        </Dialog>
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
          issue #314: this is the only route combining `primaryAction` with
          `overflowActions`; constrain the wrapper to the available width so
          it can never push the header's flex row wider than the viewport. */}
      <div style={{ padding: "0 var(--space-4)", maxWidth: "100%", boxSizing: "border-box" }}>
        <PageHeader
          title={t("nav.architecture")}
          summary={archSummary}
          primaryAction={{
            // ch. 14.2: name the result, not the gesture.
            label: t("arch.newElement", "Neues Architekturelement"),
            onClick: () => setShowCreateForm(true),
            disabled: showCreateForm,
            testId: "create-arch-btn",
          }}
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
      </div>

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
