/**
 * ARCH-L1-001 ReactFrontend — DiagramView (COMP-RF-005).
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L0-016 (Interaktive Diagramme und Grafiken),
 *          REQ-L2-DS-001 (DiagramService REST API),
 *          REQ-L2-DS-004 (Traceability connector),
 *          REQ-002 (Split-View Layout)
 *
 * Split-View layout with resizable divider:
 *   - Left panel: diagram list + create button
 *   - Divider: 4px resizable
 *   - Right panel: create form OR diagram detail (source, traceability)
 *
 * Rendering: the source is shown as a monospaced pre/code block by default,
 * with a persistent Code/Visual toggle. Mermaid sources render client-side
 * via mermaid.js when Visual is active; other payload formats stay code-only
 * (no client-side renderer available).
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { diagramsApi } from "../../api/diagrams";
import { requirementsApi } from "../../api/requirements";
import { architectureApi } from "../../api/architecture";
import { tracelinksApi } from "../../api/tracelinks";
import { CanvasEditor } from "../canvas/CanvasEditor";
import type {
  ArchitectureElement,
  Diagram,
  DiagramDetail,
  DiagramTraceLink,
  DiagramType,
  PayloadFormat,
  Requirement,
} from "../../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const DIAGRAM_TYPES: DiagramType[] = ["block", "flow", "context", "canvas", "mermaid"];
const PAYLOAD_FORMATS: PayloadFormat[] = ["mermaid", "plantuml", "json", "canvas_stroke"];

const DEFAULT_CONTENT: Record<PayloadFormat, string> = {
  mermaid:
    "graph TD\n  A[Start] --> B{Decision}\n  B -- yes --> C[Process]\n  B -- no --> D[End]",
  plantuml:
    "@startuml\n  actor User\n  User -> App : request\n  App --> User : response\n@enduml",
  json: JSON.stringify(
    {
      nodes: [
        { id: "n1", label: "Start" },
        { id: "n2", label: "End" },
      ],
      edges: [{ from: "n1", to: "n2" }],
    },
    null,
    2,
  ),
  // canvas_stroke diagrams use the CanvasEditor UI — no text content
  canvas_stroke: "",
};

interface FormState {
  name: string;
  diagram_type: DiagramType;
  payload_format: PayloadFormat;
  content: string;
  description: string;
}

const EMPTY_FORM: FormState = {
  name: "",
  diagram_type: "block",
  payload_format: "mermaid",
  content: DEFAULT_CONTENT.mermaid,
  description: "",
};

// ---------------------------------------------------------------------------
// DiagramView root — split-view (list left, detail/create right)
// ---------------------------------------------------------------------------

export default function DiagramView(): JSX.Element {
  const { t } = useTranslation();
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Diagram[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  // Split-pane resize state (REQ-002)
  const [leftPanelWidth, setLeftPanelWidth] = useState(280);
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);

  const loadList = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    setIsLoading(true);
    try {
      const resp = await diagramsApi.list(activeWorkspace.id);
      setItems(resp.results);
    } catch (err) {
      console.error("Failed to load diagrams", err);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace]);

  useEffect(() => {
    void loadList();
  }, [loadList]);

  const handleDelete = useCallback(
    async (diagramId: string): Promise<void> => {
      if (!window.confirm(t("diagrams.deleteConfirm", "Really delete this diagram?"))) {
        return;
      }
      try {
        await diagramsApi.delete(diagramId);
        await loadList();
        if (diagramId === id) navigate("/diagrams");
      } catch (err) {
        console.error("Failed to delete diagram", err);
      }
    },
    [id, loadList, navigate, t],
  );

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
    return <p role="status">{t("loading", "Loading...")}</p>;
  }

  return (
    <div
      style={{
        display: "flex",
        height: "100%",
        overflow: "hidden",
        fontFamily: "var(--font-sans)",
        color: "var(--color-text)",
      }}
    >
      {/* Diagram list (left panel) */}
      <div
        style={{
          width: `${leftPanelWidth}px`,
          minWidth: "280px",
          maxWidth: "70%",
          overflow: "auto",
          padding: "var(--space-4)",
        }}
      >
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
            {t("diagrams.title", "Diagrams")} ({items.length})
          </h3>
          <button
            type="button"
            data-testid="create-diagram-btn"
            onClick={() => setShowCreate((v) => !v)}
            style={formPrimaryButtonStyle}
          >
            + {t("actions.new", "New")}
          </button>
        </div>

        {items.length === 0 ? (
          <p
            data-testid="diagrams-empty"
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-sm)",
            }}
          >
            {t("diagrams.noItems", "No diagrams yet. Create one to get started.")}
          </p>
        ) : (
          <ul
            data-testid="diagrams-list"
            style={{ listStyle: "none", padding: 0, margin: 0 }}
          >
            {items.map((item) => {
              const isSelected = item.id === id && !showCreate;
              return (
                <li
                  key={item.id}
                  data-testid={`diagram-item-${item.id}`}
                  onClick={() => {
                    setShowCreate(false);
                    navigate(`/diagrams/${item.id}`);
                  }}
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    marginBottom: "var(--space-2)",
                    background: isSelected
                      ? "var(--color-surface-raised)"
                      : "var(--color-surface)",
                    borderRadius: "var(--radius-md)",
                    border: isSelected
                      ? "1px solid var(--color-primary)"
                      : "1px solid var(--color-border)",
                    cursor: "pointer",
                    transition: "var(--transition-fast)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    gap: "var(--space-3)",
                  }}
                >
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span
                      style={{
                        display: "block",
                        fontWeight: 600,
                        fontSize: "var(--font-size-base)",
                        color: "var(--color-text)",
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {item.name}
                    </span>
                    <span
                      style={{
                        fontSize: "var(--font-size-sm)",
                        color: "var(--color-text-muted)",
                      }}
                    >
                      {item.diagram_type}
                      {item.version_count !== undefined
                        ? ` · v${item.version_count}`
                        : ""}
                    </span>
                  </span>
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleDelete(item.id);
                    }}
                    style={{
                      background: "none",
                      border: "none",
                      color: "var(--color-text-muted)",
                      cursor: "pointer",
                      fontSize: "1.1rem",
                      lineHeight: 1,
                      fontFamily: "inherit",
                      flexShrink: 0,
                    }}
                    title={t("diagrams.delete", "Delete")}
                    aria-label={t("diagrams.delete", "Delete")}
                  >
                    ×
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      {/* Divider for split-pane resize */}
      <div
        onMouseDown={handleDividerMouseDown}
        data-testid="diagram-editor-divider"
        style={{
          width: "4px",
          backgroundColor: "var(--color-border)",
          cursor: "col-resize",
          userSelect: "none",
          transition: isDraggingRef.current
            ? "none"
            : "background-color var(--transition-fast)",
          flexShrink: 0,
        }}
        onMouseEnter={(e) => {
          (e.currentTarget as HTMLDivElement).style.backgroundColor =
            "var(--color-border-hover)";
        }}
        onMouseLeave={(e) => {
          if (!isDraggingRef.current) {
            (e.currentTarget as HTMLDivElement).style.backgroundColor =
              "var(--color-border)";
          }
        }}
      />

      {/* Detail / create form (right panel) */}
      <div
        style={{
          flex: 1,
          overflow: "auto",
          padding: "var(--space-4)",
          background: "var(--color-surface)",
        }}
      >
        {showCreate ? (
          <DiagramCreateForm
            onCreated={async (newId) => {
              setShowCreate(false);
              await loadList();
              navigate(`/diagrams/${newId}`);
            }}
            onCancel={() => setShowCreate(false)}
          />
        ) : id ? (
          <DiagramDetailView
            diagramId={id}
            onBack={() => navigate("/diagrams")}
            onChanged={loadList}
          />
        ) : (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-lg)",
              padding: "var(--space-8)",
              textAlign: "center",
            }}
          >
            {t("diagrams.selectDiagram", "Select a diagram from the list")}
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Create form (right panel content)
// ---------------------------------------------------------------------------

interface DiagramCreateFormProps {
  onCreated: (diagramId: string) => Promise<void> | void;
  onCancel: () => void;
}

function DiagramCreateForm({
  onCreated,
  onCancel,
}: DiagramCreateFormProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async (): Promise<void> => {
    if (!activeWorkspace) return;
    if (!form.name.trim()) {
      setError(t("diagrams.nameRequired", "Name is required."));
      return;
    }
    setIsSaving(true);
    setError(null);
    try {
      const created = await diagramsApi.create({
        workspace_id: activeWorkspace.id,
        name: form.name.trim(),
        diagram_type: form.diagram_type,
        payload_format: form.payload_format,
        content: form.content,
        description: form.description,
      });
      setForm(EMPTY_FORM);
      await onCreated(created.id);
    } catch (err) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div data-testid="diagram-create-form">
      <h3
        style={{
          fontSize: "var(--font-size-lg)",
          fontWeight: 700,
          marginTop: 0,
          marginBottom: "var(--space-4)",
          color: "var(--color-text)",
        }}
      >
        + {t("diagrams.create", "New Diagram")}
      </h3>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "var(--space-3)",
        }}
      >
        <label style={formLabelStyle}>
          {t("diagrams.name", "Name")}
          <input
            data-testid="diagram-name-input"
            type="text"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            style={formInputStyle}
          />
        </label>

        <label style={formLabelStyle}>
          {t("diagrams.type", "Type")}
          <select
            data-testid="diagram-type-select"
            value={form.diagram_type}
            onChange={(e) =>
              setForm({ ...form, diagram_type: e.target.value as DiagramType })
            }
            style={formInputStyle}
          >
            {DIAGRAM_TYPES.map((tp) => (
              <option key={tp} value={tp}>
                {t(`diagrams.type.${tp}`, tp)}
              </option>
            ))}
          </select>
        </label>

        <label style={formLabelStyle}>
          {t("diagrams.source", "Source Format")}
          <select
            data-testid="diagram-format-select"
            value={form.payload_format}
            onChange={(e) => {
              const fmt = e.target.value as PayloadFormat;
              setForm({
                ...form,
                payload_format: fmt,
                content: DEFAULT_CONTENT[fmt],
              });
            }}
            style={formInputStyle}
          >
            {PAYLOAD_FORMATS.map((fmt) => (
              <option key={fmt} value={fmt}>
                {fmt}
              </option>
            ))}
          </select>
        </label>

        <label style={formLabelStyle}>
          {t("diagrams.description", "Description")}
          <input
            data-testid="diagram-description-input"
            type="text"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            style={formInputStyle}
          />
        </label>

        <label style={{ ...formLabelStyle, gridColumn: "1 / -1" }}>
          {t("diagrams.source", "Source")}
          <textarea
            data-testid="diagram-source-textarea"
            value={form.content}
            onChange={(e) => setForm({ ...form, content: e.target.value })}
            rows={8}
            style={{
              ...formInputStyle,
              fontFamily: "var(--font-mono)",
              fontSize: "var(--font-size-sm)",
              resize: "vertical",
            }}
          />
        </label>

        {error && (
          <div
            data-testid="diagram-create-error"
            role="alert"
            style={{
              gridColumn: "1 / -1",
              color: "var(--color-danger)",
              fontSize: "var(--font-size-sm)",
            }}
          >
            {error}
          </div>
        )}

        <div
          style={{
            gridColumn: "1 / -1",
            display: "flex",
            gap: "var(--space-2)",
            justifyContent: "flex-end",
          }}
        >
          <button
            type="button"
            onClick={() => {
              setForm(EMPTY_FORM);
              setError(null);
              onCancel();
            }}
            style={formCancelButtonStyle}
          >
            {t("actions.cancel", "Cancel")}
          </button>
          <button
            type="button"
            data-testid="diagram-save-btn"
            onClick={() => void handleCreate()}
            disabled={isSaving || !form.name.trim()}
            style={{
              ...formPrimaryButtonStyle,
              opacity: isSaving || !form.name.trim() ? 0.6 : 1,
              cursor: isSaving || !form.name.trim() ? "not-allowed" : "pointer",
            }}
          >
            {isSaving ? t("actions.saving", "Saving...") : t("actions.save", "Save")}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail view (right panel content)
// ---------------------------------------------------------------------------

interface DiagramDetailViewProps {
  diagramId: string;
  onBack: () => void;
  onChanged: () => Promise<void> | void;
}

function DiagramDetailView({
  diagramId,
  onBack,
  onChanged,
}: DiagramDetailViewProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [detail, setDetail] = useState<DiagramDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editContent, setEditContent] = useState("");
  const [traceLinks, setTraceLinks] = useState<DiagramTraceLink[]>([]);
  const [traceReloadKey, setTraceReloadKey] = useState(0);
  const [requirements, setRequirements] = useState<Requirement[]>([]);
  const [architectureElements, setArchitectureElements] = useState<
    ArchitectureElement[]
  >([]);

  // Create-link form (REQ-L2-DS-004) — links this diagram to a Requirement
  // or Architecture Element via the "documents" trace-link type. Previously
  // the panel only displayed existing links with no way to create new ones.
  const [showLinkForm, setShowLinkForm] = useState(false);
  const [linkTargetId, setLinkTargetId] = useState("");
  const [isLinking, setIsLinking] = useState(false);
  const [linkError, setLinkError] = useState<string | null>(null);

  // Code/Visual toggle (REQ-L1-057) — mermaid sources can be rendered
  // client-side via mermaid.js; other payload formats stay code-only.
  const [viewMode, setViewMode] = useState<"code" | "visual">("visual");
  const [renderedSvg, setRenderedSvg] = useState<string>("");
  const [renderError, setRenderError] = useState<string>("");

  useEffect(() => {
    setIsLoading(true);
    setDetail(null);
    setViewMode("visual");
    diagramsApi
      .get(diagramId)
      .then((d) => {
        setDetail(d);
        setEditContent(d.content ?? "");
      })
      .catch((err) => console.error("Failed to load diagram", err))
      .finally(() => setIsLoading(false));
  }, [diagramId]);

  const canRenderVisual = detail?.payload_format === "mermaid";
  const activeSource = isEditing ? editContent : (detail?.content ?? "");

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

  // Load traceability + requirement/architecture titles for lookup
  useEffect(() => {
    if (!activeWorkspace) return;
    let cancelled = false;
    (async (): Promise<void> => {
      try {
        const [reqResp, archResp] = await Promise.all([
          requirementsApi.list(activeWorkspace.id).catch(() => null),
          architectureApi.list(activeWorkspace.id).catch(() => null),
        ]);
        if (cancelled) return;
        const reqList = reqResp?.results ?? [];
        const archList = archResp?.results ?? [];
        if (!cancelled) {
          setRequirements(reqList);
          setArchitectureElements(archList);
        }
        const reqMap = new Map<string, string>();
        reqList.forEach((r: Requirement) => reqMap.set(r.id, r.title));
        const archMap = new Map<string, string>();
        archList.forEach((a: ArchitectureElement) => archMap.set(a.id, a.title));
        const links = await diagramsApi.getTraceability(
          activeWorkspace.id,
          diagramId,
          (id) => reqMap.get(id),
          (id) => archMap.get(id),
        );
        if (!cancelled) setTraceLinks(links);
      } catch (err) {
        if (!cancelled) console.error("Failed to load traceability", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace, diagramId, traceReloadKey]);

  const handleCreateLink = async (): Promise<void> => {
    if (!linkTargetId) {
      setLinkError(t("traceability.targetRequired"));
      return;
    }
    setIsLinking(true);
    setLinkError(null);
    try {
      await tracelinksApi.create({
        source_id: diagramId,
        target_id: linkTargetId,
        link_type: "documents",
      });
      setShowLinkForm(false);
      setLinkTargetId("");
      setTraceReloadKey((k) => k + 1);
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setLinkError(msg);
    } finally {
      setIsLinking(false);
    }
  };

  const handleSave = async (): Promise<void> => {
    if (!detail) return;
    if (!detail.payload_format) return;
    setIsSaving(true);
    setError(null);
    try {
      await diagramsApi.update(diagramId, {
        payload_format: detail.payload_format,
        content: editContent,
      });
      // Refresh full detail
      const updated = await diagramsApi.get(diagramId);
      setDetail(updated);
      setEditContent(updated.content ?? "");
      setIsEditing(false);
      await onChanged();
    } catch (err) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (): Promise<void> => {
    if (!window.confirm(t("diagrams.deleteConfirm", "Really delete this diagram?"))) {
      return;
    }
    try {
      await diagramsApi.delete(diagramId);
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
              onClick={() => setIsEditing(true)}
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
                  setError(null);
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

        {error && (
          <p
            role="alert"
            data-testid="diagram-detail-error"
            style={{ color: "var(--color-danger)", marginBottom: "var(--space-3)" }}
          >
            {error}
          </p>
        )}

        {/* Canvas diagrams use the CanvasEditor surface (REQ-L2-DS-006, IF-L1-058/060) */}
        {detail.payload_format === "canvas_stroke" ? (
          <div
            data-testid="diagram-canvas-section"
            style={{ minHeight: "520px", display: "flex", flexDirection: "column" }}
          >
            <CanvasEditor
              diagramId={diagramId}
              onAutoSave={(strokes) => {
                // Optimistically mark diagram as having saved content
                console.debug("Canvas auto-saved", strokes.length, "strokes");
              }}
            />
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

      <aside
        data-testid="diagram-traceability-panel"
        style={{
          width: "300px",
          padding: "var(--space-4)",
          background: "var(--color-surface-raised)",
          borderRadius: "var(--radius-lg)",
          border: "1px solid var(--color-border)",
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
          <h3
            style={{
              fontSize: "var(--font-size-lg)",
              fontWeight: 600,
              margin: 0,
              color: "var(--color-text)",
            }}
          >
            {t("diagrams.traceability", "Traceability")}
          </h3>
          {!showLinkForm && (
            <button
              type="button"
              data-testid="diagram-link-create-btn"
              onClick={() => {
                setLinkTargetId("");
                setLinkError(null);
                setShowLinkForm(true);
              }}
              style={{
                ...formPrimaryButtonStyle,
                padding: "var(--space-1) var(--space-2)",
                fontSize: "var(--font-size-sm)",
              }}
            >
              + {t("traceability.create")}
            </button>
          )}
        </div>

        {showLinkForm && (
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-2)",
              marginBottom: "var(--space-3)",
              padding: "var(--space-3)",
              background: "var(--color-surface)",
              borderRadius: "var(--radius-md)",
              border: "1px solid var(--color-border)",
            }}
          >
            <label style={formLabelStyle}>
              {t("traceability.target")}
              <select
                data-testid="diagram-link-target-select"
                value={linkTargetId}
                onChange={(e) => setLinkTargetId(e.target.value)}
                disabled={isLinking}
                style={formInputStyle}
              >
                <option value="">—</option>
                {requirements.length > 0 && (
                  <optgroup label={t("nav.requirements", "Requirements")}>
                    {requirements.map((r) => (
                      <option key={r.id} value={r.id}>
                        {r.title || t("editor.untitled")}
                      </option>
                    ))}
                  </optgroup>
                )}
                {architectureElements.length > 0 && (
                  <optgroup label={t("nav.architecture", "Architecture")}>
                    {architectureElements.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.title || t("editor.untitled")}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
            </label>

            {linkError && (
              <p role="alert" style={{ color: "var(--color-danger)", fontSize: "var(--font-size-sm)", margin: 0 }}>
                {linkError}
              </p>
            )}

            <div style={{ display: "flex", gap: "var(--space-2)", justifyContent: "flex-end" }}>
              <button
                type="button"
                data-testid="diagram-link-cancel-btn"
                onClick={() => setShowLinkForm(false)}
                disabled={isLinking}
                style={formCancelButtonStyle}
              >
                {t("actions.cancel", "Cancel")}
              </button>
              <button
                type="button"
                data-testid="diagram-link-save-btn"
                onClick={() => void handleCreateLink()}
                disabled={isLinking || !linkTargetId}
                style={{
                  ...formPrimaryButtonStyle,
                  opacity: isLinking || !linkTargetId ? 0.6 : 1,
                }}
              >
                {isLinking ? t("traceability.submitting") : t("traceability.submit")}
              </button>
            </div>
          </div>
        )}

        {traceLinks.length === 0 ? (
          <p
            data-testid="diagram-traceability-empty"
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-sm)",
              margin: 0,
            }}
          >
            {t(
              "diagrams.noTraceLinks",
              "No artifacts are linked to this diagram yet.",
            )}
          </p>
        ) : (
          <ul
            style={{
              listStyle: "none",
              padding: 0,
              margin: 0,
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-2)",
            }}
          >
            {traceLinks.map((link) => (
              <li
                key={link.id}
                data-testid="diagram-trace-link"
                style={{
                  padding: "var(--space-2) var(--space-3)",
                  borderRadius: "var(--radius-md)",
                  background: "var(--color-surface)",
                  border: "1px solid var(--color-border)",
                }}
              >
                <div
                  style={{
                    fontSize: "var(--font-size-sm)",
                    fontWeight: 600,
                    color: "var(--color-text)",
                    wordBreak: "break-word",
                  }}
                >
                  {link.target_title}
                </div>
                <div
                  style={{
                    fontSize: "0.7rem",
                    color: "var(--color-text-muted)",
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    marginTop: "2px",
                  }}
                >
                  {link.link_type}
                </div>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers / shared style snippets
// ---------------------------------------------------------------------------

function diagramVersionLabel(n: number): string {
  // 0 means "no version yet" — show as "—"
  return n > 0 ? String(n) : "—";
}

const formLabelStyle = {
  display: "flex",
  flexDirection: "column" as const,
  gap: "var(--space-1)",
  fontWeight: 500,
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const formInputStyle = {
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  background: "var(--color-surface)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
  fontFamily: "inherit",
  boxSizing: "border-box" as const,
};

const formPrimaryButtonStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-4)",
  background: "var(--color-primary)",
  color: "white",
  border: "none",
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  fontWeight: 600,
  fontFamily: "inherit",
};

const formCancelButtonStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-4)",
  background: "transparent",
  color: "var(--color-text-muted)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  fontFamily: "inherit",
};

const formDangerButtonStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-4)",
  background: "transparent",
  color: "var(--color-danger, #ef4444)",
  border: "1px solid var(--color-danger, #ef4444)",
  borderRadius: "var(--radius-md)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  fontFamily: "inherit",
};
