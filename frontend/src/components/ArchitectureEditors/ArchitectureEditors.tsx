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

import React, { useState, useCallback, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useArchitectureData } from "./useArchitectureData";
import { MarkdownPreview } from "../RequirementEditors/MarkdownPreview";
import { ArtifactDiff } from "../ArtifactDiff/ArtifactDiff";
import { architectureApi } from "../../api/architecture";
import { tracelinksApi } from "../../api/tracelinks";
import { requirementsApi } from "../../api/requirements";
import { useWorkspace } from "../../context/WorkspaceContext";
import type {
  ArchitectureElement,
  ElementType,
  LinkType,
  Requirement,
  TraceLink,
  UUID,
} from "../../types";

// ---------------------------------------------------------------------------
// Element type options (REQ-L3-RF004-001, ADR-L3-RF-007)
// ---------------------------------------------------------------------------

const ELEMENT_TYPES: { value: ElementType; labelKey: string }[] = [
  { value: "component", labelKey: "arch.elementType.component" },
  { value: "interface", labelKey: "arch.elementType.interface" },
  { value: "subsystem", labelKey: "arch.elementType.subsystem" },
  { value: "layer", labelKey: "arch.elementType.layer" },
  { value: "module", labelKey: "arch.elementType.module" },
];

// ---------------------------------------------------------------------------
// Shared style helpers — token-based
// ---------------------------------------------------------------------------

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
  transition: "var(--transition-fast)",
  outline: "none",
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

const dangerButtonStyle: React.CSSProperties = {
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
};

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
            style={dangerButtonStyle}
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
              fontFamily: "var(--font-sans)",
            }}
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
  isExtendedPreset: boolean;
}

function ArchElementForm({
  element,
  onSaved,
  onDelete,
  isExtendedPreset,
}: ArchElementFormProps): JSX.Element {
  const { t } = useTranslation();
  const [title, setTitle] = useState(element.title);
  const [description, setDescription] = useState(element.description);
  const [elementType, setElementType] = useState(element.element_type);
  const [changeReason, setChangeReason] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [showDiff, setShowDiff] = useState(false);

  const handleSave = useCallback(async (): Promise<void> => {
    setIsSaving(true);
    setSaveError(null);
    try {
      // For extended preset, also send change_reason (REQ-L2-RF-009).
      const payload: Partial<
        Pick<
          ArchitectureElement,
          "title" | "description" | "element_type"
        >
      > & { change_reason?: string } = {
        title,
        description,
        element_type: elementType,
      };
      if (isExtendedPreset && changeReason.trim()) {
        payload.change_reason = changeReason.trim();
      }
      await architectureApi.update(element.id, payload);
      setChangeReason("");
      onSaved();
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setSaveError(msg);
    } finally {
      setIsSaving(false);
    }
  }, [
    element.id,
    title,
    description,
    elementType,
    changeReason,
    isExtendedPreset,
    onSaved,
  ]);

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

      <label htmlFor="arch-title" style={labelStyle}>
        {t("editor.title")}
      </label>
      <input
        id="arch-title"
        data-testid="arch-title"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        style={{ ...inputStyle, fontSize: "var(--font-size-lg)", fontWeight: 600 }}
        onFocus={(e) => {
          (e.currentTarget as HTMLInputElement).style.borderColor = "var(--color-primary)";
        }}
        onBlur={(e) => {
          (e.currentTarget as HTMLInputElement).style.borderColor = "var(--color-border)";
        }}
      />

      {/* Element type dropdown (REQ-L3-RF004-001, ADR-L3-RF-007) */}
      <label htmlFor="arch-type" style={labelStyle}>
        {t("arch.elementType")}
      </label>
      <select
        id="arch-type"
        data-testid="arch-element-type-select"
        value={elementType}
        onChange={(e) => setElementType(e.target.value)}
        style={{ ...inputStyle, width: "auto", minWidth: "200px" }}
      >
        {ELEMENT_TYPES.map((et) => (
          <option key={et.value} value={et.value}>
            {t(et.labelKey)}
          </option>
        ))}
      </select>

      {/* Markdown description (REQ-L3-RF004-002) */}
      <label style={labelStyle}>
        {t("editor.description")}
      </label>
      <MarkdownPreview
        value={description}
        onChange={setDescription}
      />

      {/* Change reason — only visible under the extended preset (REQ-L2-RF-009). */}
      {isExtendedPreset && (
        <>
          <label htmlFor="arch-change-reason" style={labelStyle}>
            {t("req.changeReason")}
          </label>
          <input
            id="arch-change-reason"
            data-testid="arch-change-reason-input"
            value={changeReason}
            onChange={(e) => setChangeReason(e.target.value)}
            placeholder={t("req.changeReasonPlaceholder")}
            style={inputStyle}
          />
        </>
      )}

      {saveError && (
        <p
          role="alert"
          style={{
            color: "var(--color-danger)",
            marginTop: "var(--space-3)",
            fontSize: "var(--font-size-sm)",
          }}
        >
          {saveError}
        </p>
      )}

      <div
        style={{
          display: "flex",
          gap: "var(--space-3)",
          marginTop: "var(--space-4)",
        }}
      >
        <button
          data-testid="arch-save-btn"
          onClick={() => void handleSave()}
          disabled={isSaving}
          style={{
            ...primaryButtonStyle,
            opacity: isSaving ? 0.6 : 1,
            cursor: isSaving ? "not-allowed" : "pointer",
          }}
          onMouseEnter={(e) => {
            if (!isSaving) {
              (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary-dark)";
            }
          }}
          onMouseLeave={(e) => {
            (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary)";
          }}
        >
          {isSaving ? t("actions.saving") : t("actions.save")}
        </button>
        <button
          data-testid="arch-delete-btn"
          onClick={() => setShowDeleteDialog(true)}
          style={dangerButtonStyle}
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
          data-testid="arch-view-diff-btn"
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
          entityId={element.id}
          entityType="architecture"
          currentVersion={element.version}
          diffFetcher={architectureApi.diff}
          versionsFetcher={architectureApi.versions}
          onClose={() => setShowDiff(false)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ArchTraceLinkPanel — list + create TraceLinks for a specific element
// (REQ-L2-RF-006, REQ-L3-RF004-003)
// ---------------------------------------------------------------------------

const ARCH_LINK_TYPES: LinkType[] = [
  "satisfies",
  "implements",
  "verifies",
  "derives-from",
];

interface ArchTraceLinkPanelProps {
  workspaceId: UUID;
  elementId: UUID;
}

function ArchTraceLinkPanel({
  workspaceId,
  elementId,
}: ArchTraceLinkPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [links, setLinks] = useState<TraceLink[]>([]);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState<boolean>(false);
  const [targetId, setTargetId] = useState<string>("");
  const [linkType, setLinkType] = useState<LinkType>("satisfies");
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState<number>(0);

  useEffect(() => {
    let cancelled = false;
    setIsLoading(true);
    setError(null);

    async function load(): Promise<void> {
      try {
        const [linksResp, reqResp] = await Promise.all([
          tracelinksApi.listForArtifact(workspaceId, elementId),
          requirementsApi.list(workspaceId),
        ]);
        if (cancelled) return;
        setLinks(linksResp.results);
        setRequirements(reqResp.results);
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
  }, [workspaceId, elementId, reloadKey]);

  const requirementsById: Record<UUID, Requirement> = React.useMemo(() => {
    const m: Record<UUID, Requirement> = {};
    for (const r of requirements) m[r.id] = r;
    return m;
  }, [requirements]);

  function openForm(): void {
    setTargetId("");
    setLinkType("satisfies");
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
        source_id: elementId,
        target_id: targetId,
        link_type: linkType,
      });
      setShowForm(false);
      setTargetId("");
      setReloadKey((k) => k + 1);
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

  return (
    <div
      data-testid="arch-tracelink-panel"
      style={{
        marginTop: "var(--space-4)",
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
            data-testid="arch-tracelink-create-btn"
            onClick={openForm}
            style={primaryButtonStyle}
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
          <label style={{ ...labelStyle, marginBottom: "var(--space-1)" }}>
            {t("traceability.source")}
          </label>
          <input
            value={elementId}
            readOnly
            style={{
              ...inputStyle,
              marginBottom: "var(--space-2)",
              fontFamily: "monospace",
              fontSize: "var(--font-size-sm)",
            }}
          />

          <label style={{ ...labelStyle, marginBottom: "var(--space-1)" }}>
            {t("traceability.target")}
          </label>
          <select
            data-testid="arch-tracelink-target-select"
            value={targetId}
            onChange={(e) => setTargetId(e.target.value)}
            disabled={isSubmitting}
            required
            style={{ ...inputStyle, marginBottom: "var(--space-2)" }}
          >
            <option value="">
              {requirements.length === 0
                ? t("traceability.noArtifacts")
                : "—"}
            </option>
            {requirements.map((r) => (
              <option key={r.id} value={r.id}>
                {r.title || t("editor.untitled")}
              </option>
            ))}
          </select>

          <label style={{ ...labelStyle, marginBottom: "var(--space-1)" }}>
            {t("traceability.linkType")}
          </label>
          <select
            data-testid="arch-tracelink-type-select"
            value={linkType}
            onChange={(e) => setLinkType(e.target.value as LinkType)}
            disabled={isSubmitting}
            style={{ ...inputStyle, marginBottom: "var(--space-2)" }}
          >
            {ARCH_LINK_TYPES.map((lt) => (
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
              data-testid="arch-tracelink-cancel-btn"
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
              data-testid="arch-tracelink-submit-btn"
              disabled={isSubmitting}
              style={{
                ...primaryButtonStyle,
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
          data-testid="arch-tracelink-list"
          style={{ listStyle: "none", padding: 0, margin: 0 }}
        >
          {links.map((link) => {
            const targetReq = requirementsById[link.target_id];
            const sourceReq = requirementsById[link.source_id];
            return (
              <li
                key={link.id}
                data-testid="arch-tracelink-item"
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
                <span style={{ fontFamily: "monospace" }}>
                  {sourceReq?.title ?? link.source_id.slice(0, 8) + "…"}
                </span>
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
                  {targetReq?.title ?? link.target_id.slice(0, 8) + "…"}
                </span>
              </li>
            );
          })}
        </ul>
      )}
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
      // Navigate first — the hook re-fetches automatically when selectedId changes.
      // Calling refresh() before navigate() causes a double-fetch race condition.
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
        <button onClick={refresh} style={primaryButtonStyle}>
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  return (
    <div
      style={{
        display: "flex",
        gap: "var(--space-6)",
        fontFamily: "var(--font-sans)",
        color: "var(--color-text)",
      }}
    >
      {/* Elements list (left panel) */}
      <div style={{ minWidth: "280px" }}>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            marginBottom: "var(--space-4)",
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
            style={primaryButtonStyle}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary-dark)";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.background = "var(--color-primary)";
            }}
          >
            + {t("actions.new")}
          </button>
        </div>

        {elements.length === 0 ? (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-sm)",
            }}
          >
            {t("editor.empty")}
          </p>
        ) : (
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {elements.map((el) => {
              const isActive = el.id === selectedId;
              return (
                <li
                  key={el.id}
                  onClick={() => navigate(`/architecture/${el.id}`)}
                  style={{
                    background: isActive ? "#eef2ff" : "var(--color-surface)",
                    borderRadius: "var(--radius-md)",
                    boxShadow: "var(--shadow-card)",
                    padding: "var(--space-3) var(--space-4)",
                    marginBottom: "var(--space-2)",
                    cursor: "pointer",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                    transition: "var(--transition-fast)",
                    borderLeft: isActive
                      ? "3px solid var(--color-primary)"
                      : "3px solid transparent",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) {
                      (e.currentTarget as HTMLLIElement).style.background =
                        "var(--color-surface-raised)";
                      (e.currentTarget as HTMLLIElement).style.boxShadow =
                        "var(--shadow-sm)";
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) {
                      (e.currentTarget as HTMLLIElement).style.background =
                        "var(--color-surface)";
                      (e.currentTarget as HTMLLIElement).style.boxShadow =
                        "var(--shadow-card)";
                    }
                  }}
                >
                  <span
                    style={{
                      flex: 1,
                      fontSize: "var(--font-size-base)",
                      color: "var(--color-text)",
                      fontWeight: isActive ? 600 : 500,
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      whiteSpace: "nowrap",
                    }}
                  >
                    {el.title || t("editor.untitled")}
                  </span>
                  <span
                    style={{
                      fontSize: "var(--font-size-sm)",
                      background: "var(--color-badge-draft)",
                      color: "var(--color-badge-draft-text)",
                      padding: "2px 8px",
                      borderRadius: "var(--radius-full)",
                      marginLeft: "var(--space-2)",
                      fontWeight: 500,
                      whiteSpace: "nowrap",
                    }}
                  >
                    {t(`arch.elementType.${el.element_type}`)}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Detail editor (right panel) */}
      <div style={{ flex: 1 }}>
        {element ? (
          <div
            style={{
              display: "flex",
              gap: "var(--space-6)",
              alignItems: "flex-start",
            }}
          >
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
              <h2
                style={{
                  margin: 0,
                  marginBottom: "var(--space-4)",
                  fontSize: "var(--font-size-2xl)",
                  fontWeight: 700,
                  color: "var(--color-text)",
                }}
              >
                {element.title || t("editor.untitled")}
              </h2>
              <ArchElementForm
                key={element.id}
                element={element}
                onSaved={refresh}
                onDelete={(id) => void handleDelete(id)}
                isExtendedPreset={activeWorkspace?.preset === "extended"}
              />

              {/* TraceLink panel for this element (REQ-L2-RF-006).
                  Use activeWorkspace.id if available, otherwise fall back to
                  element.workspace_id so the panel still renders when navigating
                  directly to /architecture/:id without a workspace in context. */}
              {(activeWorkspace?.id || element.workspace_id) && (
                <ArchTraceLinkPanel
                  workspaceId={activeWorkspace?.id ?? element.workspace_id}
                  elementId={element.id}
                />
              )}
            </div>

            {/* Linked requirements sidebar (REQ-L3-RF004-003) */}
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
                      onClick={() =>
                        navigate(`/requirements/${link.source_id}`)
                      }
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
                        (e.currentTarget as HTMLLIElement).style.background =
                          "#eef2ff";
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
          </div>
        ) : (
          <p
            style={{
              color: "var(--color-text-muted)",
              padding: "var(--space-4)",
            }}
          >
            {t("arch.selectElement")}
          </p>
        )}
      </div>
    </div>
  );
}
