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

import React, { useState, useCallback, useEffect, useMemo } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useArchitectureData } from "./useArchitectureData";
import { SplitView } from "../SplitView/SplitView";
import { ArchitectureList } from "./ArchitectureList";
import { ArchitectureForm } from "./ArchitectureForm";
import { ArchTraceLinkPanel } from "./ArchTraceLinkPanel";
import { EntityTypeProvider } from "../../context/EntityTypeContext";
import { architectureApi } from "../../api/architecture";
import { extractErrorMessage } from "../../api/client";
import { useWorkspace } from "../../context/WorkspaceContext";
import type {
  ArchitectureElement,
} from "../../types";

// (Style helpers and dialog moved to ArchitectureForm component)

// ---------------------------------------------------------------------------
// ArchTraceLinkPanel has been extracted to ./ArchTraceLinkPanel.tsx (Fix B-TR-001).
// ---------------------------------------------------------------------------

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
  const { elements, element, linkedTraceLinks, isLoading, error, refresh } =
    useArchitectureData(selectedId);

  // Delete-confirmation target from list context menu
  const [deleteTarget, setDeleteTarget] = useState<ArchitectureElement | null>(null);

  const handleCreate = useCallback(
    async (parentId?: string): Promise<void> => {
      if (!activeWorkspace) return;
      try {
        const created = await architectureApi.create({
          workspace_id: activeWorkspace.id,
          title: t("arch.newElementTitle"),
          element_type: "component",
          parent_id: parentId ?? undefined,
        });
        refresh();
        navigate(`/architecture/${created.id}`);
      } catch (err: unknown) {
        console.error("Create failed:", err);
      }
    },
    [activeWorkspace, t, refresh, navigate]
  );

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
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "var(--space-4)",
          paddingBottom: "var(--space-3)",
          borderBottom: "1px solid var(--color-border)",
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
          onClick={() => void handleCreate()}
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

      <div style={{ flex: 1, overflow: "auto" }}>
        <ArchitectureList
          elements={elements}
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

            {/* TraceLink panel */}
            {(activeWorkspace?.id || element.workspace_id) && (
              <ArchTraceLinkPanel
                workspaceId={activeWorkspace?.id ?? element.workspace_id}
                elementId={element.id}
              />
            )}
          </div>

          {/* Linked requirements sidebar */}
          <aside
            data-testid="arch-linked-reqs-panel"
            style={{
              minWidth: "240px",
              background: "var(--color-surface)",
              borderRadius: "var(--radius-lg)",
              boxShadow: "var(--shadow-card)",
              padding: "var(--space-4)",
            }}
          >
            <h4
              style={{
                margin: 0,
                marginBottom: "var(--space-3)",
                fontSize: "var(--font-size-base)",
                fontWeight: 700,
                color: "var(--color-text)",
              }}
            >
              {t("arch.linkedRequirements")}
            </h4>
            {linkedTraceLinks.length === 0 ? (
              <p
                style={{
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text-muted)",
                  margin: 0,
                }}
              >
                {t("traceability.none")}
              </p>
            ) : (
              <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                {linkedTraceLinks.map((link) => (
                  <li
                    key={link.id}
                    onClick={() => navigate(`/requirements/${link.source_id}`)}
                    style={{
                      padding: "var(--space-2) var(--space-3)",
                      marginBottom: "var(--space-2)",
                      background: "var(--color-surface-raised)",
                      borderRadius: "var(--radius-md)",
                      fontSize: "var(--font-size-sm)",
                      color: "var(--color-text)",
                      cursor: "pointer",
                      transition: "var(--transition-fast)",
                    }}
                    onMouseEnter={(e) => {
                      (e.currentTarget as HTMLLIElement).style.background = "#eef2ff";
                    }}
                    onMouseLeave={(e) => {
                      (e.currentTarget as HTMLLIElement).style.background =
                        "var(--color-surface-raised)";
                    }}
                  >
                    <span style={{ fontFamily: "monospace" }}>
                      {link.source_id.slice(0, 8)}…
                    </span>{" "}
                    <span
                      style={{
                        background: "var(--color-badge-draft)",
                        color: "var(--color-badge-draft-text)",
                        padding: "1px 6px",
                        borderRadius: "var(--radius-full)",
                        fontSize: "var(--font-size-sm)",
                        marginLeft: "var(--space-1)",
                      }}
                    >
                      {link.link_type}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </aside>
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
