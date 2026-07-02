/**
 * ArchitectureElementList — Extracted list component for architecture elements.
 *
 * REQ-L1-040 Phase 2 — Unified ModalDialogBase pattern.
 *
 * Manages CRUD operations for architecture elements using ModalDialogBase form.
 * Preserves deletion confirmation logic (ADR-L3-RF-008).
 */

import React, { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { architectureApi } from "../../api/architecture";
import { ModalDialogBase, SHARED_STYLES } from "../RequirementsList/ModalDialogBase";
import type { ArchitectureElement, ElementType } from "../../types";

interface ElementFormState {
  name: string;
  description: string;
  type: ElementType;
  parentId?: string;
  level?: number;
}

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
          background: "var(--color-surface)",
          padding: "var(--space-6)",
          borderRadius: "var(--radius-lg)",
          boxShadow: "var(--shadow-md)",
          maxWidth: "400px",
          textAlign: "center",
          fontFamily: "var(--font-sans)",
          color: "var(--color-text)",
        }}
      >
        <h3 style={{ margin: 0, marginBottom: "var(--space-3)", fontSize: "var(--font-size-lg)" }}>
          {t("arch.deleteTitle")}
        </h3>
        <p style={{ margin: 0, marginBottom: "var(--space-4)", color: "var(--color-text-muted)" }}>
          {t("arch.deleteConfirm")}: <strong style={{ color: "var(--color-text)" }}>{elementName}</strong>?
        </p>
        <div
          style={{
            display: "flex",
            gap: "var(--space-3)",
            justifyContent: "center",
            marginTop: "var(--space-4)",
          }}
        >
          <button
            data-testid="confirm-delete-btn"
            onClick={onConfirm}
            style={{
              background: "var(--color-danger)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: "pointer",
              transition: "var(--transition-fast)",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "#b91c1c";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "var(--color-danger)";
            }}
          >
            {t("actions.delete")}
          </button>
          <button
            onClick={onCancel}
            style={{
              background: "var(--color-surface-raised)",
              color: "var(--color-text)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: "pointer",
              transition: "var(--transition-fast)",
            }}
          >
            {t("actions.cancel")}
          </button>
        </div>
      </div>
    </div>
  );
}

const ELEMENT_TYPES: { value: ElementType; labelKey: string }[] = [
  { value: "component", labelKey: "arch.elementType.component" },
  { value: "interface", labelKey: "arch.elementType.interface" },
  { value: "subsystem", labelKey: "arch.elementType.subsystem" },
  { value: "layer", labelKey: "arch.elementType.layer" },
  { value: "module", labelKey: "arch.elementType.module" },
];

export function ArchitectureElementList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<ArchitectureElement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [elementToDelete, setElementToDelete] = useState<ArchitectureElement | null>(null);

  const [formData, setFormData] = useState<ElementFormState>({
    name: "",
    description: "",
    type: "component",
  });

  // Load elements list
  const loadList = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) {
      setItems([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const resp = await architectureApi.list(activeWorkspace.id);
      setItems(resp.results as ArchitectureElement[]);
    } catch (err: unknown) {
      const msg = (err as { error?: { message?: string } })?.error?.message ?? String(err);
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!cancelled) {
        await loadList();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadList]);

  const resetForm = useCallback((): void => {
    setFormData({ name: "", description: "", type: "component", level: undefined });
    setFormError(null);
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
      e.preventDefault();
      if (!activeWorkspace) return;

      if (!formData.name.trim()) {
        setFormError(t("editor.titleRequired"));
        return;
      }

      setIsSubmitting(true);
      setFormError(null);
      try {
        await architectureApi.create({
          workspace_id: activeWorkspace.id,
          title: formData.name.trim(),
          description: formData.description,
          element_type: formData.type,
          parent_id: formData.parentId || undefined,
        });
        setShowCreate(false);
        resetForm();
        await loadList();
      } catch (err: unknown) {
        const msg = (err as { error?: { message?: string } })?.error?.message ?? String(err);
        setFormError(msg);
      } finally {
        setIsSubmitting(false);
      }
    },
    [activeWorkspace, formData, t, resetForm, loadList]
  );

  const handleDelete = useCallback(
    (element: ArchitectureElement): void => {
      setElementToDelete(element);
      setShowDeleteDialog(true);
    },
    []
  );

  const handleConfirmDelete = useCallback(async (): Promise<void> => {
    if (!elementToDelete) return;
    setShowDeleteDialog(false);
    try {
      await architectureApi.delete(elementToDelete.id);
      await loadList();
    } catch (err: unknown) {
      console.error("Delete failed:", err);
    } finally {
      setElementToDelete(null);
    }
  }, [elementToDelete, loadList]);

  const handleCancel = useCallback((): void => {
    setShowCreate(false);
    resetForm();
  }, [resetForm]);

  if (isLoading) {
    return (
      <p role="status" style={{ color: "var(--color-text-muted)", padding: "var(--space-4)" }}>
        {t("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <div role="alert" style={{ color: "var(--color-danger)", padding: "var(--space-4)" }}>
        {error}
        <button onClick={loadList} style={SHARED_STYLES.primaryButton}>
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  return (
    <div>
      {showDeleteDialog && elementToDelete && (
        <DeleteConfirmationDialog
          elementName={elementToDelete.title || t("editor.untitled")}
          onConfirm={() => void handleConfirmDelete()}
          onCancel={() => {
            setShowDeleteDialog(false);
            setElementToDelete(null);
          }}
        />
      )}

      <ModalDialogBase
        title={t("nav.architecture")}
        isOpen={showCreate}
        onToggle={() => setShowCreate(!showCreate)}
        onSubmit={handleSubmit}
        onCancel={handleCancel}
        error={formError}
        isSubmitting={isSubmitting}
        itemCount={items.length}
        testIdPrefix="arch-element"
        buttonTestIdPrefix="arch-element"
      >
        <div>
          {!formData.level && (
            <p
              style={{
                fontSize: "var(--font-size-sm)",
                color: "var(--color-text-muted)",
                marginBottom: "var(--space-3)",
                fontStyle: "italic",
              }}
            >
              {t("arch.levelAutoCalculated")}
            </p>
          )}
          <label htmlFor="arch-element-name" style={SHARED_STYLES.label}>
            {t("editor.title")} *
          </label>
          <input
            id="arch-element-name"
            data-testid="arch-element-name"
            type="text"
            value={formData.name}
            onChange={(e) => setFormData((prev) => ({ ...prev, name: e.target.value }))}
            placeholder={t("editor.titlePlaceholder")}
            style={SHARED_STYLES.input}
            required
          />

          <label htmlFor="arch-element-type" style={SHARED_STYLES.label}>
            {t("arch.elementType")}
          </label>
          <select
            id="arch-element-type"
            data-testid="arch-element-type"
            value={formData.type}
            onChange={(e) => setFormData((prev) => ({ ...prev, type: e.target.value as ElementType }))}
            style={SHARED_STYLES.input}
          >
            {ELEMENT_TYPES.map((et) => (
              <option key={et.value} value={et.value}>
                {t(et.labelKey)}
              </option>
            ))}
          </select>

          {formData.level !== undefined && (
            <div style={{ marginTop: "var(--space-3)", marginBottom: "var(--space-3)" }}>
              <label style={SHARED_STYLES.label}>
                {t("arch.level")}
              </label>
              <div
                data-testid="arch-element-level"
                style={{
                  padding: "var(--space-2) var(--space-3)",
                  background: "var(--color-surface-raised)",
                  borderRadius: "var(--radius-md)",
                  color: "var(--color-text-muted)",
                  fontSize: "var(--font-size-sm)",
                }}
              >
                {formData.level} {t("arch.levelHint")}
              </div>
            </div>
          )}

          <label htmlFor="arch-element-description" style={SHARED_STYLES.label}>
            {t("editor.description")}
          </label>
          <textarea
            id="arch-element-description"
            data-testid="arch-element-description"
            value={formData.description}
            onChange={(e) => setFormData((prev) => ({ ...prev, description: e.target.value }))}
            placeholder={t("editor.descriptionPlaceholder")}
            style={{
              ...SHARED_STYLES.input,
              minHeight: "120px",
              fontFamily: "var(--font-sans)",
            }}
          />
        </div>
      </ModalDialogBase>

      {items.length === 0 && !showCreate ? (
        <p style={{ color: "var(--color-text-muted)", padding: "var(--space-6)" }}>
          {t("editor.empty")}
        </p>
      ) : (
        <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
          {items.map((element) => {
            const indentPx = (element.level ?? 0) * 24;
            return (
              <li
                key={element.id}
                data-testid="arch-element-item"
                style={{
                  background: "var(--color-surface)",
                  borderRadius: "var(--radius-md)",
                  boxShadow: "var(--shadow-card)",
                  padding: "var(--space-3) var(--space-4)",
                  marginBottom: "var(--space-2)",
                  marginLeft: `${indentPx}px`,
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  transition: "var(--transition-fast)",
                }}
                onMouseEnter={(e) => {
                  (e.currentTarget as HTMLLIElement).style.background = "var(--color-surface-raised)";
                }}
                onMouseLeave={(e) => {
                  (e.currentTarget as HTMLLIElement).style.background = "var(--color-surface)";
                }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-2)",
                      marginBottom: "var(--space-1)",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "var(--font-size-base)",
                        fontWeight: 600,
                        color: "var(--color-text)",
                        whiteSpace: "nowrap",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                      }}
                    >
                      {element.title || t("editor.untitled")}
                    </span>
                    <span
                      style={{
                        fontSize: "var(--font-size-sm)",
                        background: "var(--color-badge-draft)",
                        color: "var(--color-badge-draft-text)",
                        padding: "2px 8px",
                        borderRadius: "var(--radius-full)",
                        flexShrink: 0,
                      }}
                    >
                      {t(`arch.elementType.${element.element_type}`)}
                    </span>
                  </div>
                  {element.level !== undefined && (
                    <span
                      data-testid={`arch-element-level-${element.id}`}
                      style={{
                        fontSize: "var(--font-size-sm)",
                        color: "var(--color-text-muted)",
                      }}
                    >
                      {t("arch.level")}: <strong>{element.level}</strong>
                    </span>
                  )}
                </div>
                <button
                  data-testid={`delete-arch-element-${element.id}`}
                  onClick={() => handleDelete(element)}
                  style={{
                    background: "var(--color-danger)",
                    color: "white",
                    border: "none",
                    borderRadius: "var(--radius-md)",
                    padding: "var(--space-1) var(--space-3)",
                    fontSize: "var(--font-size-sm)",
                    cursor: "pointer",
                    transition: "var(--transition-fast)",
                    flexShrink: 0,
                  }}
                >
                  {t("actions.delete")}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export default ArchitectureElementList;
