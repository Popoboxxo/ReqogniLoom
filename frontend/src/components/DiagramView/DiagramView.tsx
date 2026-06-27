/**
 * ARCH-L1-001 ReactFrontend — DiagramView (COMP-RF-005).
 *
 * leaf_id: COMP-RF-005 (DiagramView)
 * req_id:  REQ-L0-016 (Interaktive Diagramme und Grafiken),
 *          REQ-L2-DS-001 (DiagramService REST API),
 *          REQ-L2-DS-004 (Traceability connector)
 *
 * Provides list/detail/create/edit of diagrams and a traceability sidebar
 * showing the artifacts (Requirements / ArchitectureElements) documented by
 * the selected diagram.
 *
 * Rendering: the source is shown as a monospaced pre/code block. The full
 * Mermaid/PlantUML rendering is out of scope for this iteration — the editor
 * surface stays source-of-truth so the next iteration can drop in a
 * Mermaid/PlantUML renderer without changing the data model.
 */

import { useCallback, useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { diagramsApi } from "../../api/diagrams";
import { requirementsApi } from "../../api/requirements";
import { architectureApi } from "../../api/architecture";
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

const DIAGRAM_TYPES: DiagramType[] = ["block", "flow", "context"];
const PAYLOAD_FORMATS: PayloadFormat[] = ["mermaid", "plantuml", "json"];

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
// DiagramView root
// ---------------------------------------------------------------------------

export default function DiagramView(): JSX.Element {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Diagram[]>([]);
  const [isLoading, setIsLoading] = useState(true);

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

  // Detail view when an :id is present
  if (id) {
    return (
      <DiagramDetailView
        diagramId={id}
        onBack={() => navigate("/diagrams")}
        onChanged={loadList}
      />
    );
  }

  // List view (also hosts the create form)
  return (
    <DiagramListView
      items={items}
      isLoading={isLoading}
      onCreated={loadList}
      onDeleted={loadList}
      onSelect={(diagramId) => navigate(`/diagrams/${diagramId}`)}
    />
  );
}

// ---------------------------------------------------------------------------
// List view
// ---------------------------------------------------------------------------

interface DiagramListViewProps {
  items: Diagram[];
  isLoading: boolean;
  onCreated: () => Promise<void> | void;
  onDeleted: () => Promise<void> | void;
  onSelect: (diagramId: string) => void;
}

function DiagramListView({
  items,
  isLoading,
  onCreated,
  onDeleted,
  onSelect,
}: DiagramListViewProps): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [showCreate, setShowCreate] = useState(false);
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
      await diagramsApi.create({
        workspace_id: activeWorkspace.id,
        name: form.name.trim(),
        diagram_type: form.diagram_type,
        payload_format: form.payload_format,
        content: form.content,
        description: form.description,
      });
      setForm(EMPTY_FORM);
      setShowCreate(false);
      await onCreated();
    } catch (err) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setError(msg);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (diagramId: string): Promise<void> => {
    try {
      await diagramsApi.delete(diagramId);
      await onDeleted();
    } catch (err) {
      console.error("Failed to delete diagram", err);
    }
  };

  return (
    <div>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "var(--space-6)",
        }}
      >
        <h2
          style={{
            fontSize: "var(--font-size-2xl)",
            fontWeight: 700,
            color: "var(--color-text)",
            margin: 0,
          }}
        >
          {t("diagrams.title", "Diagrams")}
        </h2>
        <button
          type="button"
          data-testid="create-diagram-btn"
          onClick={() => setShowCreate((v) => !v)}
          style={{
            padding: "var(--space-2) var(--space-4)",
            background: "var(--color-primary)",
            color: "white",
            border: "none",
            borderRadius: "var(--radius-md)",
            cursor: "pointer",
            fontSize: "var(--font-size-sm)",
            fontWeight: 600,
            fontFamily: "inherit",
          }}
        >
          + {t("diagrams.create", "New Diagram")}
        </button>
      </div>

      {showCreate && (
        <div
          data-testid="diagram-create-form"
          style={{
            padding: "var(--space-4)",
            marginBottom: "var(--space-4)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px solid var(--color-border)",
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
              onChange={(e) =>
                setForm({ ...form, description: e.target.value })
              }
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
                setShowCreate(false);
                setForm(EMPTY_FORM);
                setError(null);
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
      )}

      {isLoading ? (
        <p>{t("loading", "Loading...")}</p>
      ) : items.length === 0 ? (
        <p
          data-testid="diagrams-empty"
          style={{
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px dashed var(--color-border)",
            textAlign: "center",
          }}
        >
          {t("diagrams.noItems", "No diagrams yet. Create one to get started.")}
        </p>
      ) : (
        <ul
          data-testid="diagrams-list"
          style={{ listStyle: "none", padding: 0, margin: 0 }}
        >
          {items.map((item) => (
            <li
              key={item.id}
              data-testid={`diagram-item-${item.id}`}
              style={{
                padding: "var(--space-3) var(--space-4)",
                marginBottom: "var(--space-2)",
                background: "var(--color-surface)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                gap: "var(--space-3)",
              }}
            >
              <button
                type="button"
                onClick={() => onSelect(item.id)}
                style={{
                  flex: 1,
                  textAlign: "left",
                  background: "none",
                  border: "none",
                  padding: 0,
                  cursor: "pointer",
                  fontFamily: "inherit",
                  color: "var(--color-text)",
                }}
              >
                <div style={{ fontWeight: 600, fontSize: "var(--font-size-base)" }}>
                  {item.name}
                </div>
                <div
                  style={{
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text-muted)",
                    marginTop: "2px",
                  }}
                >
                  {item.diagram_type}
                  {item.version_count !== undefined
                    ? ` · v${item.version_count}`
                    : ""}
                </div>
              </button>
              <button
                type="button"
                onClick={() => void handleDelete(item.id)}
                style={{
                  background: "none",
                  border: "none",
                  color: "var(--color-text-muted)",
                  cursor: "pointer",
                  fontSize: "1.1rem",
                  lineHeight: 1,
                  fontFamily: "inherit",
                }}
                title={t("diagrams.delete", "Delete")}
                aria-label={t("diagrams.delete", "Delete")}
              >
                ×
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Detail view
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

  useEffect(() => {
    setIsLoading(true);
    setDetail(null);
    diagramsApi
      .get(diagramId)
      .then((d) => {
        setDetail(d);
        setEditContent(d.content ?? "");
      })
      .catch((err) => console.error("Failed to load diagram", err))
      .finally(() => setIsLoading(false));
  }, [diagramId]);

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
        const reqMap = new Map<string, string>();
        (reqResp?.results ?? []).forEach((r: Requirement) =>
          reqMap.set(r.id, r.title),
        );
        const archMap = new Map<string, string>();
        (archResp?.results ?? []).forEach((a: ArchitectureElement) =>
          archMap.set(a.id, a.title),
        );
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
  }, [activeWorkspace, diagramId]);

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
        <button type="button" onClick={onBack} style={backLinkStyle}>
          ← {t("actions.back", "Back")}
        </button>
        <p>{t("diagrams.notFound", "Diagram not found.")}</p>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", gap: "var(--space-6)", alignItems: "flex-start" }}>
      <div style={{ flex: 1 }}>
        <button type="button" onClick={onBack} style={backLinkStyle}>
          ← {t("actions.back", "Back")}
        </button>

        <h2
          style={{
            fontSize: "var(--font-size-2xl)",
            fontWeight: 700,
            color: "var(--color-text)",
            marginTop: "var(--space-2)",
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

        {isEditing ? (
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
        <h3
          style={{
            fontSize: "var(--font-size-lg)",
            fontWeight: 600,
            marginTop: 0,
            marginBottom: "var(--space-3)",
            color: "var(--color-text)",
          }}
        >
          {t("diagrams.traceability", "Traceability")}
        </h3>
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

const backLinkStyle: React.CSSProperties = {
  background: "none",
  border: "none",
  color: "var(--color-primary)",
  cursor: "pointer",
  fontSize: "var(--font-size-sm)",
  padding: 0,
  marginBottom: "var(--space-3)",
  fontFamily: "inherit",
};
