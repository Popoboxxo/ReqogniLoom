/**
 * ARCH-L1-001 ReactFrontend — RequirementEditors (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L2-RF-003 (Requirements-Editor mit Inline-Editing und Markdown),
 *          REQ-L3-RF003-001 (Inline-Editing — Title, Description, Category),
 *          REQ-L3-RF003-002 (Workflow-State-Anzeige + Transition),
 *          REQ-L3-RF003-003 (TraceabilityPanel),
 *          REQ-L3-RF003-004 (Editor-Performance < 500ms)
 *
 * Interfaces implemented:
 *   IF-RF-INT-001  ← NavigationShell activates this view
 *   IF-RF-INT-002  ← I18nService via useTranslation
 *   IF-RF-INT-003  ← artifact_id from URL params
 *   IF-RF-EXT-OUT-001 → GET/PATCH /api/v1/requirements/
 */

import React, { useState, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useRequirementData } from "./useRequirementData";
import { MarkdownPreview } from "./MarkdownPreview";
import { TraceabilityPanel } from "./TraceabilityPanel";
import { requirementsApi } from "../../api/requirements";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { Requirement } from "../../types";

// ---------------------------------------------------------------------------
// Workflow states (backend is source of truth, these are common values)
// ---------------------------------------------------------------------------

const WORKFLOW_STATES = ["draft", "review", "approved", "rejected", "deprecated"];

// ---------------------------------------------------------------------------
// Requirement detail editor
// ---------------------------------------------------------------------------

interface RequirementDetailEditorProps {
  requirement: Requirement;
  onSaved: () => void;
}

function RequirementDetailEditor({
  requirement,
  onSaved,
}: RequirementDetailEditorProps): JSX.Element {
  const { t } = useTranslation();
  const [title, setTitle] = useState(requirement.title);
  const [description, setDescription] = useState(requirement.description);
  const [category, setCategory] = useState(requirement.category);
  const [workflowState, setWorkflowState] = useState(requirement.status);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await requirementsApi.update(requirement.id, {
        title,
        description,
        category,
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
  }, [requirement.id, title, description, category, onSaved]);

  return (
    <div
      style={{
        display: "flex",
        gap: "1.5rem",
        alignItems: "flex-start",
      }}
    >
      {/* Main editor */}
      <div style={{ flex: 1 }}>
        <label htmlFor="req-title" style={{ fontWeight: "bold", display: "block" }}>
          {t("editor.title")}
        </label>
        <input
          id="req-title"
          data-testid="req-title"
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

        <label style={{ fontWeight: "bold", display: "block", marginBottom: "0.25rem" }}>
          {t("editor.description")}
        </label>
        <MarkdownPreview value={description} onChange={setDescription} />

        <label htmlFor="req-category" style={{ fontWeight: "bold", display: "block", marginTop: "1rem" }}>
          {t("editor.category")}
        </label>
        <input
          id="req-category"
          data-testid="req-category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          style={{
            padding: "0.4rem",
            marginBottom: "1rem",
            width: "200px",
          }}
        />

        {/* Workflow state (REQ-L3-RF003-002) */}
        <label htmlFor="req-workflow" style={{ fontWeight: "bold", display: "block" }}>
          {t("editor.workflowState")}
        </label>
        <select
          id="req-workflow"
          data-testid="req-workflow"
          value={workflowState}
          onChange={(e) => setWorkflowState(e.target.value)}
          style={{ padding: "0.4rem", marginBottom: "1rem" }}
        >
          {WORKFLOW_STATES.map((state) => (
            <option key={state} value={state}>
              {state}
            </option>
          ))}
        </select>

        {saveError && (
          <p role="alert" style={{ color: "red" }}>
            {saveError}
          </p>
        )}

        <div style={{ display: "flex", gap: "0.75rem" }}>
          <button
            data-testid="save-btn"
            onClick={() => void handleSave()}
            disabled={isSaving}
            style={{ padding: "0.5rem 1.5rem" }}
          >
            {isSaving ? t("actions.saving") : t("actions.save")}
          </button>
        </div>
      </div>

      {/* Traceability sidebar */}
      <TraceabilityPanel
        upstreamLinks={[]}
        downstreamLinks={[]}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// RequirementEditors — main view
// ---------------------------------------------------------------------------

export default function RequirementEditors(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace, terminologyLabel } = useWorkspace();
  const { requirements, requirement, isLoading, error, refresh } =
    useRequirementData(selectedId);

  const reqLabel = terminologyLabel("requirements");

  const handleCreate = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    try {
      const created = await requirementsApi.create({
        workspace_id: activeWorkspace.id,
        title: t("editor.newRequirementTitle"),
      });
      refresh();
      navigate(`/requirements/${created.id}`);
    } catch (err: unknown) {
      console.error("Create failed:", err);
    }
  }, [activeWorkspace, t, refresh, navigate]);

  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      if (!window.confirm(t("editor.deleteConfirm"))) return;
      try {
        await requirementsApi.delete(id);
        refresh();
        navigate("/requirements");
      } catch (err: unknown) {
        console.error("Delete failed:", err);
      }
    },
    [t, refresh, navigate]
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
      {/* Requirements list (left panel) */}
      <div style={{ minWidth: "240px", borderRight: "1px solid #ddd", paddingRight: "1rem" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "0.75rem",
          }}
        >
          <h3 style={{ margin: 0 }}>{reqLabel}</h3>
          <button
            data-testid="create-req-btn"
            onClick={() => void handleCreate()}
            style={{ fontSize: "0.85rem" }}
          >
            + {t("actions.new")}
          </button>
        </div>

        {requirements.length === 0 ? (
          <p style={{ color: "#888", fontSize: "0.85rem" }}>{t("editor.empty")}</p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {requirements.map((req) => (
              <li
                key={req.id}
                style={{
                  padding: "0.4rem 0.5rem",
                  cursor: "pointer",
                  borderRadius: "4px",
                  background: req.id === selectedId ? "#e8eef8" : "transparent",
                  display: "flex",
                  justifyContent: "space-between",
                  alignItems: "center",
                  marginBottom: "0.2rem",
                }}
              >
                <span
                  onClick={() => navigate(`/requirements/${req.id}`)}
                  style={{ flex: 1 }}
                >
                  {req.title || t("editor.untitled")}
                </span>
                <span
                  style={{
                    fontSize: "0.7rem",
                    background: "#ddd",
                    padding: "0.1rem 0.3rem",
                    borderRadius: "3px",
                    marginLeft: "0.5rem",
                  }}
                >
                  {req.status}
                </span>
                <button
                  onClick={() => void handleDelete(req.id)}
                  style={{ marginLeft: "0.5rem", fontSize: "0.75rem", cursor: "pointer" }}
                  title={t("actions.delete")}
                >
                  ×
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Detail editor (right panel) */}
      <div style={{ flex: 1 }}>
        {requirement ? (
          <>
            <h2>{requirement.title || t("editor.untitled")}</h2>
            <RequirementDetailEditor
              key={requirement.id}
              requirement={requirement}
              onSaved={refresh}
            />
          </>
        ) : (
          <p style={{ color: "#888" }}>{t("editor.selectRequirement")}</p>
        )}
      </div>
    </div>
  );
}
