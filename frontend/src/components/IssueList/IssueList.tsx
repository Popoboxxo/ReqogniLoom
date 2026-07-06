/**
 * ARCH-L1-001 ReactFrontend — Issue list view (COMP-RF-003).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-L1-029 (ADR/Risk/Issue REST API),
 *          REQ-002 (Masken-Standardisierung auf Split-View-Layout),
 *          REQ-L1-095 (ArtifactInspector adoption — 10 artifact types),
 *          REQ-L2-RF-034 (ArtifactInspector RightSidebar shell)
 *
 * Split-View layout with resizable divider:
 * - Left panel: Issue list with create button
 * - Divider: 4px resizable
 * - Middle panel: Issue detail editor
 * - Right panel (detail only): ArtifactInspector (Version / Diff / Trace).
 *   Note: Issue wire-format has no `version` field (see
 *   `frontend/src/types/index.ts:247`), so the inspector is mounted
 *   with `currentVersion={undefined}`; the VersionPanel will fetch
 *   history from the backend if/when a `/issues/<id>/versions/`
 *   endpoint is added.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { issuesApi } from "../../api/issues";
import { RightSidebar } from "../shared/ArtifactInspector";
import type { Issue, IssueSeverity, IssueStatus, IssueCategory } from "../../types";

const SEVERITY_OPTIONS: IssueSeverity[] = ["low", "medium", "high", "critical"];
const STATUS_OPTIONS: IssueStatus[] = ["Open", "In Progress", "Resolved", "Closed", "Wontfix"];
const CATEGORY_OPTIONS: IssueCategory[] = ["defect", "improvement", "documentation", "question"];

const inputStyle: React.CSSProperties = {
  width: "100%",
  fontSize: "var(--font-size-base)",
  padding: "var(--space-2) var(--space-3)",
  marginBottom: "var(--space-4)",
  boxSizing: "border-box",
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontFamily: "var(--font-sans)",
};

const labelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: "block",
  marginBottom: "var(--space-2)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const primaryButtonStyle: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "#ffffff",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
  transition: "var(--transition-fast)",
  fontFamily: "var(--font-sans)",
};

// ---------------------------------------------------------------------------
// IssueDetailEditor — right panel content
// ---------------------------------------------------------------------------

interface IssueDetailEditorProps {
  issue: Issue;
  onSaved: () => void;
}

function IssueDetailEditor({ issue, onSaved }: IssueDetailEditorProps): JSX.Element {
  const { t } = useTranslation();
  const [title, setTitle] = useState(issue.title);
  const [description, setDescription] = useState(issue.description ?? "");
  const [severity, setSeverity] = useState<IssueSeverity>(issue.severity ?? "medium");
  const [category, setCategory] = useState<IssueCategory>(issue.category ?? "defect");
  const [status, setStatus] = useState<IssueStatus>(issue.status ?? "Open");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const handleSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    try {
      await issuesApi.update(issue.id, {
        title: title.trim(),
        description: description.trim() || undefined,
        severity,
        category,
        status,
      });
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ?? String(err);
      setSaveError(msg);
    } finally {
      setIsSaving(false);
    }
  }, [issue.id, title, description, severity, category, status, onSaved]);

  const handleDelete = useCallback(async (): Promise<void> => {
    if (!window.confirm(t("editor.deleteConfirm"))) return;
    try {
      await issuesApi.delete(issue.id);
      onSaved();
    } catch (err: unknown) {
      console.error("Delete failed:", err);
    }
  }, [issue.id, t, onSaved]);

  return (
    <div style={{ padding: "var(--space-6)", overflow: "auto" }}>
      <h2 style={{ fontSize: "var(--font-size-xl)", fontWeight: 700, marginBottom: "var(--space-4)" }}>
        {issue.title || t("editor.untitled")}
      </h2>

      <div>
        <label htmlFor="issue-title" style={labelStyle}>
          {t("editor.title")} *
        </label>
        <input
          id="issue-title"
          data-testid="issue-title-input"
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          disabled={isSaving}
          style={inputStyle}
        />
      </div>

      <div>
        <label htmlFor="issue-description" style={labelStyle}>
          {t("editor.description")}
        </label>
        <textarea
          id="issue-description"
          data-testid="issue-description-input"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          disabled={isSaving}
          rows={4}
          style={{ ...inputStyle, fontFamily: "inherit", resize: "vertical" }}
        />
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "var(--space-3)",
          marginBottom: "var(--space-4)",
        }}
      >
        <div>
          <label htmlFor="issue-severity" style={labelStyle}>
            Severity
          </label>
          <select
            id="issue-severity"
            data-testid="issue-severity-select"
            value={severity}
            onChange={(e) => setSeverity(e.target.value as IssueSeverity)}
            disabled={isSaving}
            style={inputStyle}
          >
            {SEVERITY_OPTIONS.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor="issue-category" style={labelStyle}>
            Category
          </label>
          <select
            id="issue-category"
            data-testid="issue-category-select"
            value={category}
            onChange={(e) => setCategory(e.target.value as IssueCategory)}
            disabled={isSaving}
            style={inputStyle}
          >
            {CATEGORY_OPTIONS.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label htmlFor="issue-status" style={labelStyle}>
          Status
        </label>
        <select
          id="issue-status"
          data-testid="issue-status-select"
          value={status}
          onChange={(e) => setStatus(e.target.value as IssueStatus)}
          disabled={isSaving}
          style={inputStyle}
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
      </div>

      {saveError && (
        <p style={{ color: "var(--color-danger)", marginBottom: "var(--space-3)" }}>
          {saveError}
        </p>
      )}

      <div style={{ display: "flex", gap: "var(--space-2)" }}>
        <button
          data-testid="issue-save-btn"
          onClick={() => void handleSave()}
          disabled={isSaving}
          style={primaryButtonStyle}
        >
          {isSaving ? t("actions.saving") : t("actions.save")}
        </button>
        <button
          data-testid="issue-delete-btn"
          onClick={() => void handleDelete()}
          style={{
            background: "var(--color-danger)",
            color: "#ffffff",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-4)",
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            cursor: "pointer",
            transition: "var(--transition-fast)",
            fontFamily: "var(--font-sans)",
          }}
        >
          {t("actions.delete")}
        </button>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// IssueList — main view with split-pane
// ---------------------------------------------------------------------------

export default function IssueList(): JSX.Element {
  const { t } = useTranslation();
  const { id: selectedId } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Issue[]>([]);
  const [selectedIssue, setSelectedIssue] = useState<Issue | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Split-pane resize state
  const [leftPanelWidth, setLeftPanelWidth] = useState(280);
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);

  const loadList = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    setError(null);
    try {
      const resp = await issuesApi.list(activeWorkspace.id);
      setItems(resp.results);
      // Auto-select first item or navigate to selectedId if it exists
      if (selectedId) {
        const issue = resp.results.find((r) => r.id === selectedId);
        setSelectedIssue(issue || null);
      }
    } catch (err: unknown) {
      const msg = (err as { error?: { message?: string } })?.error?.message ?? String(err);
      setError(msg);
      console.error(err);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace, selectedId]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const handleCreate = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    try {
      const created = await issuesApi.create({
        workspace_id: activeWorkspace.id,
        title: t("editor.newRequirementTitle"),
        severity: "medium",
        status: "Open",
      });
      navigate(`/issues/${created.id}`);
    } catch (err: unknown) {
      console.error("Create failed:", err);
    }
  }, [activeWorkspace, t, navigate]);

  // Split-pane resize handlers
  const handleDividerMouseDown = (e: React.MouseEvent): void => {
    isDraggingRef.current = true;
    dragStartXRef.current = e.clientX;
    dragStartWidthRef.current = leftPanelWidth;
    document.body.style.userSelect = "none";
    document.body.style.cursor = "col-resize";
    e.preventDefault();
  };

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent): void => {
      if (!isDraggingRef.current) return;
      const delta = e.clientX - dragStartXRef.current;
      const newWidth = Math.max(280, dragStartWidthRef.current + delta);
      setLeftPanelWidth(newWidth);
    };

    const handleMouseUp = (): void => {
      if (!isDraggingRef.current) return;
      isDraggingRef.current = false;
      document.body.style.userSelect = "";
      document.body.style.cursor = "";
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, []);

  if (isLoading) {
    return <p role="status">{t("loading")}</p>;
  }

  if (error) {
    return (
      <div role="alert">
        <p style={{ color: "var(--color-danger)" }}>{error}</p>
        <button onClick={() => void loadList()}>{t("actions.reload")}</button>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", height: "100%", overflow: "hidden" }}>
      {/* Left panel: Issue list */}
      <div
        style={{
          width: `${leftPanelWidth}px`,
          minWidth: "280px",
          maxWidth: "70%",
          overflow: "auto",
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
            {t("nav.issues")}
          </h3>
          <button
            type="button"
            data-testid="create-issue-btn"
            onClick={() => void handleCreate()}
            style={primaryButtonStyle}
          >
            + {t("actions.new")}
          </button>
        </div>

        {items.length === 0 ? (
          <p style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
            {t("editor.empty")}
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {items.map((item) => {
              const isSelected = selectedIssue?.id === item.id;
              return (
                <li
                  key={item.id}
                  data-testid={`issue-item-${item.id}`}
                  onClick={() => {
                    setSelectedIssue(item);
                    navigate(`/issues/${item.id}`);
                  }}
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    marginBottom: "var(--space-2)",
                    background: isSelected ? "var(--color-surface-raised)" : "var(--color-surface)",
                    borderRadius: "var(--radius-md)",
                    border: isSelected ? "1px solid var(--color-primary)" : "1px solid var(--color-border)",
                    cursor: "pointer",
                    transition: "var(--transition-fast)",
                  }}
                >
                  <strong style={{ color: "var(--color-text)" }}>{item.title}</strong>
                  <br />
                  <span style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
                    {item.severity} | {item.status}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Divider for split-pane resize */}
      <div
        onMouseDown={handleDividerMouseDown}
        data-testid="issue-editor-divider"
        style={{
          width: "4px",
          backgroundColor: "var(--color-border)",
          cursor: "col-resize",
          userSelect: "none",
          transition: isDraggingRef.current ? "none" : "background-color var(--transition-fast)",
          flexShrink: 0,
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.backgroundColor = "var(--color-border-hover)";
        }}
        onMouseLeave={(e) => {
          if (!isDraggingRef.current) {
            (e.currentTarget as HTMLDivElement).style.backgroundColor = "var(--color-border)";
          }
        }}
      />

      {/* Right panel: Issue detail editor */}
      <div
        style={{
          flex: 1,
          overflow: "hidden",
          background: "var(--color-surface)",
        }}
      >
        {selectedIssue ? (
          <IssueDetailEditor issue={selectedIssue} onSaved={() => void loadList()} />
        ) : (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-lg)",
              padding: "var(--space-8)",
              textAlign: "center",
            }}
          >
            {t("issues.selectIssue")}
          </p>
        )}
      </div>

      {/* Right pane: ArtifactInspector (REQ-L1-095, REQ-L2-RF-034) */}
      {selectedIssue && (
        <RightSidebar
          kind="issue"
          artifactId={selectedIssue.id}
          currentVersion={undefined}
        />
      )}
    </div>
  );
}
