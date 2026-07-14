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

import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  type BaselineDiff,
  type BaselineScope,
} from "../../api/baselines";
import { SplitView } from "../SplitView/SplitView";
import type { Artifact } from "../../types";
import {
  BaselineComparePanel,
  BaselineEntriesSection,
} from "./BaselinesPanels";
import { useBaselinesData } from "./useBaselinesData";

// Re-exported so existing imports (and unit tests) that pull DiffItemRow from
// this module keep working after the Container/Presenter split (REQ-050).
export { DiffItemRow } from "./BaselinesPanels";

/** Extract a `{ error: { message } }`-shaped API error message. */
function baselineErrorMessage(err: unknown): string {
  return (
    (err as { error?: { message?: string } })?.error?.message ?? String(err)
  );
}

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
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [formArtifactId, setFormArtifactId] = useState<string>("");
  // REQ-L1-049: scope is now one of {document, project, global}; default
  // is "project" to match the backend model default.
  const [formScope, setFormScope] = useState<BaselineScope>("project");
  const [isSaving, setIsSaving] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  // REQ-L2-BL-003: baseline compare (field-level diff). ``showCompare`` swaps
  // the right panel to the compare form + result. The diff state stays local
  // to the container since it is imperative (button-triggered, not a query).
  const [showCompare, setShowCompare] = useState(false);
  const [compareAId, setCompareAId] = useState<string>("");
  const [compareBId, setCompareBId] = useState<string>("");
  const [diff, setDiff] = useState<BaselineDiff | null>(null);
  const [diffLoading, setDiffLoading] = useState(false);
  const [diffError, setDiffError] = useState<string | null>(null);

  // All data-fetching (lists, scope preview, detail, create/delete/compare)
  // lives in useBaselinesData (TanStack Query — REQ-049/REQ-050).
  const {
    baselines,
    artifacts,
    isLoading,
    error,
    scopePreview,
    scopePreviewLoading,
    scopePreviewError,
    detail,
    detailLoading,
    detailError,
    refreshList,
    createBaseline,
    deleteBaseline,
    compareBaselines,
  } = useBaselinesData({ showForm, formScope, formArtifactId, selectedId });

  // The render still reads a `state`-shaped object (kept for parity with the
  // pre-decomposition markup).
  const state = { baselines, artifacts, isLoading, error };

  // When form opens, default to the first available artifact.
  useEffect(() => {
    if (showForm && !formArtifactId && artifacts.length > 0) {
      setFormArtifactId(artifacts[0].id);
    }
  }, [showForm, formArtifactId, artifacts]);

  const handleCreate = useCallback(async (): Promise<void> => {
    // REQ-L1-049: ``document`` scope requires an artifact.
    if (formScope === "document" && !formArtifactId) {
      setCreateError(t("baselines.artifactRequired"));
      return;
    }
    setIsSaving(true);
    setCreateError(null);
    try {
      const created = await createBaseline({
        scope: formScope,
        artifactId: formArtifactId,
      });
      setShowForm(false);
      setFormArtifactId("");
      setFormScope("project");
      setSelectedId(created.id);
    } catch (err: unknown) {
      setCreateError(baselineErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }, [formArtifactId, formScope, t, createBaseline]);

  const handleDelete = useCallback(
    async (id: string): Promise<void> => {
      if (!window.confirm(t("baselines.deleteConfirm", "Really delete this baseline?"))) {
        return;
      }
      try {
        await deleteBaseline(id);
        if (selectedId === id) setSelectedId(null);
      } catch {
        // Failure surfaces via the hook's `error` (delete mutation error).
      }
    },
    [deleteBaseline, selectedId, t]
  );

  const handleCompare = useCallback(async (): Promise<void> => {
    if (!compareAId || !compareBId) {
      setDiffError(t("baselines.compareSelectBoth", "Select two baselines."));
      return;
    }
    if (compareAId === compareBId) {
      setDiffError(
        t("baselines.compareSameBaseline", "Select two different baselines.")
      );
      return;
    }
    setDiffLoading(true);
    setDiffError(null);
    try {
      const result = await compareBaselines(compareAId, compareBId);
      setDiff(result);
    } catch (err: unknown) {
      setDiffError(baselineErrorMessage(err));
      setDiff(null);
    } finally {
      setDiffLoading(false);
    }
  }, [compareAId, compareBId, t, compareBaselines]);

  const openCompare = useCallback((): void => {
    setShowForm(false);
    setShowCompare(true);
    setSelectedId(null);
    setDiff(null);
    setDiffError(null);
  }, []);

  const closeCompare = useCallback((): void => {
    setShowCompare(false);
    setDiff(null);
    setDiffError(null);
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
          onClick={() => void refreshList()}
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
        height: "100%",
        fontFamily: "var(--font-sans)",
        color: "var(--color-text)",
      }}
    >
      <SplitView
        moduleType="baselines"
        leftMinWidth={280}
        leftPanel={
          <>
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
          <div style={{ display: "flex", gap: "var(--space-2)" }}>
            <button
              data-testid="compare-baseline-btn"
              onClick={() => (showCompare ? closeCompare() : openCompare())}
              disabled={state.baselines.length < 2}
              style={{
                background: showCompare
                  ? "var(--color-surface-raised)"
                  : "transparent",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-sm)",
                fontWeight: 600,
                cursor:
                  state.baselines.length < 2 ? "not-allowed" : "pointer",
                opacity: state.baselines.length < 2 ? 0.6 : 1,
                transition: "var(--transition-fast)",
              }}
            >
              {showCompare
                ? t("actions.cancel")
                : t("baselines.compare", "Compare")}
            </button>
            <button
              data-testid="create-baseline-btn"
              onClick={() => {
                setShowCompare(false);
                setShowForm((v) => !v);
              }}
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
                      fontSize: "var(--font-size-sm)",
                    }}
                  >
                    {bl.name || `${bl.id.slice(0, 8)}…`}
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
          </>
        }
        rightPanel={
          showCompare ? (
            <BaselineComparePanel
              baselines={state.baselines}
              aId={compareAId}
              bId={compareBId}
              onChangeA={setCompareAId}
              onChangeB={setCompareBId}
              onCompare={() => void handleCompare()}
              diff={diff}
              loading={diffLoading}
              error={diffError}
            />
          ) : showForm ? (
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
                    state.artifacts.map((a) => {
                      // The /artifacts/ payload currently exposes only the ID
                      // (no title/name field). Read them defensively so the
                      // label upgrades automatically once the backend adds them.
                      const named = a as Artifact & { title?: string; name?: string };
                      const label = named.title ?? named.name ?? `${a.id.slice(0, 8)}…`;
                      return (
                        <option key={a.id} value={a.id}>
                          {a.artifact_type} — {label}
                        </option>
                      );
                    })
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
              }}
              title={selectedBaseline.id}
            >
              {selectedBaseline.name || `${selectedBaseline.id.slice(0, 8)}…`}
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

            {/* REQ-L2-BL-012: captured items with their full-state snapshot. */}
            <BaselineEntriesSection
              entries={detail?.entries ?? null}
              loading={detailLoading}
              error={detailError}
            />

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
          )
        }
      />
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

