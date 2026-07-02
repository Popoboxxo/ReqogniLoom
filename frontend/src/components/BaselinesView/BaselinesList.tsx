/**
 * BaselinesList — Extracted list component for baselines.
 *
 * REQ-L1-040 Phase 2 — Unified ModalDialogBase pattern.
 * REQ-L1-049 — Scope-dependent artifact filtering.
 *
 * Manages baseline creation with multi-scope selection and dynamic artifact filtering.
 */

import React, { useState, useCallback, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import { baselinesApi, type Baseline, type BaselineScope, type ScopePreview } from "../../api/baselines";
import { artifactsApi } from "../../api/artifacts";
import { ModalDialogBase, SHARED_STYLES } from "../RequirementsList/ModalDialogBase";
import type { Artifact } from "../../types";

interface BaselineFormState {
  scope: BaselineScope;
  artifactId?: string;
  name?: string;
}

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

export function BaselinesList(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [items, setItems] = useState<Baseline[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [formData, setFormData] = useState<BaselineFormState>({
    scope: "project",
  });

  const [scopePreview, setScopePreview] = useState<ScopePreview | null>(null);
  const [scopePreviewLoading, setScopePreviewLoading] = useState(false);
  const [scopePreviewError, setScopePreviewError] = useState<string | null>(null);

  // Load baselines and artifacts list
  const loadList = useCallback(async (): Promise<void> => {
    if (!activeWorkspace) {
      setItems([]);
      setArtifacts([]);
      setIsLoading(false);
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const [blResp, artResp] = await Promise.all([
        baselinesApi.list(activeWorkspace.id),
        artifactsApi.list(activeWorkspace.id),
      ]);
      setItems(blResp.results as Baseline[]);
      setArtifacts(artResp.results as Artifact[]);
    } catch (err: unknown) {
      const msg = (err as { error?: { message?: string } })?.error?.message ?? String(err);
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeWorkspace]);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!cancelled) {
        await loadList();
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [loadList]);

  // Load scope preview when form is open and scope/artifact changes
  useEffect(() => {
    if (!showCreate || !activeWorkspace) {
      setScopePreview(null);
      return;
    }
    if (formData.scope === "document" && !formData.artifactId) {
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
          scope: formData.scope,
          workspaceId: activeWorkspace.id,
          artifactId: formData.scope === "document" ? formData.artifactId ?? null : null,
        });
        if (!cancelled) {
          setScopePreview(result);
        }
      } catch (err: unknown) {
        if (!cancelled) {
          const msg = (err as { error?: { message?: string } })?.error?.message ?? String(err);
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
  }, [showCreate, activeWorkspace, formData.scope, formData.artifactId]);

  // Set default artifact when form opens
  useEffect(() => {
    if (showCreate && !formData.artifactId && artifacts.length > 0) {
      setFormData((prev) => ({ ...prev, artifactId: artifacts[0].id }));
    }
  }, [showCreate, artifacts, formData.artifactId]);

  const resetForm = useCallback((): void => {
    setFormData({ scope: "project" });
    setFormError(null);
    setScopePreview(null);
    setScopePreviewError(null);
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
      e.preventDefault();
      if (!activeWorkspace) return;

      // Validate: document scope requires artifact
      if (formData.scope === "document" && !formData.artifactId) {
        setFormError(t("baselines.artifactRequired"));
        return;
      }

      setIsSubmitting(true);
      setFormError(null);
      try {
        await baselinesApi.create({
          workspace_id: activeWorkspace.id,
          scope: formData.scope,
          artifact_id: formData.scope === "document" ? formData.artifactId : null,
        });
        setShowCreate(false);
        resetForm();
        await loadList();
      } catch (err: unknown) {
        const msg = (err as { error?: { message?: string } })?.error?.message ?? String(err);
        setFormError(msg);
      } finally {
        setIsSubmitting(false);
      }
    },
    [activeWorkspace, formData, t, resetForm, loadList]
  );

  const handleCancel = useCallback((): void => {
    setShowCreate(false);
    resetForm();
  }, [resetForm]);

  if (isLoading) {
    return (
      <p role="status" style={{ color: "var(--color-text-muted)", padding: "var(--space-4)" }}>
        {t("loading")}
      </p>
    );
  }

  if (error) {
    return (
      <div role="alert" style={{ color: "var(--color-danger)", padding: "var(--space-4)" }}>
        {error}
        <button onClick={loadList} style={SHARED_STYLES.primaryButton}>
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  return (
    <div>
      <ModalDialogBase
        title={t("nav.baselines")}
        isOpen={showCreate}
        onToggle={() => setShowCreate(!showCreate)}
        onSubmit={handleSubmit}
        onCancel={handleCancel}
        error={formError}
        isSubmitting={isSubmitting}
        itemCount={items.length}
        testIdPrefix="baseline"
        buttonTestIdPrefix="baseline"
      >
        <div>
          {/* Scope selector — REQ-L1-049 */}
          <label style={SHARED_STYLES.label}>
            {t("baselines.scope")}
          </label>
          <div
            data-testid="baseline-scope-group"
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-2)",
              marginBottom: "var(--space-4)",
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
                  checked={formData.scope === opt.value}
                  onChange={() => setFormData((prev) => ({ ...prev, scope: opt.value }))}
                />
                <span>{t(opt.labelKey)}</span>
              </label>
            ))}
          </div>

          {/* Scope preview — REQ-L1-049 */}
          <p
            data-testid="baseline-scope-count"
            aria-live="polite"
            style={{
              fontSize: "var(--font-size-sm)",
              color: scopePreviewError ? "var(--color-danger)" : "var(--color-text-muted)",
              margin: "0 0 var(--space-4) 0",
            }}
          >
            {scopePreviewError
              ? scopePreviewError
              : scopePreviewLoading
                ? t("baselines.scopeCountLoading")
                : scopePreview
                  ? t("baselines.scopeCountReady", { count: scopePreview.count })
                  : formData.scope === "document" && !formData.artifactId
                    ? t("baselines.scopeCountNeedsArtifact")
                    : t("baselines.scopeCountIdle")}
          </p>

          {/* Artifact picker — only for document scope — REQ-L1-049 */}
          {formData.scope === "document" && (
            <>
              <label htmlFor="baseline-artifact" style={SHARED_STYLES.label}>
                {t("baselines.artifact")} *
              </label>
              <select
                id="baseline-artifact"
                data-testid="baseline-artifact-select"
                value={formData.artifactId ?? ""}
                onChange={(e) =>
                  setFormData((prev) => ({
                    ...prev,
                    artifactId: e.target.value || undefined,
                  }))
                }
                disabled={artifacts.length === 0}
                style={SHARED_STYLES.input}
              >
                <option value="">
                  {artifacts.length === 0 ? t("baselines.noArtifacts") : "—"}
                </option>
                {artifacts.map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.artifact_type} — {a.id.slice(0, 8)}…
                  </option>
                ))}
              </select>
            </>
          )}
        </div>
      </ModalDialogBase>

      {items.length === 0 && !showCreate ? (
        <p style={{ color: "var(--color-text-muted)", padding: "var(--space-6)" }}>
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
            {items.map((baseline) => (
              <tr key={baseline.id} data-testid="baseline-item">
                <td
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    fontFamily: "monospace",
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text)",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  {baseline.id.slice(0, 8)}…
                </td>
                <td
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    fontSize: "var(--font-size-base)",
                    color: "var(--color-text)",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  {baseline.scope}
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
                  {baseline.artifact_id ? `${baseline.artifact_id.slice(0, 8)}…` : "—"}
                </td>
                <td
                  style={{
                    padding: "var(--space-3) var(--space-4)",
                    fontSize: "var(--font-size-sm)",
                    color: "var(--color-text-muted)",
                    borderBottom: "1px solid var(--color-border)",
                  }}
                >
                  {formatDate(baseline.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

export default BaselinesList;
