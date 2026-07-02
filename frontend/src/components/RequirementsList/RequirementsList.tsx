/**
 * ARCH-L1-001 ReactFrontend — RequirementsList (REQ-L1-040 Phase 2).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-040 (SE Masks Unification — ModalDialogBase adoption),
 *          REQ-L2-RF-003 (Requirements-Editor — list entry point)
 *
 * Standalone list view for requirements built on ModalDialogBase:
 *   - Loads all requirements of the active workspace
 *   - Table: title | category | workflow state | version | actions
 *   - Create modal (title, description, category) via ModalDialogBase
 *   - Edit action navigates to RequirementEditors (/requirements/:id) —
 *     the detail editor is NOT modified and keeps its public interface.
 *
 * Contract note: the registered requirements contract
 * (requirementsApi.create → POST /api/v1/requirements/) accepts
 * workspace_id, title, description, category. Level/priority/parent
 * fields are not part of the registered contract and are therefore
 * intentionally NOT rendered here (no unilateral interface extension).
 *
 * Interfaces implemented:
 *   IF-RF-INT-002 ← I18nService via useTranslation
 *   IF-RF-EXT-OUT-001 → GET/POST/DELETE /api/v1/requirements/
 */

import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useWorkspace } from "../../context/WorkspaceContext";
import { requirementsApi } from "../../api/requirements";
import ModalDialogBase, { SHARED_STYLES } from "./ModalDialogBase";
import type { Requirement } from "../../types";
import { REQ_CATEGORIES } from "../../types";

function extractErrorMessage(err: unknown, fallback: string): string {
  const e = err as { error?: { message?: string } };
  return e?.error?.message ?? (err ? String(err) : fallback);
}

const cellStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  borderBottom: "1px solid var(--color-border)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  textAlign: "left",
  verticalAlign: "middle",
};

const headerCellStyle: React.CSSProperties = {
  ...cellStyle,
  fontWeight: 600,
  color: "var(--color-text-muted)",
  textTransform: "uppercase",
  fontSize: "var(--font-size-xs)",
  letterSpacing: "0.05em",
};

export default function RequirementsList(): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();

  const [items, setItems] = useState<Requirement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [showCreate, setShowCreate] = useState(false);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [category, setCategory] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const loadList = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) {
      setItems([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setLoadError(null);
    try {
      const resp = await requirementsApi.list(activeWorkspace.id);
      setItems(resp.results);
    } catch (err) {
      setLoadError(extractErrorMessage(err, t("editor.empty")));
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace, t]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const resetForm = (): void => {
    setTitle("");
    setDescription("");
    setCategory("");
    setFormError(null);
  };

  const closeCreate = (): void => {
    resetForm();
    setShowCreate(false);
  };

  const handleSubmit = async (
    e: React.FormEvent<HTMLFormElement>
  ): Promise<void> => {
    e.preventDefault();
    if (!activeWorkspace) return;
    if (!title.trim()) {
      setFormError(t("editor.title") + " *");
      return;
    }
    setIsSubmitting(true);
    setFormError(null);
    try {
      await requirementsApi.create({
        workspace_id: activeWorkspace.id,
        title: title.trim(),
        description: description.trim() || undefined,
        category: category || undefined,
      });
      closeCreate();
      await loadList();
    } catch (err) {
      setFormError(extractErrorMessage(err, String(err)));
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (id: string): Promise<void> => {
    if (!window.confirm(t("editor.deleteConfirm"))) return;
    try {
      await requirementsApi.delete(id);
      await loadList();
    } catch (err) {
      setLoadError(extractErrorMessage(err, String(err)));
    }
  };

  const handleEdit = (id: string): void => {
    // Detail view is handled by RequirementEditors — navigation only,
    // its public interface stays untouched.
    navigate(`/requirements/${id}`);
  };

  if (isLoading) {
    return (
      <p role="status" style={{ color: "var(--color-text-muted)" }}>
        {t("loading")}
      </p>
    );
  }

  if (loadError) {
    return (
      <div role="alert">
        <p style={{ color: "var(--color-danger)" }}>{loadError}</p>
        <button
          type="button"
          onClick={() => void loadList()}
          style={SHARED_STYLES.primaryButton}
        >
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  return (
    <>
      <ModalDialogBase
        title={t("nav.requirements")}
        isOpen={showCreate}
        onToggle={() => {
          if (showCreate) closeCreate();
          else setShowCreate(true);
        }}
        onSubmit={handleSubmit}
        onCancel={closeCreate}
        error={formError}
        isSubmitting={isSubmitting}
        itemCount={items.length}
        testIdPrefix="req-list"
        buttonTestIdPrefix="req-list"
      >
        <div>
          <label htmlFor="req-list-title" style={SHARED_STYLES.label}>
            {t("editor.title")} *
          </label>
          <input
            id="req-list-title"
            data-testid="req-list-title-input"
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            autoFocus
            disabled={isSubmitting}
            placeholder={t("editor.newRequirementTitle")}
            style={SHARED_STYLES.input}
          />
        </div>
        <div>
          <label htmlFor="req-list-description" style={SHARED_STYLES.label}>
            {t("editor.description")}
          </label>
          <textarea
            id="req-list-description"
            data-testid="req-list-description-input"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            disabled={isSubmitting}
            rows={3}
            placeholder={t("editor.descriptionPlaceholder")}
            style={{
              ...SHARED_STYLES.input,
              fontFamily: "inherit",
              resize: "vertical",
            }}
          />
        </div>
        <div>
          <label htmlFor="req-list-category" style={SHARED_STYLES.label}>
            {t("editor.category")}
          </label>
          <select
            id="req-list-category"
            data-testid="req-list-category-select"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            disabled={isSubmitting}
            style={SHARED_STYLES.input}
          >
            <option value="">-- {t("editor.categoryPlaceholder")} --</option>
            {REQ_CATEGORIES.map((cat) => (
              <option key={cat} value={cat}>
                {t(`categories.${cat}`)}
              </option>
            ))}
          </select>
        </div>
      </ModalDialogBase>

      {/* Requirements table (rendered outside modal) */}
      {items.length > 0 && (
        <table
          data-testid="req-list-table"
          style={{
            width: "100%",
            borderCollapse: "collapse",
            background: "var(--color-surface)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-border)",
          }}
        >
          <thead>
            <tr>
              <th style={headerCellStyle}>{t("editor.title")}</th>
              <th style={headerCellStyle}>{t("editor.category")}</th>
              <th style={headerCellStyle}>{t("editor.workflowState")}</th>
              <th style={headerCellStyle}>v</th>
              <th style={headerCellStyle} />
            </tr>
          </thead>
          <tbody>
            {items.map((req) => (
              <tr key={req.id} data-testid={`req-list-item-${req.id}`}>
                <td style={cellStyle}>
                  {req.title || t("editor.untitled")}
                </td>
                <td style={cellStyle}>
                  {req.category ? t(`categories.${req.category}`) : "—"}
                </td>
                <td style={cellStyle}>{req.status}</td>
                <td style={cellStyle}>{req.version}</td>
                <td style={{ ...cellStyle, whiteSpace: "nowrap" }}>
                  <button
                    type="button"
                    data-testid={`req-list-edit-${req.id}`}
                    onClick={() => handleEdit(req.id)}
                    style={{
                      background: "var(--color-surface)",
                      color: "var(--color-primary)",
                      border: "1px solid var(--color-border)",
                      borderRadius: "var(--radius-md)",
                      padding: "var(--space-1) var(--space-3)",
                      fontSize: "var(--font-size-sm)",
                      cursor: "pointer",
                      marginRight: "var(--space-2)",
                    }}
                  >
                    {t("editor.editMode")}
                  </button>
                  <button
                    type="button"
                    data-testid={`req-list-delete-${req.id}`}
                    onClick={() => void handleDelete(req.id)}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--color-danger)",
                      cursor: "pointer",
                      fontSize: "var(--font-size-sm)",
                      fontWeight: 600,
                    }}
                    title={t("actions.delete")}
                  >
                    ×
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
