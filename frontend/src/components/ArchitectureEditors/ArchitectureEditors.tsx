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

import React, { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useArchitectureData } from "./useArchitectureData";
import { MarkdownPreview } from "../RequirementEditors/MarkdownPreview";
import { architectureApi } from "../../api/architecture";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { ArchitectureElement, ElementType } from "../../types";

// ---------------------------------------------------------------------------
// Element type options (REQ-L3-RF004-001, ADR-L3-RF-007)
// ---------------------------------------------------------------------------

const ELEMENT_TYPES: { value: ElementType; label: string }[] = [
  { value: "component", label: "Component" },
  { value: "interface", label: "Interface" },
  { value: "subsystem", label: "Subsystem" },
  { value: "layer", label: "Layer" },
  { value: "module", label: "Module" },
];

// ---------------------------------------------------------------------------
// Delete Confirmation Dialog (ADR-L3-RF-008)
// ---------------------------------------------------------------------------

interface DeleteConfirmationDialogProps {
  elementName: string;
  onConfirm: () => void;
  onCancel: () => void;
}

function DeleteConfirmationDialog({
  elementName,
  onConfirm,
  onCancel,
}: DeleteConfirmationDialogProps): JSX.Element {
  const { t } = useTranslation();
  return (
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
          background: "#fff",
          padding: "2rem",
          borderRadius: "8px",
          maxWidth: "400px",
          textAlign: "center",
        }}
      >
        <h3>{t("arch.deleteTitle")}</h3>
        <p>
          {t("arch.deleteConfirm")}: <strong>{elementName}</strong>?
        </p>
        <div style={{ display: "flex", gap: "1rem", justifyContent: "center", marginTop: "1rem" }}>
          <button
            data-testid="confirm-delete-btn"
            onClick={onConfirm}
            style={{ padding: "0.5rem 1.5rem", background: "#cc0000", color: "#fff", border: "none", borderRadius: "4px", cursor: "pointer" }}
          >
            {t("actions.delete")}
          </button>
          <button
            onClick={onCancel}
            style={{ padding: "0.5rem 1.5rem", cursor: "pointer" }}
          >
            {t("actions.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Architecture Element Form
// ---------------------------------------------------------------------------

interface ArchElementFormProps {
  element: ArchitectureElement;
  onSaved: () => void;
  onDelete: (id: string) => void;
}

function ArchElementForm({
  element,
  onSaved,
  onDelete,
}: ArchElementFormProps): JSX.Element {
  const { t } = useTranslation();
  const [title, setTitle] = useState(element.title);
  const [description, setDescription] = useState(element.description);
  const [elementType, setElementType] = useState(element.element_type);
  const [isSaving, setIsSaving] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await architectureApi.update(element.id, {
        title,
        description,
        element_type: elementType,
      });
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setSaveError(msg);
    } finally {
      setIsSaving(false);
    }
  }, [element.id, title, description, elementType, onSaved]);

  const handleConfirmDelete = useCallback(async (): Promise<void> => {
    setShowDeleteDialog(false);
    onDelete(element.id);
  }, [element.id, onDelete]);

  return (
    <div>
      {showDeleteDialog && (
        <DeleteConfirmationDialog
          elementName={title}
          onConfirm={() => void handleConfirmDelete()}
          onCancel={() => setShowDeleteDialog(false)}
        />
      )}

      <label htmlFor="arch-title" style={{ fontWeight: "bold", display: "block" }}>
        {t("editor.title")}
      </label>
      <input
        id="arch-title"
        data-testid="arch-title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        style={{
          width: "100%",
          fontSize: "1.1rem",
          padding: "0.4rem",
          marginBottom: "1rem",
          boxSizing: "border-box",
        }}
      />

      {/* Element type dropdown (REQ-L3-RF004-001, ADR-L3-RF-007) */}
      <label htmlFor="arch-type" style={{ fontWeight: "bold", display: "block" }}>
        {t("arch.elementType")}
      </label>
      <select
        id="arch-type"
        data-testid="arch-element-type"
        value={elementType}
        onChange={(e) => setElementType(e.target.value)}
        style={{ padding: "0.4rem", marginBottom: "1rem" }}
      >
        {ELEMENT_TYPES.map((et) => (
          <option key={et.value} value={et.value}>
            {et.label}
          </option>
        ))}
      </select>

      {/* Markdown description (REQ-L3-RF004-002) */}
      <label style={{ fontWeight: "bold", display: "block", marginBottom: "0.25rem" }}>
        {t("editor.description")}
      </label>
      <MarkdownPreview
        value={description}
        onChange={setDescription}
      />

      {saveError && (
        <p role="alert" style={{ color: "red", marginTop: "0.5rem" }}>
          {saveError}
        </p>
      )}

      <div
        style={{
          display: "flex",
          gap: "0.75rem",
          marginTop: "1rem",
        }}
      >
        <button
          data-testid="arch-save-btn"
          onClick={() => void handleSave()}
          disabled={isSaving}
          style={{ padding: "0.5rem 1.5rem" }}
        >
          {isSaving ? t("actions.saving") : t("actions.save")}
        </button>
        <button
          data-testid="arch-delete-btn"
          onClick={() => setShowDeleteDialog(true)}
          style={{
            padding: "0.5rem 1rem",
            background: "#fee",
            border: "1px solid #fcc",
            cursor: "pointer",
            borderRadius: "4px",
          }}
        >
          {t("actions.delete")}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ArchitectureEditors — main view
// ---------------------------------------------------------------------------

export default function ArchitectureEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { elements, element, linkedTraceLinks, isLoading, error, refresh } =
    useArchitectureData(selectedId);

  const handleCreate = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    try {
      const created = await architectureApi.create({
        workspace_id: activeWorkspace.id,
        title: t("arch.newElementTitle"),
        element_type: "component",
      });
      refresh();
      navigate(`/architecture/${created.id}`);
    } catch (err: unknown) {
      console.error("Create failed:", err);
    }
  }, [activeWorkspace, t, refresh, navigate]);

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
    return <p role="status">{t("loading")}</p>;
  }

  if (error) {
    return (
      <div role="alert">
        <p style={{ color: "red" }}>{error}</p>
        <button onClick={refresh}>{t("actions.reload")}</button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: "1.5rem" }}>
      {/* Elements list */}
      <div style={{ minWidth: "240px", borderRight: "1px solid #ddd", paddingRight: "1rem" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "0.75rem",
          }}
        >
          <h3 style={{ margin: 0 }}>{t("nav.architecture")}</h3>
          <button
            data-testid="create-arch-btn"
            onClick={() => void handleCreate()}
            style={{ fontSize: "0.85rem" }}
          >
            + {t("actions.new")}
          </button>
        </div>

        {elements.length === 0 ? (
          <p style={{ color: "#888", fontSize: "0.85rem" }}>{t("editor.empty")}</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {elements.map((el) => (
              <li
                key={el.id}
                style={{
                  padding: "0.4rem 0.5rem",
                  cursor: "pointer",
                  borderRadius: "4px",
                  background: el.id === selectedId ? "#e8eef8" : "transparent",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "0.2rem",
                }}
                onClick={() => navigate(`/architecture/${el.id}`)}
              >
                <span style={{ flex: 1 }}>{el.title || t("editor.untitled")}</span>
                <span
                  style={{
                    fontSize: "0.7rem",
                    background: "#ddd",
                    padding: "0.1rem 0.3rem",
                    borderRadius: "3px",
                    marginLeft: "0.5rem",
                  }}
                >
                  {el.element_type}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Detail editor */}
      <div style={{ flex: 1 }}>
        {element ? (
          <div style={{ display: "flex", gap: "1.5rem", alignItems: "flex-start" }}>
            {/* Main form */}
            <div style={{ flex: 1 }}>
              <h2>{element.title || t("editor.untitled")}</h2>
              <ArchElementForm
                key={element.id}
                element={element}
                onSaved={refresh}
                onDelete={(id) => void handleDelete(id)}
              />
            </div>

            {/* Linked requirements sidebar (REQ-L3-RF004-003) */}
            <aside
              style={{
                borderLeft: "1px solid #ddd",
                paddingLeft: "1rem",
                minWidth: "200px",
              }}
            >
              <h4 style={{ margin: "0 0 0.5rem" }}>
                {t("arch.linkedRequirements")}
              </h4>
              {linkedTraceLinks.length === 0 ? (
                <p style={{ fontSize: "0.85rem", color: "#888" }}>
                  {t("traceability.none")}
                </p>
              ) : (
                <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
                  {linkedTraceLinks.map((link) => (
                    <li
                      key={link.id}
                      style={{
                        padding: "0.3rem 0",
                        borderBottom: "1px solid #eee",
                        fontSize: "0.85rem",
                        cursor: "pointer",
                      }}
                      onClick={() =>
                        navigate(`/requirements/${link.source_id}`)
                      }
                    >
                      {link.source_id.slice(0, 8)}… ({link.link_type})
                    </li>
                  ))}
                </ul>
              )}
            </aside>
          </div>
        ) : (
          <p style={{ color: "#888" }}>{t("arch.selectElement")}</p>
        )}
      </div>
    </div>
  );
}
