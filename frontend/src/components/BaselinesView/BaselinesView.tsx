/**
 * ARCH-L1-001 ReactFrontend — BaselinesView.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — gated by preset)
 * req_id:  REQ-L1-018 (Baselines),
 *          REQ-L1-049 (Baseline scope-select with 3 scopes),
 *          REQ-L2-RF-007 (Preset-basierte Sichtbarkeit — Baselines gated),
 *          REQ-002 (Split-View Layout)
 *
 * Split-View layout with resizable divider:
 *   - Left panel: baseline list + create button
 *   - Divider: 4px resizable
 *   - Right panel: create form OR baseline detail (scope, artifact, created)
 *
 * Hidden in Minimal preset (gated upstream by NavigationShell).
 *
 * Interfaces consumed:
 *   IF-RF-EXT-OUT-001 → GET/POST/DELETE /api/v1/baselines/
 *   IF-RF-EXT-OUT-001 → GET /api/v1/artifacts/ (artifact picker for create form)
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  baselinesApi,
  type Baseline,
  type BaselineScope,
  type ScopePreview,
} from "../../api/baselines";
import { artifactsApi } from "../../api/artifacts";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { Artifact } from "../../types";

interface BaselinesState {
  baselines: Baseline[];
  artifacts: Artifact[];
  isLoading: boolean;
  error: string | null;
}

const INITIAL_STATE: BaselinesState = {
  baselines: [],
  artifacts: [],
  isLoading: true,
  error: null,
};

// REQ-L1-049: only these three scopes are valid. The order is intentional
// (most common first) and matches the i18n key ordering in the locales.
const SCOPE_OPTIONS: { value: BaselineScope; labelKey: string }[] = [
  { value: "document", labelKey: "baselines.scopeDocument" },
  { value: "project", labelKey: "baselines.scopeProject" },
  { value: "global", labelKey: "baselines.scopeGlobal" },
];

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString();
  } catch {
    return iso;
  }
}

export default function BaselinesView(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [state, setState] = useState<BaselinesState>(INITIAL_STATE);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formArtifactId, setFormArtifactId] = useState<string>("");
  // REQ-L1-049: scope is now one of {document, project, global}; default
  // is "project" to match the backend model default.
  const [formScope, setFormScope] = useState<BaselineScope>("project");
  const [isSaving, setIsSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // REQ-L1-049: live count of items that would be included for the chosen
  // scope. ``null`` means "not yet loaded" (or "not applicable").
  const [scopePreview, setScopePreview] = useState<ScopePreview | null>(null);
  const [scopePreviewLoading, setScopePreviewLoading] = useState(false);
  const [scopePreviewError, setScopePreviewError] = useState<string | null>(
    null
  );

  // Split-pane resize state (REQ-002)
  const [leftPanelWidth, setLeftPanelWidth] = useState(300);
  const isDraggingRef = useRef(false);
  const dragStartXRef = useRef(0);
  const dragStartWidthRef = useRef(0);

  const load = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) {
      setState({ baselines: [], artifacts: [], isLoading: false, error: null });
      return;
    }
    setState((prev) => ({ ...prev, isLoading: true, error: null }));
    try {
      const [blResp, artResp] = await Promise.all([
        baselinesApi.list(activeWorkspace.id),
        artifactsApi.list(activeWorkspace.id),
      ]);
      setState({
        baselines: blResp.results,
        artifacts: artResp.results,
        isLoading: false,
        error: null,
      });
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setState({ baselines: [], artifacts: [], isLoading: false, error: msg });
    }
  }, [activeWorkspace]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (cancelled) return;
      await load();
    })();
    return () => {
      cancelled = true;
    };
  }, [load]);

  // When form opens, default to the first available artifact.
  useEffect(() => {
    if (showForm && !formArtifactId && state.artifacts.length > 0) {
      setFormArtifactId(state.artifacts[0].id);
    }
  }, [showForm, formArtifactId, state.artifacts]);

  // REQ-L1-049: refetch the scope preview whenever the user picks a
  // different scope, switches the artifact, or the active workspace
  // changes. For ``document`` scope we require an artifact; for the other
  // scopes we issue a single GET with the workspace_id.
  useEffect(() => {
    if (!showForm || !activeWorkspace) {
      setScopePreview(null);
      return;
    }
    if (formScope === "document" && !formArtifactId) {
      setScopePreview(null);
      setScopePreviewError(null);
      return;
    }
    let cancelled = false;
    setScopePreviewLoading(true);
    setScopePreviewError(null);
    void (async () => {
      try {
        const result = await baselinesApi.previewScope({
          scope: formScope,
          workspaceId: activeWorkspace.id,
          artifactId: formScope === "document" ? formArtifactId : null,
        });
        if (!cancelled) {
          setScopePreview(result);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const msg =
            (err as { error?: { message?: string } })?.error?.message ??
            String(err);
          setScopePreviewError(msg);
          setScopePreview(null);
        }
      } finally {
        if (!cancelled) {
          setScopePreviewLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [showForm, activeWorkspace, formScope, formArtifactId]);

  const handleCreate = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) return;
    // REQ-L1-049: ``document`` scope requires an artifact.
    if (formScope === "document" && !formArtifactId) {
      setCreateError(t("baselines.artifactRequired"));
      return;
    }
    setIsSaving(true);
    setCreateError(null);
    try {
      const created = await baselinesApi.create({
        workspace_id: activeWorkspace.id,
        // ``project`` / ``global`` scopes send ``artifact_id: null``; the
        // backend now requires the value only for ``document``.
        artifact_id: formScope === "document" ? formArtifactId : null,
        scope: formScope,
      });
      setShowForm(false);
      setFormArtifactId("");
      setFormScope("project");
      setScopePreview(null);
      await load();
      setSelectedId(created.id);
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setCreateError(msg);
    } finally {
      setIsSaving(false);
    }
  }, [activeWorkspace, formArtifactId, formScope, t, load]);

  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      if (!window.confirm(t("baselines.deleteConfirm", "Really delete this baseline?"))) {
        return;
      }
      try {
        await baselinesApi.delete(id);
        if (selectedId === id) setSelectedId(null);
        await load();
      } catch (err: unknown) {
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setState((prev) => ({ ...prev, error: msg }));
      }
    },
    [load, selectedId, t]
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

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (state.isLoading) {
    return (
      <div data-testid="baselines-view">
        <p
          role="status"
          style={{
            fontSize: "var(--font-size-base)",
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
          }}
        >
          {t("loading")}
        </p>
      </div>
    );
  }

  if (state.error) {
    return (
      <div
        data-testid="baselines-view"
        role="alert"
        style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-danger)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-6)",
          boxShadow: "var(--shadow-card)",
          maxWidth: "480px",
        }}
      >
        <p style={{ color: "var(--color-danger)", margin: 0 }}>{state.error}</p>
        <button
          onClick={() => void load()}
          style={{
            marginTop: "var(--space-4)",
            background: "var(--color-primary)",
            color: "var(--color-surface)",
            border: "none",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-2) var(--space-4)",
            cursor: "pointer",
          }}
        >
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  const selectedBaseline =
    state.baselines.find((bl) => bl.id === selectedId) ?? null;

  return (
    <div
      data-testid="baselines-view"
      style={{
        display: "flex",
        height: "100%",
        overflow: "hidden",
        fontFamily: "var(--font-sans)",
        color: "var(--color-text)",
      }}
    >
      {/* Baseline list (left panel) */}
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
            {t("nav.baselines")} ({state.baselines.length})
          </h3>
          <button
            data-testid="create-baseline-btn"
            onClick={() => setShowForm((v) => !v)}
            style={{
              background: "var(--color-primary)",
              color: "white",
              border: "none",
              borderRadius: "var(--radius-md)",
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-sm)",
              fontWeight: 600,
              cursor: "pointer",
              transition: "var(--transition-fast)",
            }}
          >
            {showForm ? t("actions.cancel") : `+ ${t("baselines.create")}`}
          </button>
        </div>

        {state.baselines.length === 0 ? (
          <p
            data-testid="baselines-empty"
            style={{
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
            }}
          >
            {t("baselines.empty")}
          </p>
        ) : (
          <ul
            data-testid="baseline-list"
            style={{ listStyle: "none", padding: 0, margin: 0 }}
          >
            {state.baselines.map((bl) => {
              const isSelected = bl.id === selectedId && !showForm;
              return (
                <li
                  key={bl.id}
                  data-testid="baseline-item"
                  onClick={() => {
                    setShowForm(false);
                    setSelectedId(bl.id);
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
                  }}
                >
                  <strong
                    style={{
                      display: "block",
                      color: "var(--color-text)",
                      fontFamily: "monospace",
                      fontSize: "var(--font-size-sm)",
                    }}
                  >
                    {bl.id.slice(0, 8)}…
                  </strong>
                  <span
                    style={{
                      color: "var(--color-text-muted)",
                      fontSize: "var(--font-size-sm)",
                    }}
                  >
                    {bl.scope} | {formatDate(bl.created_at)}
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
        data-testid="baseline-editor-divider"
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
        {showForm ? (
          <div data-testid="create-baseline-form" style={{ maxWidth: "560px" }}>
            <h3
              style={{
                fontSize: "var(--font-size-lg)",
                fontWeight: 700,
                marginTop: 0,
                marginBottom: "var(--space-4)",
                color: "var(--color-text)",
              }}
            >
              + {t("baselines.create")}
            </h3>
            <label
              htmlFor="baseline-scope"
              style={{
                display: "block",
                fontWeight: 500,
                color: "var(--color-text)",
                marginBottom: "var(--space-1)",
              }}
            >
              {t("baselines.scope")}
            </label>
            {/* REQ-L1-049: radio group with the three valid scopes. */}
            <div
              data-testid="baseline-scope-group"
              style={{
                display: "flex",
                flexDirection: "column",
                gap: "var(--space-2)",
                marginBottom: "var(--space-3)",
              }}
            >
              {SCOPE_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  htmlFor={`baseline-scope-${opt.value}`}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: "var(--space-2)",
                    cursor: "pointer",
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text)",
                  }}
                >
                  <input
                    id={`baseline-scope-${opt.value}`}
                    data-testid={`baseline-scope-${opt.value}`}
                    type="radio"
                    name="baseline-scope"
                    value={opt.value}
                    checked={formScope === opt.value}
                    onChange={() => setFormScope(opt.value)}
                  />
                  <span>{t(opt.labelKey)}</span>
                </label>
              ))}
            </div>

            {/* REQ-L1-049: live count of items that would be included for
                the chosen scope. Re-fetches on scope/artifact change. */}
            <p
              data-testid="baseline-scope-count"
              aria-live="polite"
              style={{
                fontSize: "var(--font-size-sm)",
                color: scopePreviewError
                  ? "var(--color-danger)"
                  : "var(--color-text-muted)",
                margin: "0 0 var(--space-4) 0",
              }}
            >
              {scopePreviewError
                ? scopePreviewError
                : scopePreviewLoading
                  ? t("baselines.scopeCountLoading")
                  : scopePreview
                    ? t("baselines.scopeCountReady", {
                        count: scopePreview.count,
                      })
                    : formScope === "document" && !formArtifactId
                      ? t("baselines.scopeCountNeedsArtifact")
                      : t("baselines.scopeCountIdle")}
            </p>

            {/* REQ-L1-049: artifact picker is shown only for document scope. */}
            {formScope === "document" && (
              <>
                <label
                  htmlFor="baseline-artifact"
                  style={{
                    display: "block",
                    fontWeight: 500,
                    color: "var(--color-text)",
                    marginBottom: "var(--space-1)",
                  }}
                >
                  {t("baselines.artifact")}
                </label>
                <select
                  id="baseline-artifact"
                  data-testid="baseline-artifact-select"
                  value={formArtifactId}
                  onChange={(e) => setFormArtifactId(e.target.value)}
                  disabled={state.artifacts.length === 0}
                  style={{
                    width: "100%",
                    border: "1px solid var(--color-border)",
                    borderRadius: "var(--radius-md)",
                    padding: "var(--space-3)",
                    fontSize: "var(--font-size-base)",
                    marginBottom: "var(--space-4)",
                    background: "var(--color-surface)",
                    color: "var(--color-text)",
                  }}
                >
                  {state.artifacts.length === 0 ? (
                    <option value="">{t("baselines.noArtifacts")}</option>
                  ) : (
                    state.artifacts.map((a) => (
                      <option key={a.id} value={a.id}>
                        {a.artifact_type} — {a.id.slice(0, 8)}…
                      </option>
                    ))
                  )}
                </select>
              </>
            )}

            {createError && (
              <p
                role="alert"
                style={{
                  color: "var(--color-danger)",
                  fontSize: "var(--font-size-sm)",
                  margin: "0 0 var(--space-3) 0",
                }}
              >
                {createError}
              </p>
            )}

            <div style={{ display: "flex", gap: "var(--space-3)" }}>
              <button
                data-testid="baseline-submit-btn"
                onClick={() => void handleCreate()}
                disabled={
                  isSaving ||
                  (formScope === "document" && !formArtifactId)
                }
                style={{
                  background: "var(--color-primary)",
                  color: "white",
                  border: "none",
                  borderRadius: "var(--radius-md)",
                  padding: "var(--space-2) var(--space-6)",
                  fontSize: "var(--font-size-sm)",
                  cursor:
                    isSaving || (formScope === "document" && !formArtifactId)
                      ? "not-allowed"
                      : "pointer",
                  opacity:
                    isSaving || (formScope === "document" && !formArtifactId)
                      ? 0.7
                      : 1,
                }}
              >
                {isSaving ? t("actions.saving") : t("actions.save")}
              </button>
              <button
                onClick={() => {
                  setShowForm(false);
                  setCreateError(null);
                }}
                style={{
                  background: "transparent",
                  color: "var(--color-text)",
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  padding: "var(--space-2) var(--space-6)",
                  fontSize: "var(--font-size-sm)",
                  cursor: "pointer",
                }}
              >
                {t("actions.cancel")}
              </button>
            </div>
          </div>
        ) : selectedBaseline ? (
          <div data-testid="baseline-detail" style={{ maxWidth: "640px" }}>
            <h2
              style={{
                fontSize: "var(--font-size-2xl)",
                fontWeight: 700,
                color: "var(--color-text)",
                marginTop: 0,
                marginBottom: "var(--space-4)",
                fontFamily: "monospace",
              }}
            >
              {selectedBaseline.id.slice(0, 8)}…
            </h2>

            <dl
              style={{
                display: "grid",
                gridTemplateColumns: "160px 1fr",
                rowGap: "var(--space-3)",
                columnGap: "var(--space-4)",
                margin: 0,
                marginBottom: "var(--space-6)",
              }}
            >
              <dt style={detailTermStyle}>{t("baselines.id")}</dt>
              <dd style={detailValueStyle}>
                <code style={{ fontFamily: "monospace" }}>
                  {selectedBaseline.id}
                </code>
              </dd>

              <dt style={detailTermStyle}>{t("baselines.scope")}</dt>
              <dd style={detailValueStyle}>{selectedBaseline.scope}</dd>

              <dt style={detailTermStyle}>{t("baselines.artifact")}</dt>
              <dd style={detailValueStyle}>
                {selectedBaseline.artifact_id ? (
                  <code style={{ fontFamily: "monospace" }}>
                    {selectedBaseline.artifact_id}
                  </code>
                ) : (
                  "—"
                )}
              </dd>

              <dt style={detailTermStyle}>{t("baselines.created")}</dt>
              <dd style={detailValueStyle}>
                {formatDate(selectedBaseline.created_at)}
              </dd>
            </dl>

            <button
              type="button"
              data-testid="baseline-delete-btn"
              onClick={() => void handleDelete(selectedBaseline.id)}
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
        ) : (
          <p
            style={{
              color: "var(--color-text-muted)",
              fontSize: "var(--font-size-lg)",
              padding: "var(--space-8)",
              textAlign: "center",
            }}
          >
            {t("baselines.selectBaseline")}
          </p>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Style snippets
// ---------------------------------------------------------------------------

const detailTermStyle: React.CSSProperties = {
  fontWeight: 600,
  color: "var(--color-text-muted)",
  fontSize: "var(--font-size-sm)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
};

const detailValueStyle: React.CSSProperties = {
  margin: 0,
  color: "var(--color-text)",
  fontSize: "var(--font-size-base)",
  wordBreak: "break-all",
};
