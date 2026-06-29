/**
 * ARCH-L1-001 ReactFrontend — BaselinesView.
 *
 * leaf_id: COMP-RF-001 (NavigationShell — gated by preset)
 * req_id:  REQ-L1-018 (Baselines),
 *          REQ-L2-RF-007 (Preset-basierte Sichtbarkeit — Baselines gated)
 *
 * Lists baselines for the active workspace and lets users create new ones.
 * Hidden in Minimal preset (gated upstream by NavigationShell).
 *
 * Interfaces consumed:
 *   IF-RF-EXT-OUT-001 → GET/POST /api/v1/baselines/
 *   IF-RF-EXT-OUT-001 → GET /api/v1/artifacts/ (artifact picker for create form)
 */

import React, { useCallback, useEffect, useState } from "react";
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
      await baselinesApi.create({
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
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setCreateError(msg);
    } finally {
      setIsSaving(false);
    }
  }, [activeWorkspace, formArtifactId, formScope, t, load]);

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

  return (
    <div data-testid="baselines-view">
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
          {t("nav.baselines")}
        </h2>
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
            cursor: "pointer",
            transition: "var(--transition-fast)",
          }}
        >
          {showForm ? t("actions.cancel") : `+ ${t("baselines.create")}`}
        </button>
      </div>

      {showForm && (
        <div
          data-testid="create-baseline-form"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-card)",
            padding: "var(--space-6)",
            marginBottom: "var(--space-6)",
            maxWidth: "560px",
          }}
        >
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
      )}

      {state.baselines.length === 0 ? (
        <p
          data-testid="baselines-empty"
          style={{
            fontSize: "var(--font-size-base)",
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px dashed var(--color-border)",
          }}
        >
          {t("baselines.empty")}
        </p>
      ) : (
        <table
          data-testid="baseline-list"
          style={{
            width: "100%",
            borderCollapse: "collapse",
            background: "var(--color-surface)",
            borderRadius: "var(--radius-lg)",
            boxShadow: "var(--shadow-card)",
            overflow: "hidden",
          }}
        >
          <thead>
            <tr style={{ background: "var(--color-surface-raised)" }}>
              <th
                style={{
                  textAlign: "left",
                  padding: "var(--space-3) var(--space-4)",
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 600,
                  color: "var(--color-text)",
                  borderBottom: "1px solid var(--color-border)",
                }}
              >
                {t("baselines.id")}
              </th>
              <th
                style={{
                  textAlign: "left",
                  padding: "var(--space-3) var(--space-4)",
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 600,
                  color: "var(--color-text)",
                  borderBottom: "1px solid var(--color-border)",
                }}
              >
                {t("baselines.scope")}
              </th>
              <th
                style={{
                  textAlign: "left",
                  padding: "var(--space-3) var(--space-4)",
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 600,
                  color: "var(--color-text)",
                  borderBottom: "1px solid var(--color-border)",
                }}
              >
                {t("baselines.artifact")}
              </th>
              <th
                style={{
                  textAlign: "left",
                  padding: "var(--space-3) var(--space-4)",
                  fontSize: "var(--font-size-sm)",
                  fontWeight: 600,
                  color: "var(--color-text)",
                  borderBottom: "1px solid var(--color-border)",
                }}
              >
                {t("baselines.created")}
              </th>
            </tr>
          </thead>
          <tbody>
            {state.baselines.map((bl) => (
              <tr key={bl.id} data-testid="baseline-item">
                <td
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    fontFamily: "monospace",
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text)",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  {bl.id.slice(0, 8)}…
                </td>
                <td
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    fontSize: "var(--font-size-base)",
                    color: "var(--color-text)",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  {bl.scope}
                </td>
                <td
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    fontFamily: "monospace",
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text-muted)",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  {bl.artifact_id.slice(0, 8)}…
                </td>
                <td
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text-muted)",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  {formatDate(bl.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
