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
import type { Requirement, TraceLink } from "../../types";

// ---------------------------------------------------------------------------
// Workflow states (backend is source of truth, these are common values)
// ---------------------------------------------------------------------------

const WORKFLOW_STATES = ["draft", "review", "approved", "rejected", "deprecated"];

// ---------------------------------------------------------------------------
// Status badge color mapping
// ---------------------------------------------------------------------------

function getStatusBadgeStyle(status: string): React.CSSProperties {
  const base: React.CSSProperties = {
    borderRadius: "var(--radius-full)",
    fontSize: "var(--font-size-sm)",
    padding: "2px 8px",
    fontWeight: 500,
    whiteSpace: "nowrap",
  };
  switch (status) {
    case "approved":
      return { ...base, background: "var(--color-badge-approved)", color: "var(--color-badge-approved-text)" };
    case "review":
      return { ...base, background: "#bee3f8", color: "#2c5282" };
    case "rejected":
    case "deprecated":
      return { ...base, background: "#fed7d7", color: "#9b2c2c" };
    default:
      return { ...base, background: "var(--color-badge-draft)", color: "var(--color-badge-draft-text)" };
  }
}

// ---------------------------------------------------------------------------
// Requirement detail editor
// ---------------------------------------------------------------------------

interface RequirementDetailEditorProps {
  requirement: Requirement;
  upstreamLinks: TraceLink[];
  downstreamLinks: TraceLink[];
  onSaved: () => void;
}

function RequirementDetailEditor({
  requirement,
  upstreamLinks,
  downstreamLinks,
  onSaved,
}: RequirementDetailEditorProps): JSX.Element {
  const { t } = useTranslation();
  const [title, setTitle] = useState(requirement.title);
  const [description, setDescription] = useState(requirement.description);
  const [category, setCategory] = useState(requirement.category);
  const [workflowState, setWorkflowState] = useState(requirement.status);
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const inputStyle: React.CSSProperties = {
    width: "100%",
    border: "1px solid var(--color-border)",
    borderRadius: "var(--radius-md)",
    padding: "var(--space-3)",
    fontFamily: "var(--font-sans)",
    fontSize: "var(--font-size-base)",
    marginBottom: "var(--space-4)",
    color: "var(--color-text)",
    background: "var(--color-surface)",
    boxSizing: "border-box",
  };

  const labelStyle: React.CSSProperties = {
    fontWeight: 500,
    color: "var(--color-text)",
    display: "block",
    marginBottom: "var(--space-1)",
  };

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
        background: "var(--color-surface)",
        borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-card)",
        padding: "var(--space-6)",
        flex: 1,
        display: "flex",
        gap: "var(--space-6)",
        alignItems: "flex-start",
      }}
    >
      {/* Main editor */}
      <div style={{ flex: 1 }}>
        <h2
          style={{
            fontSize: "var(--font-size-xl)",
            fontWeight: 700,
            marginBottom: "var(--space-4)",
            color: "var(--color-text)",
            marginTop: 0,
          }}
        >
          {requirement.title || t("editor.untitled")}
        </h2>

        <label htmlFor="req-title" style={labelStyle}>
          {t("editor.title")}
        </label>
        <input
          id="req-title"
          data-testid="req-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={inputStyle}
        />

        <label style={{ ...labelStyle, marginBottom: "var(--space-1)" }}>
          {t("editor.description")}
        </label>
        <MarkdownPreview value={description} onChange={setDescription} />

        <label htmlFor="req-category" style={{ ...labelStyle, marginTop: "var(--space-4)" }}>
          {t("editor.category")}
        </label>
        <input
          id="req-category"
          data-testid="req-category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          style={inputStyle}
        />

        {/* Workflow state (REQ-L3-RF003-002) */}
        <label htmlFor="req-workflow" style={labelStyle}>
          {t("editor.workflowState")}
        </label>
        <select
          id="req-workflow"
          data-testid="req-workflow"
          value={workflowState}
          onChange={(e) => setWorkflowState(e.target.value)}
          style={inputStyle}
        >
          {WORKFLOW_STATES.map((state) => (
            <option key={state} value={state}>
              {state}
            </option>
          ))}
        </select>

        {saveError && (
          <p role="alert" style={{ color: "var(--color-danger)" }}>
            {saveError}
          </p>
        )}

        <div style={{ display: "flex", gap: "var(--space-3)" }}>
          <SaveButton
            data-testid="save-btn"
            onClick={() => void handleSave()}
            disabled={isSaving}
            padding="var(--space-2) var(--space-6)"
          >
            {isSaving ? t("actions.saving") : t("actions.save")}
          </SaveButton>
        </div>
      </div>

      {/* Traceability sidebar (REQ-L3-RF003-003) */}
      <TraceabilityPanel
        upstreamLinks={upstreamLinks}
        downstreamLinks={downstreamLinks}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared primary button with hover state
// ---------------------------------------------------------------------------

interface PrimaryButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  padding?: string;
}

function SaveButton({ padding = "var(--space-2) var(--space-4)", style, children, ...props }: PrimaryButtonProps): JSX.Element {
  const [hovered, setHovered] = useState(false);

  const buttonStyle: React.CSSProperties = {
    background: hovered ? "var(--color-primary-dark)" : "var(--color-primary)",
    color: "white",
    border: "none",
    borderRadius: "var(--radius-md)",
    padding,
    fontSize: "var(--font-size-sm)",
    cursor: props.disabled ? "not-allowed" : "pointer",
    opacity: props.disabled ? 0.7 : 1,
    transition: "var(--transition-fast)",
    ...style,
  };

  return (
    <button
      {...props}
      style={buttonStyle}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {children}
    </button>
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
  const { requirements, requirement, upstreamLinks, downstreamLinks, isLoading, error, refresh } =
    useRequirementData(selectedId);

  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [newBtnHovered, setNewBtnHovered] = useState(false);

  const reqLabel = terminologyLabel("requirements");

  const handleCreate = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    try {
      const created = await requirementsApi.create({
        workspace_id: activeWorkspace.id,
        title: t("editor.newRequirementTitle"),
      });
      // Navigate first — the hook re-fetches automatically when selectedId changes.
      // Calling refresh() here would cause a double-fetch race where the first
      // fetch runs with the old selectedId and may overwrite state set by the
      // second fetch that already has the correct ID.
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
        <p style={{ color: "var(--color-danger)" }}>{error}</p>
        <button onClick={refresh}>{t("actions.reload")}</button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: "var(--space-6)" }}>
      {/* Requirements list (left panel) */}
      <div
        style={{
          minWidth: "260px",
          borderRight: "1px solid var(--color-border)",
          paddingRight: "var(--space-4)",
        }}
      >
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
              fontSize: "var(--font-size-lg)",
              fontWeight: 600,
              margin: 0,
              color: "var(--color-text)",
            }}
          >
            {reqLabel}
          </h3>
          <button
            data-testid="create-req-btn"
            onClick={() => void handleCreate()}
            onMouseEnter={() => setNewBtnHovered(true)}
            onMouseLeave={() => setNewBtnHovered(false)}
            style={{
              background: newBtnHovered ? "var(--color-primary-dark)" : "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              cursor: "pointer",
              transition: "var(--transition-fast)",
            }}
          >
            + {t("actions.new")}
          </button>
        </div>

        {requirements.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
            {t("editor.empty")}
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {requirements.map((req) => {
              const isActive = req.id === selectedId;
              const isHovered = hoveredId === req.id;

              const cardStyle: React.CSSProperties = {
                background: isActive
                  ? "#eef2ff"
                  : isHovered
                  ? "var(--color-surface-raised)"
                  : "var(--color-surface)",
                borderRadius: "var(--radius-md)",
                boxShadow: isHovered ? "var(--shadow-sm)" : "var(--shadow-card)",
                padding: "var(--space-3) var(--space-4)",
                marginBottom: "var(--space-2)",
                cursor: "pointer",
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                borderLeft: isActive ? "3px solid var(--color-primary)" : "3px solid transparent",
                transition: "var(--transition-fast)",
              };

              return (
                <li
                  key={req.id}
                  style={cardStyle}
                  onMouseEnter={() => setHoveredId(req.id)}
                  onMouseLeave={() => setHoveredId(null)}
                >
                  <span
                    onClick={() => navigate(`/requirements/${req.id}`)}
                    style={{ flex: 1, fontSize: "var(--font-size-base)", color: "var(--color-text)" }}
                  >
                    {req.title || t("editor.untitled")}
                  </span>
                  <span style={getStatusBadgeStyle(req.status)}>
                    {req.status}
                  </span>
                  <button
                    onClick={() => void handleDelete(req.id)}
                    style={{
                      marginLeft: "var(--space-2)",
                      fontSize: "var(--font-size-base)",
                      cursor: "pointer",
                      background: "none",
                      border: "none",
                      color: "var(--color-text-muted)",
                      lineHeight: 1,
                    }}
                    title={t("actions.delete")}
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Detail editor (right panel) */}
      <div style={{ flex: 1 }}>
        {requirement ? (
          <RequirementDetailEditor
            key={requirement.id}
            requirement={requirement}
            upstreamLinks={upstreamLinks}
            downstreamLinks={downstreamLinks}
            onSaved={refresh}
          />
        ) : (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-lg)",
              textAlign: "center",
              padding: "var(--space-8)",
            }}
          >
            {t("editor.selectRequirement")}
          </p>
        )}
      </div>
    </div>
  );
}
