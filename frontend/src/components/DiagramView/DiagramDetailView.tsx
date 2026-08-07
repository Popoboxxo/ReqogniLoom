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
 *
 * Phase 6 / decision E2-D4 — preview instead of inline edit detail: the pane
 * answers "what does it look like?", not "how do I change it?". Formats that
 * own a fullscreen editor route render read-only here and their primary
 * action navigates to that route (D3: /diagrams/:id/canvas and
 * /diagrams/:id/mermaid stay fullscreen, without the list):
 *   - canvas_stroke -> server-rendered SVG export (IF-L1-060), NOT a mounted
 *     <CanvasEditor>. Mounting the editable Fabric surface in a 40%-wide
 *     preview pane was both the wrong affordance and the reason this presenter
 *     needed a canvas/WebGL stub in every test that rendered it.
 *   - mermaid -> client-side mermaid.render of the persisted source, with the
 *     Code/Visual toggle kept as a read-only view switch (REQ-L1-057).
 * Formats with NO fullscreen editor (plantuml, json) keep the inline source
 * editor: removing it would drop the only way to edit them at all, which
 * ch. 4 (funktionale Untergrenze) forbids. That fallback is the only path on
 * which `isEditing` can still become true.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { sanitizeSvg } from "../../utils/sanitizeSvg";
import { RightSidebar } from "../shared/ArtifactInspector";
import type { VersionRef } from "../shared/ArtifactInspector";
import { WorkflowStatusEditor } from "../WorkflowStatusEditor";
import { GraphCanvas } from "../DiagramGraphEditor/GraphCanvas";
import {
  parseNodeGraphContentStrict,
  payloadToFlowEdges,
  payloadToFlowNodes,
} from "../DiagramGraphEditor/useGraphPayload";
import { useDiagramDetail } from "./useDiagramData";
import type { NodeGraphPayload } from "../../types";
import {
  diagramVersionLabel,
  formCancelButtonStyle,
  formDangerButtonStyle,
  formPrimaryButtonStyle,
  previewBoxStyle,
  previewErrorStyle,
  previewEmptyStyle,
} from "./diagram-view-shared";

export interface DiagramDetailViewProps {
  diagramId: string;
  onBack: () => void;
  onChanged: () => Promise<void> | void;
}

/**
 * What this pane renders for a given ``payload_format``, and which
 * fullscreen editor route (if any) its primary action navigates to.
 *
 * GH-353 Task 9 / final-review T9: replaces the three independently-computed
 * `isCanvas`/`isNodeGraph`/`canRenderVisual` booleans (each re-deriving
 * `payload_format === "..."`) and the nested `editorRoute` ternary chain with
 * a single lookup keyed by `payload_format` — one place to add a future
 * format instead of three-plus scattered equality checks.
 */
type PreviewKind = "node_graph" | "canvas" | "mermaid" | "source";

interface PayloadFormatPreviewConfig {
  previewKind: PreviewKind;
  /** Fullscreen editor route for this format, or null when it has none
   * (plantuml/json keep the inline source editor — D3/E2-D4). */
  editorRoute: (diagramId: string) => string | null;
}

const PAYLOAD_FORMAT_PREVIEW: Record<string, PayloadFormatPreviewConfig> = {
  node_graph: {
    previewKind: "node_graph",
    editorRoute: (id) => `/diagrams/${id}/graph`,
  },
  canvas_stroke: {
    previewKind: "canvas",
    editorRoute: (id) => `/diagrams/${id}/canvas`,
  },
  mermaid: {
    previewKind: "mermaid",
    editorRoute: (id) => `/diagrams/${id}/mermaid`,
  },
};

/** plantuml/json (and any unrecognised future format) fall back to the
 * inline source editor — no fullscreen route. */
const DEFAULT_PREVIEW_CONFIG: PayloadFormatPreviewConfig = {
  previewKind: "source",
  editorRoute: () => null,
};

function previewConfigFor(payloadFormat: string | null | undefined): PayloadFormatPreviewConfig {
  if (!payloadFormat) return DEFAULT_PREVIEW_CONFIG;
  return PAYLOAD_FORMAT_PREVIEW[payloadFormat] ?? DEFAULT_PREVIEW_CONFIG;
}

export function DiagramDetailView({
  diagramId,
  onBack,
  onChanged,
}: DiagramDetailViewProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const {
    detail,
    isLoading,
    canvasSvg,
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

  // Node graph payload parsing for read-only preview (GH-353 Task 9)
  const [nodeGraphPayload, setNodeGraphPayload] = useState<NodeGraphPayload | null>(null);
  const [nodeGraphError, setNodeGraphError] = useState<string>("");

  // Reset the view when switching diagrams and seed the source draft once the
  // detail row is (re)loaded.
  useEffect(() => {
    setIsEditing(false);
    setViewMode("visual");
  }, [diagramId]);

  useEffect(() => {
    if (detail) setEditContent(detail.content ?? "");
  }, [detail]);

  // Parse node_graph payload for read-only preview (GH-353 Task 9).
  // I4 (final review): uses the canonical, shape-validating
  // parseNodeGraphContentStrict (useGraphPayload.ts) instead of a bespoke
  // inline JSON.parse that only caught syntax errors, not e.g. a valid JSON
  // object missing 'nodes'/'edges' arrays — that weaker check let this
  // pane's other read-only-preview bug (C1: raw domain objects handed to
  // GraphCanvas) through a task-scoped review undetected.
  useEffect(() => {
    if (detail?.payload_format === "node_graph" && detail?.content) {
      try {
        const payload = parseNodeGraphContentStrict(detail.content);
        setNodeGraphPayload(payload);
        setNodeGraphError("");
      } catch (err) {
        setNodeGraphPayload(null);
        setNodeGraphError(err instanceof Error ? err.message : String(err));
      }
    } else {
      setNodeGraphPayload(null);
      setNodeGraphError("");
    }
  }, [detail?.payload_format, detail?.content]);

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

  // Both SVG strings are rendered via dangerouslySetInnerHTML below, so they
  // pass through DOMPurify first (see utils/sanitizeSvg).
  const safeCanvasSvg = useMemo(() => sanitizeSvg(canvasSvg ?? ""), [canvasSvg]);
  const safeRenderedSvg = useMemo(() => sanitizeSvg(renderedSvg), [renderedSvg]);

  // GH-353 Task 9 / final-review T9: previewKind + editorRoute are both
  // derived from the single PAYLOAD_FORMAT_PREVIEW map above, keyed on
  // `payload_format` (not `diagram_type`: the editors are bound to the
  // payload endpoints — canvas-strokes / mermaid-source / node_graph content
  // — and a diagram of type "flow" may well carry a mermaid payload).
  const previewConfig = previewConfigFor(detail?.payload_format);
  const previewKind = previewConfig.previewKind;
  const isCanvas = previewKind === "canvas";
  const isNodeGraph = previewKind === "node_graph";
  const canRenderVisual = previewKind === "mermaid";
  const activeSource = isEditing ? editContent : detail?.content ?? "";
  const editorRoute: string | null = previewConfig.editorRoute(diagramId);

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
          // Labels must be plain SVG <text>: the rendered markup passes
          // through sanitizeSvg, which drops <foreignObject> (mXSS vector).
          htmlLabels: false,
          flowchart: { htmlLabels: false },
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
          {/* D4: for formats with a fullscreen editor the primary action
              navigates there instead of turning this pane into a form. */}
          {editorRoute ? (
            <button
              type="button"
              data-testid="diagram-open-editor-btn"
              onClick={() => navigate(editorRoute)}
              style={formPrimaryButtonStyle}
            >
              {t("diagrams.openEditor", "Open editor")}
            </button>
          ) : !isEditing ? (
            <button
              type="button"
              data-testid="diagram-edit-btn"
              onClick={() => {
                setIsEditing(true);
                setViewMode("code");
              }}
              style={formPrimaryButtonStyle}
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

        {/* GH-353 Task 9: node_graph diagrams show the read-only React Flow
            preview; editing happens on the fullscreen /diagrams/:id/graph route. */}
        {isNodeGraph ? (
          <div data-testid="diagram-node-graph-section" style={previewBoxStyle}>
            {nodeGraphError ? (
              <p role="alert" data-testid="diagram-node-graph-error" style={previewErrorStyle}>
                {nodeGraphError}
              </p>
            ) : nodeGraphPayload ? (
              // C1 (final review): GraphCanvas needs React-Flow-shaped nodes
              // (data.node.label, type="graphNode"/"graphEdge") — passing the
              // raw domain NodeGraphPayload.nodes/edges directly both fails
              // `tsc` (GraphCanvasProps expects GraphFlowNode[]/GraphFlowEdge[])
              // and, even where a loose type let it through, renders unlabeled
              // default nodes because React Flow finds no NODE_TYPES/EDGE_TYPES
              // match for a raw domain object.
              <GraphCanvas
                nodes={payloadToFlowNodes(nodeGraphPayload)}
                edges={payloadToFlowEdges(nodeGraphPayload)}
                isLoading={false}
                error={null}
                selection={{ kind: "none" }}
                onSelect={() => {}}
                editMode={false}
                elementsSelectable={false}
                onConnectNodes={() => {}}
                onRenameNode={() => {}}
                onNodeDragStop={() => {}}
                onDeleteSelection={() => {}}
                onAddNode={() => {}}
                onAutoLayout={() => {}}
              />
            ) : (
              <p style={previewEmptyStyle}>
                {t("diagrams.emptySource", "(no source)")}
              </p>
            )}
          </div>
        ) : isCanvas ? (
          <div data-testid="diagram-canvas-section" style={previewBoxStyle}>
            {isCanvasLoading ? (
              <p role="status">{t("loading", "Loading...")}</p>
            ) : canvasSvg ? (
              <div
                data-testid="diagram-canvas-svg"
                dangerouslySetInnerHTML={{ __html: safeCanvasSvg }}
              />
            ) : (
              <p style={{ color: "var(--color-text-muted)", margin: 0 }}>
                {t("diagrams.emptyCanvas", "This canvas is still empty.")}
              </p>
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
                {t("diagrams.viewModeLabels.code", "Code")}
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
                {t("diagrams.viewModeLabels.visual", "Visual")}
              </button>
            </div>
          )}
          {canRenderVisual && viewMode === "visual" ? (
            <div data-testid="diagram-visual-preview" style={previewBoxStyle}>
              {renderError ? (
                <p role="alert" data-testid="diagram-visual-error" style={{ color: "var(--color-danger)", margin: 0 }}>
                  {renderError}
                </p>
              ) : renderedSvg ? (
                <div
                  data-testid="diagram-visual-svg"
                  dangerouslySetInnerHTML={{ __html: safeRenderedSvg }}
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
