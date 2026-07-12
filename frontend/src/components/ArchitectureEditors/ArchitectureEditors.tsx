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
import { ArchitectureList } from "./ArchitectureList";
import { ArchitectureForm } from "./ArchitectureForm";
import { TraceLinkPanel } from "../shared/TraceLinkPanel";
import { DeriveRequirementForm } from "../shared/DeriveRequirementForm";
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

// ---------------------------------------------------------------------------
// ArchitectureEditors — main view with SplitView integration
// ---------------------------------------------------------------------------

/**
 * ARCH-L1-001 ReactFrontend — ArchitectureEditors (COMP-RF-004).
 *
 * Refactored to use SplitView component (REQ-L1-084) for generic
 * split-panel layout. Extracts ArchitectureList (left) and
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

  // Delete-confirmation target from list context menu
  const [deleteTarget, setDeleteTarget] = useState<ArchitectureElement | null>(null);

  // "Ableiten": create a Requirement allocated to the selected element
  // (SE: Req --allocated-to--> ArchitectureElement).
  const [showDeriveForm, setShowDeriveForm] = useState(false);
  const [deriveTitle, setDeriveTitle] = useState("");
  const [isDeriving, setIsDeriving] = useState(false);
  const [deriveError, setDeriveError] = useState<string | null>(null);

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

  // Filter elements by search. Must be declared before any early return so
  // the hook order stays stable across renders (React hooks invariant).
  const filteredElements = useMemo(() => {
    if (!listSearch.trim()) return elements;
    const q = listSearch.trim().toLowerCase();
    return elements.filter((el) =>
      el.title.toLowerCase().includes(q) ||
      (el.uid && el.uid.toLowerCase().includes(q))
    );
  }, [elements, listSearch]);

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
      <div style={{ marginBottom: 'var(--space-3)' }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "var(--space-3)",
          }}
        >
          <h3
            style={{
              margin: 0,
              fontSize: "var(--font-size-lg)",
              fontWeight: 700,
              color: "var(--color-text)",
            }}
          >
            {t("nav.architecture")}
          </h3>
          <button
            data-testid="create-arch-btn"
            onClick={() => setShowCreateForm(true)}
            style={{
              background: "var(--color-primary)",
              color: "#ffffff",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            + {t("actions.new")}
          </button>
        </div>

        {/* Search input */}
        <input
          type="text"
          value={listSearch}
          onChange={(e) => setListSearch(e.target.value)}
          placeholder={t('editor.searchPlaceholder', 'Search...')}
          style={{
            width: "100%",
            padding: "var(--space-2) var(--space-3)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-border)",
            fontSize: "var(--font-size-sm)",
            background: "var(--color-surface)",
            color: "var(--color-text)",
            boxSizing: "border-box",
          }}
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
            type="text" value={newTitle} onChange={(e) => setNewTitle(e.target.value)} autoFocus
            placeholder={t('arch.newElementTitle')}
            style={{
              padding: 'var(--space-2) var(--space-3)', borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)', fontSize: 'var(--font-size-sm)',
              background: 'var(--color-surface)', color: 'var(--color-text)',
            }}
          />
          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 'var(--space-2)' }}>
            <button type="button" onClick={() => { setShowCreateForm(false); setNewTitle(''); }}
              style={{
                background: 'transparent', color: 'var(--color-text)', border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)', cursor: 'pointer',
              }}
            >{t('cancel', 'Cancel')}</button>
            <button type="submit" disabled={!newTitle.trim()}
              style={{
                background: 'var(--color-primary)', color: 'white', border: 'none',
                borderRadius: 'var(--radius-md)', padding: 'var(--space-2) var(--space-4)',
                fontSize: 'var(--font-size-sm)', cursor: 'pointer',
              }}
            >{t('create', 'Create')}</button>
          </div>
        </form>
      )}

      <div style={{ flex: 1, overflow: "auto" }}>
        <ArchitectureList
          elements={filteredElements}
          selectedId={selectedId}
          onSelect={(id) => navigate(`/architecture/${id}`)}
          onAddChild={(parentId) => void handleCreate(parentId)}
          onDelete={(el) => setDeleteTarget(el)}
          onReparent={() => refresh()}
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

          {/* New unified right sidebar (REQ-L2-RF-034). */}
          <RightSidebar
            kind="architecture"
            artifactId={element.id}
            currentVersion={currentVersion}
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
        <div
          role="dialog"
          aria-modal="true"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.4)",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: "var(--color-surface)",
              padding: "var(--space-6)",
              borderRadius: "var(--radius-lg)",
              boxShadow: "var(--shadow-md)",
              maxWidth: "400px",
              textAlign: "center",
            }}
          >
            <h3 style={{ margin: 0, marginBottom: "var(--space-3)" }}>
              {t("arch.deleteTitle")}
            </h3>
            <p style={{ margin: 0, marginBottom: "var(--space-4)" }}>
              {t("arch.deleteConfirm")}: <strong>{deleteTarget.title}</strong>?
            </p>
            <div style={{ display: "flex", gap: "var(--space-3)", justifyContent: "center" }}>
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
            </div>
          </div>
        </div>
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
