/**
 * ARCH-L1-001 ReactFrontend — TraceabilityView (COMP-RF-005).
 *
 * leaf_id: COMP-RF-005
 * req_id:  REQ-L2-RF-006 (Traceability-Anzeige)
 *
 * Lists TraceLinks for the active workspace, grouped by link_type.
 * Each link shows source -> link_type -> target, resolving requirement
 * titles where possible so the table stays human-readable.
 *
 * Interfaces consumed:
 *   IF-RF-EXT-OUT-001 → GET  /api/v1/tracelinks/?workspace_id=<id>
 *   IF-RF-EXT-OUT-001 → POST /api/v1/tracelinks/
 *   IF-RF-EXT-OUT-001 → GET  /api/v1/requirements/ (title resolution)
 *   IF-RF-EXT-OUT-001 → GET  /api/v1/artifacts/?workspace_id=<id> (form options)
 */

import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { tracelinksApi } from "../../api/tracelinks";
import { requirementsApi } from "../../api/requirements";
import { artifactsApi } from "../../api/artifacts";
import { useWorkspace } from "../../context/WorkspaceContext";
import type {
  Artifact,
  LinkType,
  Requirement,
  TraceLink,
  UUID,
} from "../../types";

interface TraceabilityState {
  links: TraceLink[];
  titles: Record<UUID, string>;
  artifacts: Artifact[];
  isLoading: boolean;
  error: string | null;
}

const INITIAL_STATE: TraceabilityState = {
  links: [],
  titles: {},
  artifacts: [],
  isLoading: true,
  error: null,
};

// Canonical link_type order (REQ-L2-RF-006 — predictable section order)
const LINK_TYPE_ORDER: LinkType[] = [
  "parent-child",
  "derives-from",
  "satisfies",
  "verifies",
  "implements",
  "refines",
];

interface CreateFormData {
  source_id: string;
  target_id: string;
  link_type: LinkType;
}

const INITIAL_FORM: CreateFormData = {
  source_id: "",
  target_id: "",
  link_type: "parent-child",
};

function formatId(id: UUID): string {
  return `${id.slice(0, 8)}…`;
}

function renderEndpoint(id: UUID, titles: Record<UUID, string>): string {
  const title = titles[id];
  return title ? `${title} (${formatId(id)})` : formatId(id);
}

function artifactLabel(a: Artifact): string {
  return `${a.artifact_type} (${formatId(a.id)})`;
}

function groupByLinkType(links: TraceLink[]): Record<string, TraceLink[]> {
  const grouped: Record<string, TraceLink[]> = {};
  for (const link of links) {
    const key = link.link_type || "other";
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(link);
  }
  return grouped;
}

function orderedGroupKeys(grouped: Record<string, TraceLink[]>): string[] {
  const known = LINK_TYPE_ORDER.filter((k) => grouped[k]);
  const unknown = Object.keys(grouped)
    .filter((k) => !LINK_TYPE_ORDER.includes(k as LinkType))
    .sort();
  return [...known, ...unknown];
}

export default function TraceabilityView(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [state, setState] = useState<TraceabilityState>(INITIAL_STATE);
  const [showCreateForm, setShowCreateForm] = useState<boolean>(false);
  const [formData, setFormData] = useState<CreateFormData>(INITIAL_FORM);
  const [formError, setFormError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [reloadKey, setReloadKey] = useState<number>(0);

  useEffect(() => {
    if (!activeWorkspace) {
      setState({
        links: [],
        titles: {},
        artifacts: [],
        isLoading: false,
        error: null,
      });
      return;
    }

    let cancelled = false;
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    async function load(): Promise<void> {
      if (!activeWorkspace) return;
      try {
        // Load links, requirements and artifacts in parallel.
        // - requirements provide titles for endpoint rendering
        // - artifacts populate the create-form selects
        const [linksResp, reqResp, artifactsResp] = await Promise.all([
          tracelinksApi.list(activeWorkspace.id),
          requirementsApi.list(activeWorkspace.id),
          artifactsApi.list(activeWorkspace.id),
        ]);
        if (cancelled) return;

        const titles: Record<UUID, string> = {};
        for (const r of reqResp.results as Requirement[]) {
          titles[r.id] = r.title || t("editor.untitled");
        }

        setState({
          links: linksResp.results,
          titles,
          artifacts: artifactsResp.results,
          isLoading: false,
          error: null,
        });
      } catch (err: unknown) {
        if (cancelled) return;
        // 404 → endpoint missing → render empty state gracefully
        const status = (err as { status?: number })?.status;
        if (status === 404) {
          setState({
            links: [],
            titles: {},
            artifacts: [],
            isLoading: false,
            error: null,
          });
          return;
        }
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setState({
          links: [],
          titles: {},
          artifacts: [],
          isLoading: false,
          error: msg,
        });
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace, t, reloadKey]);

  const grouped = useMemo(() => groupByLinkType(state.links), [state.links]);
  const groupKeys = useMemo(() => orderedGroupKeys(grouped), [grouped]);

  // ---------------------------------------------------------------------------
  // Create-form handlers
  // ---------------------------------------------------------------------------

  function openCreateForm(): void {
    setFormData(INITIAL_FORM);
    setFormError(null);
    setShowCreateForm(true);
  }

  function cancelCreateForm(): void {
    setShowCreateForm(false);
    setFormError(null);
  }

  async function submitCreateForm(
    e: React.FormEvent<HTMLFormElement>
  ): Promise<void> {
    e.preventDefault();
    if (!activeWorkspace) return;

    if (!formData.source_id) {
      setFormError(t("traceability.sourceRequired"));
      return;
    }
    if (!formData.target_id) {
      setFormError(t("traceability.targetRequired"));
      return;
    }
    if (formData.source_id === formData.target_id) {
      setFormError(t("traceability.sameEndpoints"));
      return;
    }

    setIsSubmitting(true);
    setFormError(null);
    try {
      await tracelinksApi.create({
        source_id: formData.source_id,
        target_id: formData.target_id,
        link_type: formData.link_type,
      });
      setShowCreateForm(false);
      setFormData(INITIAL_FORM);
      setReloadKey((k) => k + 1);
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setFormError(msg);
    } finally {
      setIsSubmitting(false);
    }
  }

  // ---------------------------------------------------------------------------
  // Render
  // ---------------------------------------------------------------------------

  if (state.isLoading) {
    return (
      <div data-testid="traceability-view">
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
      <div data-testid="traceability-view">
        <div
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
          <p style={{ color: "var(--color-danger)", margin: 0 }}>
            {state.error}
          </p>
        </div>
      </div>
    );
  }

  const hasArtifacts = state.artifacts.length > 0;

  return (
    <div data-testid="traceability-view">
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
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
          {t("nav.traceability")}
        </h2>
        {!showCreateForm && (
          <button
            type="button"
            data-testid="tracelink-create-btn"
            onClick={openCreateForm}
            disabled={!activeWorkspace}
            style={{
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-base)",
              fontWeight: 500,
              background: "var(--color-primary)",
              color: "var(--color-on-primary, #fff)",
              border: "none",
              borderRadius: "var(--radius-md)",
              cursor: activeWorkspace ? "pointer" : "not-allowed",
            }}
          >
            {t("traceability.create")}
          </button>
        )}
      </div>

      {showCreateForm && (
        <form
          data-testid="tracelink-create-form"
          onSubmit={submitCreateForm}
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-border)",
            borderRadius: "var(--radius-lg)",
            padding: "var(--space-5)",
            marginBottom: "var(--space-6)",
            display: "flex",
            flexDirection: "column",
            gap: "var(--space-3)",
            boxShadow: "var(--shadow-card)",
            maxWidth: "640px",
          }}
        >
          <label
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-1)",
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text)",
            }}
          >
            <span>{t("traceability.source")}</span>
            <select
              data-testid="tracelink-source-select"
              value={formData.source_id}
              onChange={(e) =>
                setFormData((prev) => ({ ...prev, source_id: e.target.value }))
              }
              disabled={!hasArtifacts || isSubmitting}
              required
              style={{
                padding: "var(--space-2)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                fontSize: "var(--font-size-base)",
              }}
            >
              <option value="">
                {hasArtifacts ? "—" : t("traceability.noArtifacts")}
              </option>
              {state.artifacts.map((a) => (
                <option key={a.id} value={a.id}>
                  {artifactLabel(a)}
                </option>
              ))}
            </select>
          </label>

          <label
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-1)",
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text)",
            }}
          >
            <span>{t("traceability.target")}</span>
            <select
              data-testid="tracelink-target-select"
              value={formData.target_id}
              onChange={(e) =>
                setFormData((prev) => ({ ...prev, target_id: e.target.value }))
              }
              disabled={!hasArtifacts || isSubmitting}
              required
              style={{
                padding: "var(--space-2)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                fontSize: "var(--font-size-base)",
              }}
            >
              <option value="">
                {hasArtifacts ? "—" : t("traceability.noArtifacts")}
              </option>
              {state.artifacts.map((a) => (
                <option key={a.id} value={a.id}>
                  {artifactLabel(a)}
                </option>
              ))}
            </select>
          </label>

          <label
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-1)",
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text)",
            }}
          >
            <span>{t("traceability.linkType")}</span>
            <select
              data-testid="tracelink-type-select"
              value={formData.link_type}
              onChange={(e) =>
                setFormData((prev) => ({
                  ...prev,
                  link_type: e.target.value as LinkType,
                }))
              }
              disabled={isSubmitting}
              required
              style={{
                padding: "var(--space-2)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                fontSize: "var(--font-size-base)",
              }}
            >
              {LINK_TYPE_ORDER.map((lt) => (
                <option key={lt} value={lt}>
                  {lt}
                </option>
              ))}
            </select>
          </label>

          {formError && (
            <p
              role="alert"
              data-testid="tracelink-form-error"
              style={{
                color: "var(--color-danger)",
                fontSize: "var(--font-size-sm)",
                margin: 0,
              }}
            >
              {formError}
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
              data-testid="tracelink-cancel-btn"
              onClick={cancelCreateForm}
              disabled={isSubmitting}
              style={{
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-base)",
                background: "var(--color-surface-raised)",
                color: "var(--color-text)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-md)",
                cursor: isSubmitting ? "not-allowed" : "pointer",
              }}
            >
              {t("actions.cancel")}
            </button>
            <button
              type="submit"
              data-testid="tracelink-submit-btn"
              disabled={isSubmitting || !hasArtifacts}
              style={{
                padding: "var(--space-2) var(--space-4)",
                fontSize: "var(--font-size-base)",
                fontWeight: 500,
                background: "var(--color-primary)",
                color: "var(--color-on-primary, #fff)",
                border: "none",
                borderRadius: "var(--radius-md)",
                cursor:
                  isSubmitting || !hasArtifacts ? "not-allowed" : "pointer",
              }}
            >
              {isSubmitting
                ? t("traceability.submitting")
                : t("traceability.submit")}
            </button>
          </div>
        </form>
      )}

      {state.links.length === 0 ? (
        <p
          data-testid="traceability-empty"
          style={{
            fontSize: "var(--font-size-base)",
            color: "var(--color-text-muted)",
            padding: "var(--space-6)",
            background: "var(--color-surface-raised)",
            borderRadius: "var(--radius-lg)",
            border: "1px dashed var(--color-border)",
          }}
        >
          {t("traceability.empty")}
        </p>
      ) : (
        <div
          data-testid="traceability-list"
          style={{ display: "flex", flexDirection: "column", gap: "var(--space-6)" }}
        >
          {groupKeys.map((linkType) => {
            const groupLinks = grouped[linkType];
            return (
              <section
                key={linkType}
                data-testid="tracelink-group"
                data-link-type={linkType}
                style={{
                  background: "var(--color-surface)",
                  borderRadius: "var(--radius-lg)",
                  boxShadow: "var(--shadow-card)",
                  overflow: "hidden",
                }}
              >
                <header
                  style={{
                    background: "var(--color-surface-raised)",
                    padding: "var(--space-3) var(--space-4)",
                    borderBottom: "1px solid var(--color-border)",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                  }}
                >
                  <h3
                    style={{
                      margin: 0,
                      fontSize: "var(--font-size-lg)",
                      fontWeight: 600,
                      color: "var(--color-text)",
                    }}
                  >
                    {linkType}
                  </h3>
                  <span
                    style={{
                      fontSize: "var(--font-size-sm)",
                      color: "var(--color-text-muted)",
                    }}
                  >
                    {groupLinks.length}
                  </span>
                </header>
                <ul
                  style={{
                    listStyle: "none",
                    margin: 0,
                    padding: 0,
                  }}
                >
                  {groupLinks.map((link) => (
                    <li
                      key={link.id}
                      data-testid="tracelink-item"
                      data-link-type={link.link_type}
                      style={{
                        padding: "var(--space-3) var(--space-4)",
                        borderBottom: "1px solid var(--color-border)",
                        display: "flex",
                        alignItems: "center",
                        gap: "var(--space-3)",
                        fontSize: "var(--font-size-base)",
                        color: "var(--color-text)",
                      }}
                    >
                      <span data-testid="tracelink-source">
                        {renderEndpoint(link.source_id, state.titles)}
                      </span>
                      <span
                        aria-hidden="true"
                        style={{
                          color: "var(--color-text-muted)",
                          fontWeight: 500,
                        }}
                      >
                        →
                      </span>
                      <span
                        data-testid="tracelink-type"
                        style={{
                          fontSize: "var(--font-size-sm)",
                          background: "#eef",
                          padding: "2px 8px",
                          borderRadius: "var(--radius-full)",
                          color: "#2c5282",
                          fontWeight: 500,
                        }}
                      >
                        {link.link_type}
                      </span>
                      <span
                        aria-hidden="true"
                        style={{
                          color: "var(--color-text-muted)",
                          fontWeight: 500,
                        }}
                      >
                        →
                      </span>
                      <span data-testid="tracelink-target">
                        {renderEndpoint(link.target_id, state.titles)}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            );
          })}
        </div>
      )}
    </div>
  );
}
