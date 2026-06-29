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

import React, { useState, useCallback, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useRequirementData } from "./useRequirementData";
import { MarkdownPreview } from "./MarkdownPreview";
import { TraceabilityPanel } from "./TraceabilityPanel";
import { ArtifactDiff } from "../ArtifactDiff/ArtifactDiff";
import { requirementsApi } from "../../api/requirements";
import { tracelinksApi } from "../../api/tracelinks";
import { workspacesApi } from "../../api/workspaces";
import { testcasesApi } from "../../api/testcases";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { Requirement, TraceLink, LinkType, UUID } from "../../types";
import type { TestCase } from "../../api/testcases";
import { REQ_CATEGORIES } from "../../types";

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
  requirements: Requirement[];
  workspaceId: UUID;
  onSaved: () => void;
}

function RequirementDetailEditor({
  requirement,
  upstreamLinks,
  downstreamLinks,
  requirements,
  workspaceId,
  onSaved,
}: RequirementDetailEditorProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [title, setTitle] = useState(requirement.title);
  const [description, setDescription] = useState(requirement.description);
  const [category, setCategory] = useState(requirement.category);
  const [workflowState, setWorkflowState] = useState(requirement.status);
  const [changeReason, setChangeReason] = useState(requirement.change_reason ?? "");
  const [isSaving, setIsSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);

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
        status: workflowState,
        change_reason: changeReason,
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
  }, [requirement.id, title, description, category, workflowState, changeReason, onSaved]);

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
        <select
          id="req-category"
          data-testid="req-category"
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          style={inputStyle}
        >
          <option value="">-- {t("editor.categoryPlaceholder")} --</option>
          {REQ_CATEGORIES.map((cat) => (
            <option key={cat} value={cat}>
              {t(`categories.${cat}`)}
            </option>
          ))}
        </select>

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

        {/* Change reason (REQ-L2-RF-012 Extended preset) */}
        {(activeWorkspace?.preset === "extended") && (
          <div>
            <label htmlFor="change-reason" style={labelStyle}>
              {t("req.changeReason")} <span style={{color: "var(--color-danger)"}}>*</span>
            </label>
            <textarea
              id="change-reason"
              data-testid="change-reason-input"
              value={changeReason}
              onChange={(e) => setChangeReason(e.target.value)}
              rows={2}
              style={{...inputStyle, resize: "vertical"}}
              placeholder={t("req.changeReasonPlaceholder")}
            />
          </div>
        )}

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
          <button
            data-testid="view-diff-btn"
            onClick={() => setShowDiff(!showDiff)}
            style={{
              background: showDiff ? "var(--color-primary)" : "transparent",
              color: showDiff ? "white" : "var(--color-primary)",
              border: "1px solid var(--color-primary)",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            {showDiff ? "Hide Diff" : "View Diff"}
          </button>
        </div>

        {/* Artifact Diff View (REQ-L2-RF-014) */}
        {showDiff && (
          <ArtifactDiff
            entityId={requirement.id}
            entityType="requirement"
            currentVersion={requirement.version}
            diffFetcher={requirementsApi.diff}
            versionsFetcher={requirementsApi.versions}
            onClose={() => setShowDiff(false)}
          />
        )}

        {/* TraceLink panel for this requirement (REQ-L2-RF-006) */}
        <ReqTraceLinkPanel
          workspaceId={workspaceId}
          requirementId={requirement.id}
          requirements={requirements}
          onLinksChanged={onSaved}
        />
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
// ReqTraceLinkPanel — create/list/delete TraceLinks for a requirement
// (REQ-L2-RF-006)
// ---------------------------------------------------------------------------

const REQ_LINK_TYPES: LinkType[] = [
  "parent-child",
  "derives-from",
  "satisfies",
  "verifies",
  "implements",
  "refines",
];

const reqPanelInputStyle: React.CSSProperties = {
  width: "100%",
  fontSize: "var(--font-size-base)",
  padding: "var(--space-2) var(--space-3)",
  marginBottom: "var(--space-2)",
  boxSizing: "border-box",
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  color: "var(--color-text)",
  fontFamily: "var(--font-sans)",
};

const reqPanelLabelStyle: React.CSSProperties = {
  fontWeight: 600,
  display: "block",
  marginBottom: "var(--space-1)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const reqPanelPrimaryBtn: React.CSSProperties = {
  background: "var(--color-primary)",
  color: "#ffffff",
  border: "none",
  borderRadius: "var(--radius-md)",
  padding: "var(--space-2) var(--space-4)",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  cursor: "pointer",
};

interface ReqTraceLinkPanelProps {
  workspaceId: UUID;
  requirementId: UUID;
  requirements: Requirement[];
  onLinksChanged: () => void;
}

function ReqTraceLinkPanel({
  workspaceId,
  requirementId,
  requirements,
  onLinksChanged,
}: ReqTraceLinkPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [links, setLinks] = useState<TraceLink[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState<boolean>(false);
  const [targetId, setTargetId] = useState<string>("");
  const [linkType, setLinkType] = useState<LinkType>("derives-from");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [testCases, setTestCases] = useState<TestCase[]>([]);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    async function load(): Promise<void> {
      try {
        const resp = await tracelinksApi.listForArtifact(workspaceId, requirementId);
        if (cancelled) return;
        setLinks(resp.results);
      } catch (err: unknown) {
        if (cancelled) return;
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setError(msg);
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [workspaceId, requirementId, reloadKey]);

  // Load TestCases so the trace-link target dropdown can offer them in
  // an optgroup alongside Requirements (A.6, REQ-L1-035).
  useEffect(() => {
    let cancelled = false;
    testcasesApi
      .list(workspaceId)
      .then((resp) => {
        if (!cancelled) setTestCases(resp.results);
      })
      .catch((err: unknown) => {
        // Soft-fail: dropdown just shows the Requirements group only.
        if (cancelled) return;
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        // Keep the panel alive even if TestCases loading fails (e.g. preset
        // doesn't expose them); log for diagnostics.
        // eslint-disable-next-line no-console
        console.warn("Failed to load TestCases for trace-link target list:", msg);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const requirementsById: Record<UUID, Requirement> = React.useMemo(() => {
    const m: Record<UUID, Requirement> = {};
    for (const r of requirements) m[r.id] = r;
    return m;
  }, [requirements]);

  const otherRequirements = requirements.filter((r) => r.id !== requirementId);

  function openForm(): void {
    setTargetId("");
    setLinkType("derives-from");
    setSubmitError(null);
    setShowForm(true);
  }

  function cancelForm(): void {
    setShowForm(false);
    setSubmitError(null);
  }

  async function submitForm(
    e: React.FormEvent<HTMLFormElement>
  ): Promise<void> {
    e.preventDefault();
    if (!targetId) {
      setSubmitError(t("traceability.targetRequired"));
      return;
    }
    setIsSubmitting(true);
    setSubmitError(null);
    try {
      await tracelinksApi.create({
        source_id: requirementId,
        target_id: targetId,
        link_type: linkType,
      });
      setShowForm(false);
      setTargetId("");
      setReloadKey((k) => k + 1);
      onLinksChanged();
    } catch (err: unknown) {
      const apiErr = err as {
        error?: {
          message?: string;
          details?: { field?: string; errors?: string[] }[];
        };
      };
      const baseMsg = apiErr?.error?.message;
      const firstDetail = apiErr?.error?.details?.[0];
      const detailMsg = firstDetail
        ? `${firstDetail.field ?? ""}: ${(firstDetail.errors ?? []).join(", ")}`
        : "";
      const msg = baseMsg
        ? detailMsg
          ? `${baseMsg} — ${detailMsg}`
          : baseMsg
        : String(err);
      setSubmitError(msg);
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleDelete(linkId: UUID): Promise<void> {
    try {
      await tracelinksApi.delete(linkId);
      setReloadKey((k) => k + 1);
      onLinksChanged();
    } catch (err: unknown) {
      console.error("Delete tracelink failed:", err);
    }
  }

  return (
    <div
      data-testid="req-tracelink-panel"
      style={{
        marginTop: "var(--space-6)",
        background: "var(--color-surface)",
        borderRadius: "var(--radius-lg)",
        boxShadow: "var(--shadow-card)",
        padding: "var(--space-4)",
      }}
    >
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: "var(--space-3)",
        }}
      >
        <h4
          style={{
            margin: 0,
            fontSize: "var(--font-size-base)",
            fontWeight: 700,
            color: "var(--color-text)",
          }}
        >
          {t("arch.tracelinkPanelTitle")}
        </h4>
        {!showForm && (
          <button
            type="button"
            data-testid="req-tracelink-create-btn"
            onClick={openForm}
            style={reqPanelPrimaryBtn}
          >
            {t("traceability.create")}
          </button>
        )}
      </div>

      {showForm && (
        <form
          onSubmit={(e) => void submitForm(e)}
          style={{
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-2)",
            marginBottom: "var(--space-3)",
            padding: "var(--space-3)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--color-border)",
          }}
        >
          <label style={reqPanelLabelStyle}>
            {t("traceability.target")}
          </label>
          <select
            data-testid="req-tracelink-target-select"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            disabled={isSubmitting}
            required
            style={reqPanelInputStyle}
          >
            <option value="">
              {otherRequirements.length === 0 && testCases.length === 0
                ? t("traceability.noArtifacts")
                : "—"}
            </option>
            {otherRequirements.length > 0 && (
              <optgroup label={t("traceability.requirementsGroup", "Requirements")}>
                {otherRequirements.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.title || t("editor.untitled")}
                  </option>
                ))}
              </optgroup>
            )}
            {testCases.length > 0 && (
              <optgroup label={t("traceability.testCasesGroup", "Test Cases")}>
                {testCases.map((tc) => (
                  <option key={tc.id} value={tc.id}>
                    {tc.title || t("editor.untitled")}
                  </option>
                ))}
              </optgroup>
            )}
          </select>

          <label style={reqPanelLabelStyle}>
            {t("traceability.linkType")}
          </label>
          <select
            data-testid="req-tracelink-type-select"
            value={linkType}
            onChange={(e) => setLinkType(e.target.value as LinkType)}
            disabled={isSubmitting}
            style={reqPanelInputStyle}
          >
            {REQ_LINK_TYPES.map((lt) => (
              <option key={lt} value={lt}>
                {lt}
              </option>
            ))}
          </select>

          {submitError && (
            <p
              role="alert"
              style={{
                color: "var(--color-danger)",
                fontSize: "var(--font-size-sm)",
                margin: 0,
              }}
            >
              {submitError}
            </p>
          )}

          <div
            style={{
              display: "flex",
              gap: "var(--space-2)",
              justifyContent: "flex-end",
            }}
          >
            <button
              type="button"
              data-testid="req-tracelink-cancel-btn"
              onClick={cancelForm}
              disabled={isSubmitting}
              style={{
                background: "var(--color-surface-raised)",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
                cursor: isSubmitting ? "not-allowed" : "pointer",
              }}
            >
              {t("actions.cancel")}
            </button>
            <button
              type="submit"
              data-testid="req-tracelink-submit-btn"
              disabled={isSubmitting}
              style={{
                ...reqPanelPrimaryBtn,
                opacity: isSubmitting ? 0.6 : 1,
                cursor: isSubmitting ? "not-allowed" : "pointer",
              }}
            >
              {isSubmitting
                ? t("traceability.submitting")
                : t("traceability.submit")}
            </button>
          </div>
        </form>
      )}

      {isLoading && (
        <p
          role="status"
          style={{
            color: "var(--color-text-muted)",
            fontSize: "var(--font-size-sm)",
            margin: 0,
          }}
        >
          {t("loading")}
        </p>
      )}

      {error && !isLoading && (
        <p
          role="alert"
          style={{
            color: "var(--color-danger)",
            fontSize: "var(--font-size-sm)",
            margin: 0,
          }}
        >
          {error}
        </p>
      )}

      {!isLoading && !error && links.length === 0 && (
        <p
          style={{
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
            margin: 0,
          }}
        >
          {t("traceability.none")}
        </p>
      )}

      {!isLoading && !error && links.length > 0 && (
        <ul
          data-testid="req-tracelink-list"
          style={{ listStyle: "none", padding: 0, margin: 0 }}
        >
          {links.map((link) => {
            const targetReq = requirementsById[link.target_id];
            return (
              <li
                key={link.id}
                data-testid="req-tracelink-item"
                style={{
                  padding: "var(--space-2) var(--space-3)",
                  marginBottom: "var(--space-2)",
                  background: "var(--color-surface-raised)",
                  borderRadius: "var(--radius-md)",
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text)",
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  flexWrap: "wrap",
                }}
              >
                <span
                  style={{
                    background: "var(--color-badge-draft)",
                    color: "var(--color-badge-draft-text)",
                    padding: "1px 6px",
                    borderRadius: "var(--radius-full)",
                    fontSize: "var(--font-size-sm)",
                  }}
                >
                  {link.link_type}
                </span>
                <span style={{ fontFamily: "monospace" }}>
                  → {targetReq?.title ?? link.target_id.slice(0, 8) + "…"}
                </span>
                <button
                  data-testid="req-tracelink-delete-btn"
                  onClick={() => void handleDelete(link.id)}
                  style={{
                    marginLeft: "auto",
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
              </li>
            );
          })}
        </ul>
      )}
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
  const { requirements, requirement, upstreamLinks, downstreamLinks, isLoading, error, refresh } =
    useRequirementData(selectedId);

  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [newBtnHovered, setNewBtnHovered] = useState(false);
  const [isExportingPdf, setIsExportingPdf] = useState(false);

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

  const handleExportPdf = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsExportingPdf(true);
    try {
      const blob = await workspacesApi.downloadPdfReport(
        activeWorkspace.id,
        "requirement_document"
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `requirement_document_${activeWorkspace.id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("PDF export failed:", err);
    } finally {
      setIsExportingPdf(false);
    }
  }, [activeWorkspace]);

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
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <button
              type="button"
              data-testid="export-pdf-btn"
              onClick={() => void handleExportPdf()}
              disabled={!activeWorkspace || isExportingPdf}
              style={{
                background: "var(--color-surface)",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-sm)",
                cursor: activeWorkspace ? "pointer" : "not-allowed",
                opacity: isExportingPdf ? 0.6 : 1,
              }}
            >
              {isExportingPdf ? "Exporting…" : "Export PDF"}
            </button>
            <button
              type="button"
              data-testid="csv-import-toolbar-btn"
              onClick={() => navigate("/import")}
              disabled={!activeWorkspace}
              style={{
                background: "var(--color-surface)",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-sm)",
                cursor: activeWorkspace ? "pointer" : "not-allowed",
                opacity: activeWorkspace ? 1 : 0.5,
              }}
            >
              {t("import.upload", "Import CSV")}
            </button>
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
            requirements={requirements}
            workspaceId={activeWorkspace!.id}
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
