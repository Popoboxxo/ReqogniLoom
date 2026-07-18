/**
 * ARCH-L1-001 ReactFrontend — DiagramDetailView (Presenter).
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L2-DS-001 (DiagramService REST API), REQ-L1-057 (Code/Visual toggle),
 *          REQ-L2-CV-005 (persisted canvas), REQ-L1-095 (ArtifactInspector adoption),
 *          REQ-050 (Container/Presenter decomposition)
 *
 * Right-panel detail view for a single diagram. Data (detail row, persisted
 * canvas, save/delete) is owned by useDiagramDetail; this component keeps only
 * view state (edit mode, source draft, Code/Visual toggle, mermaid render).
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { CanvasEditor } from "../canvas/CanvasEditor";
import { RightSidebar } from "../shared/ArtifactInspector";
import type { VersionRef } from "../shared/ArtifactInspector";
import { WorkflowStatusEditor } from "../WorkflowStatusEditor";
import { useDiagramDetail } from "./useDiagramData";
import {
  diagramVersionLabel,
  formCancelButtonStyle,
  formDangerButtonStyle,
  formPrimaryButtonStyle,
} from "./diagram-view-shared";

export interface DiagramDetailViewProps {
  diagramId: string;
  onBack: () => void;
  onChanged: () => Promise<void> | void;
}

export function DiagramDetailView({
  diagramId,
  onBack,
  onChanged,
}: DiagramDetailViewProps): JSX.Element {
  const { t } = useTranslation();
  const {
    detail,
    isLoading,
    canvasJson,
    canvasStrokes,
    isCanvasLoading,
    saveContent,
    deleteDiagram,
    isSaving,
    saveError,
    resetSaveError,
  } = useDiagramDetail(diagramId);

  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState("");

  // Code/Visual toggle (REQ-L1-057) — mermaid sources can be rendered
  // client-side via mermaid.js; other payload formats stay code-only.
  const [viewMode, setViewMode] = useState<"code" | "visual">("visual");
  const [renderedSvg, setRenderedSvg] = useState<string>("");
  const [renderError, setRenderError] = useState<string>("");

  // Reset the view when switching diagrams and seed the source draft once the
  // detail row is (re)loaded.
  useEffect(() => {
    setIsEditing(false);
    setViewMode("visual");
  }, [diagramId]);

  useEffect(() => {
    if (detail) setEditContent(detail.content ?? "");
  }, [detail]);

  // Current-version ref for the ArtifactInspector (REQ-L2-RF-035).
  const currentVersion: VersionRef | undefined = useMemo(() => {
    if (
      !detail ||
      detail.version_number === null ||
      detail.version_number === undefined
    ) {
      return undefined;
    }
    return {
      version: detail.version_number,
      label: `v${detail.version_number}`,
      createdAt: detail.created_at ?? null,
      baselineIds: [],
    };
  }, [detail]);

  const canRenderVisual = detail?.payload_format === "mermaid";
  const activeSource = isEditing ? editContent : detail?.content ?? "";

  // Client-side Mermaid rendering for the Visual view.
  useEffect(() => {
    if (!canRenderVisual || viewMode !== "visual") {
      setRenderedSvg("");
      setRenderError("");
      return;
    }
    if (!activeSource.trim()) {
      setRenderedSvg("");
      setRenderError("");
      return;
    }

    let cancelled = false;

    async function renderMermaid(): Promise<void> {
      try {
        const mermaid = (await import("mermaid")).default;
        if (cancelled) return;
        mermaid.initialize({
          startOnLoad: false,
          theme: "default",
          securityLevel: "strict",
        });
        const id = `diagram-mermaid-${diagramId}-${Date.now()}`;
        const { svg } = await mermaid.render(id, activeSource);
        if (!cancelled) {
          setRenderedSvg(svg);
          setRenderError("");
        }
      } catch (err) {
        if (cancelled) return;
        setRenderedSvg("");
        setRenderError(err instanceof Error ? err.message : String(err));
      }
    }

    void renderMermaid();
    return () => {
      cancelled = true;
    };
  }, [canRenderVisual, viewMode, activeSource, diagramId]);

  const handleSave = async (): Promise<void> => {
    if (!detail?.payload_format) return;
    try {
      await saveContent(editContent);
      setIsEditing(false);
      await onChanged();
    } catch {
      // Error surfaced via saveError from the mutation.
    }
  };

  const handleDelete = async (): Promise<void> => {
    if (
      !window.confirm(t("diagrams.deleteConfirm", "Really delete this diagram?"))
    ) {
      return;
    }
    try {
      await deleteDiagram();
      await onChanged();
      onBack();
    } catch (err) {
      console.error("Failed to delete diagram", err);
    }
  };

  if (isLoading) {
    return <p>{t("loading", "Loading...")}</p>;
  }

  if (!detail) {
    return (
      <div>
        <p>{t("diagrams.notFound", "Diagram not found.")}</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: "var(--space-6)", alignItems: "flex-start" }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <h2
          style={{
            fontSize: "var(--font-size-2xl)",
            fontWeight: 700,
            color: "var(--color-text)",
            marginTop: 0,
            marginBottom: "var(--space-2)",
          }}
        >
          {detail.name}
        </h2>

        <div
          style={{
            display: "flex",
            gap: "var(--space-3)",
            marginBottom: "var(--space-4)",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
          }}
        >
          <span>{t("diagrams.type", "Type")}: {detail.diagram_type}</span>
          <span>·</span>
          <span>{detail.payload_format ?? "?"}</span>
          {detail.version_number !== null && (
            <>
              <span>·</span>
              <span>v{diagramVersionLabel(detail.version_number)}</span>
            </>
          )}
        </div>

        {detail.description && (
          <p
            style={{
              color: "var(--color-text-muted)",
              marginBottom: "var(--space-4)",
            }}
          >
            {detail.description}
          </p>
        )}

        {/* REQ-173: WorkflowEngine-driven status editor for the diagram. */}
        {diagramId && (
          <div style={{ marginBottom: "var(--space-4)" }}>
            <WorkflowStatusEditor
              artifactType="diagram"
              artifactId={diagramId}
              currentStatus={detail.status ?? undefined}
              disabled={isSaving}
              onTransitionComplete={onChanged}
            />
          </div>
        )}

        <div
          style={{
            display: "flex",
            gap: "var(--space-2)",
            marginBottom: "var(--space-4)",
          }}
        >
          {!isEditing ? (
            <button
              type="button"
              data-testid="diagram-edit-btn"
              onClick={() => {
                setIsEditing(true);
                setViewMode("code");
              }}
              style={formPrimaryButtonStyle}
              // For canvas diagrams the button opens the canvas editor; hide when already in canvas mode
              hidden={detail.payload_format === "canvas_stroke"}
            >
              {t("diagrams.edit", "Edit Source")}
            </button>
          ) : (
            <>
              <button
                type="button"
                data-testid="diagram-save-btn"
                onClick={() => void handleSave()}
                disabled={isSaving}
                style={{
                  ...formPrimaryButtonStyle,
                  opacity: isSaving ? 0.6 : 1,
                }}
              >
                {isSaving ? t("actions.saving", "Saving...") : t("actions.save", "Save")}
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsEditing(false);
                  setEditContent(detail.content ?? "");
                  resetSaveError();
                }}
                style={formCancelButtonStyle}
              >
                {t("actions.cancel", "Cancel")}
              </button>
            </>
          )}
          <button
            type="button"
            data-testid="diagram-delete-btn"
            onClick={() => void handleDelete()}
            style={formDangerButtonStyle}
          >
            {t("diagrams.delete", "Delete")}
          </button>
        </div>

        {saveError && (
          <p
            role="alert"
            data-testid="diagram-detail-error"
            style={{ color: "var(--color-danger)", marginBottom: "var(--space-3)" }}
          >
            {saveError}
          </p>
        )}

        {/* Canvas diagrams use the CanvasEditor surface (REQ-L2-DS-006, IF-L1-058/060) */}
        {detail.payload_format === "canvas_stroke" ? (
          <div
            data-testid="diagram-canvas-section"
            style={{
              height: "calc(100vh - 260px)",
              minHeight: "560px",
              display: "flex",
              flexDirection: "column",
            }}
          >
            {isCanvasLoading ? (
              <p role="status">{t("loading", "Loading...")}</p>
            ) : (
              <CanvasEditor
                diagramId={diagramId}
                initialCanvasJson={canvasJson}
                initialStrokes={canvasStrokes}
                onAutoSave={(strokes) => {
                  // Optimistically mark diagram as having saved content
                  console.debug("Canvas auto-saved", strokes.length, "strokes");
                }}
              />
            )}
          </div>
        ) : (
          <>
          {canRenderVisual && (
            <div
              role="group"
              aria-label={t("diagrams.viewMode", "View mode")}
              style={{ display: "flex", gap: "var(--space-1)", marginBottom: "var(--space-3)" }}
            >
              <button
                type="button"
                data-testid="diagram-viewmode-code-btn"
                aria-pressed={viewMode === "code"}
                onClick={() => setViewMode("code")}
                style={{
                  ...formCancelButtonStyle,
                  ...(viewMode === "code" ? formPrimaryButtonStyle : {}),
                }}
              >
                {t("diagrams.viewMode.code", "Code")}
              </button>
              <button
                type="button"
                data-testid="diagram-viewmode-visual-btn"
                aria-pressed={viewMode === "visual"}
                onClick={() => setViewMode("visual")}
                style={{
                  ...formCancelButtonStyle,
                  ...(viewMode === "visual" ? formPrimaryButtonStyle : {}),
                }}
              >
                {t("diagrams.viewMode.visual", "Visual")}
              </button>
            </div>
          )}
          {canRenderVisual && viewMode === "visual" ? (
            <div
              data-testid="diagram-visual-preview"
              style={{
                padding: "var(--space-4)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                background: "var(--color-surface-raised)",
                overflow: "auto",
                maxHeight: "480px",
                minHeight: "160px",
              }}
            >
              {renderError ? (
                <p role="alert" data-testid="diagram-visual-error" style={{ color: "var(--color-danger)", margin: 0 }}>
                  {renderError}
                </p>
              ) : renderedSvg ? (
                <div
                  data-testid="diagram-visual-svg"
                  dangerouslySetInnerHTML={{ __html: renderedSvg }}
                />
              ) : (
                <p style={{ color: "var(--color-text-muted)", margin: 0 }}>
                  {t("diagrams.emptySource", "(no source)")}
                </p>
              )}
            </div>
          ) : isEditing ? (
          <label style={{ display: "block" }}>
            <span
              style={{
                fontWeight: 500,
                display: "block",
                marginBottom: "var(--space-1)",
                color: "var(--color-text)",
              }}
            >
              {t("diagrams.source", "Source")}
            </span>
            <textarea
              data-testid="diagram-source-textarea"
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              rows={18}
              style={{
                width: "100%",
                padding: "var(--space-3)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                fontFamily: "var(--font-mono)",
                fontSize: "var(--font-size-sm)",
                background: "var(--color-surface)",
                color: "var(--color-text)",
                resize: "vertical",
                boxSizing: "border-box",
              }}
            />
          </label>
        ) : (
          <pre
            data-testid="diagram-source-preview"
            style={{
              padding: "var(--space-4)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
              background: "var(--color-surface-raised)",
              fontFamily: "var(--font-mono)",
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text)",
              overflow: "auto",
              maxHeight: "480px",
              margin: 0,
              whiteSpace: "pre-wrap",
              wordBreak: "break-word",
            }}
          >
            {detail.content || t("diagrams.emptySource", "(no source)")}
          </pre>
        )}
        </>
        )}
      </div>

      {/* Unified <RightSidebar kind="diagram" /> — Version / Diff / Trace (REQ-L1-095). */}
      <RightSidebar
        kind="diagram"
        artifactId={diagramId}
        currentVersion={currentVersion}
      />
    </div>
  );
}
