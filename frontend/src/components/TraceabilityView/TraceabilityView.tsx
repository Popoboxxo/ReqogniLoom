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
 *   IF-RF-EXT-OUT-001 → GET /api/v1/tracelinks/?workspace_id=<id>
 *   IF-RF-EXT-OUT-001 → GET /api/v1/requirements/ (title resolution)
 */

import React, { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { tracelinksApi } from "../../api/tracelinks";
import { requirementsApi } from "../../api/requirements";
import { useWorkspace } from "../../context/WorkspaceContext";
import type { TraceLink, Requirement, UUID } from "../../types";

interface TraceabilityState {
  links: TraceLink[];
  titles: Record<UUID, string>;
  isLoading: boolean;
  error: string | null;
}

const INITIAL_STATE: TraceabilityState = {
  links: [],
  titles: {},
  isLoading: true,
  error: null,
};

// Canonical link_type order (REQ-L2-RF-006 — predictable section order)
const LINK_TYPE_ORDER: string[] = [
  "parent-child",
  "derives-from",
  "satisfies",
  "verifies",
  "implements",
  "refines",
];

function formatId(id: UUID): string {
  return `${id.slice(0, 8)}…`;
}

function renderEndpoint(id: UUID, titles: Record<UUID, string>): string {
  const title = titles[id];
  return title ? `${title} (${formatId(id)})` : formatId(id);
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
    .filter((k) => !LINK_TYPE_ORDER.includes(k))
    .sort();
  return [...known, ...unknown];
}

export default function TraceabilityView(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [state, setState] = useState<TraceabilityState>(INITIAL_STATE);

  useEffect(() => {
    if (!activeWorkspace) {
      setState({ links: [], titles: {}, isLoading: false, error: null });
      return;
    }

    let cancelled = false;
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    async function load(): Promise<void> {
      if (!activeWorkspace) return;
      try {
        // Load links and requirements in parallel — requirements provide titles
        // for endpoint rendering so the table is human-readable.
        const [linksResp, reqResp] = await Promise.all([
          tracelinksApi.list(activeWorkspace.id),
          requirementsApi.list(activeWorkspace.id),
        ]);
        if (cancelled) return;

        const titles: Record<UUID, string> = {};
        for (const r of reqResp.results as Requirement[]) {
          titles[r.id] = r.title || t("editor.untitled");
        }

        setState({
          links: linksResp.results,
          titles,
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
            isLoading: false,
            error: null,
          });
          return;
        }
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setState({ links: [], titles: {}, isLoading: false, error: msg });
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace, t]);

  const grouped = useMemo(() => groupByLinkType(state.links), [state.links]);
  const groupKeys = useMemo(() => orderedGroupKeys(grouped), [grouped]);

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

  return (
    <div data-testid="traceability-view">
      <h2
        style={{
          fontSize: "var(--font-size-2xl)",
          fontWeight: 700,
          color: "var(--color-text)",
          marginTop: 0,
          marginBottom: "var(--space-6)",
        }}
      >
        {t("nav.traceability")}
      </h2>

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
