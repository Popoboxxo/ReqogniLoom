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

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { tracelinksApi } from "../../api/tracelinks";
import { traceabilityApi } from "../../api/traceability";
import type { ImpactDirection, ImpactNode } from "../../api/tracelinks";
import { requirementsApi } from "../../api/requirements";
import { architectureApi } from "../../api/architecture";
import { artifactsApi } from "../../api/artifacts";
import { testcasesApi } from "../../api/testcases";
import { risksApi } from "../../api/risks";
import { issuesApi } from "../../api/issues";
import { adrsApi } from "../../api/adrs";
import { stakeholderNeedApi } from "../../api/stakeholder-need";
import { icdsApi } from "../../api/icds";
import { workspacesApi } from "../../api/workspaces";
import { useWorkspace } from "../../context/WorkspaceContext";
import {
  ALL_LINK_TYPES,
  getLinkTypeLabel,
} from "../../constants/traceLinkLabels";
import { CreateTraceLinkDialog } from "../shared/CreateTraceLinkDialog";
import type {
  ArchitectureElement,
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
  cycles: UUID[][];
  isLoading: boolean;
  error: string | null;
}

const INITIAL_STATE: TraceabilityState = {
  links: [],
  titles: {},
  artifacts: [],
  cycles: [],
  isLoading: true,
  error: null,
};

// Canonical link_type order (REQ-L2-RF-006 — predictable section order).
// Sourced from the shared label map so all 12 backend link types are covered.
const LINK_TYPE_ORDER: string[] = ALL_LINK_TYPES;


function formatId(id: UUID): string {
  return `${id.slice(0, 8)}…`;
}

function renderEndpoint(id: UUID, titles: Record<UUID, string>): string {
  const title = titles[id];
  return title ? `${title} (${formatId(id)})` : formatId(id);
}

function artifactLabel(a: Artifact, titles: Record<UUID, string>): string {
  const title = titles[a.id];
  if (title) return `${a.artifact_type}: ${title} (${formatId(a.id)})`;
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
    .filter((k) => !LINK_TYPE_ORDER.includes(k))
    .sort();
  return [...known, ...unknown];
}

export default function TraceabilityView(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace, isLoadingWorkspace } = useWorkspace();
  const [state, setState] = useState<TraceabilityState>(INITIAL_STATE);
  // REQ-005: unified CreateTraceLinkDialog replaces the old inline form
  const [showCreateDialog, setShowCreateDialog] = useState<boolean>(false);
  const [reloadKey, setReloadKey] = useState<number>(0);
  const [isExportingPdf, setIsExportingPdf] = useState<boolean>(false);
  // Impact-analysis panel state (REQ-L2-TE-019).
  const [impactArtifact, setImpactArtifact] = useState<string>("");
  const [impactDirection, setImpactDirection] =
    useState<ImpactDirection>("outgoing");
  const [impactNodes, setImpactNodes] = useState<ImpactNode[]>([]);
  const [impactLoading, setImpactLoading] = useState<boolean>(false);
  const [impactError, setImpactError] = useState<string | null>(null);
  const [impactRan, setImpactRan] = useState<boolean>(false);

  useEffect(() => {
    if (!activeWorkspace || isLoadingWorkspace) {
      setState({
        links: [],
        titles: {},
        artifacts: [],
        cycles: [],
        isLoading: false,
        error: null,
      });
      return;
    }

    let cancelled = false;
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    async function load(): Promise<void> {
      if (!activeWorkspace || isLoadingWorkspace) return;
      try {
        // Load links, requirements, architecture elements, test cases and
        // artifacts in parallel.
        // - requirements + architecture + testcases provide titles for
        //   endpoint rendering (REQ-L1-035, A.6: TestCase endpoints must
        //   resolve to titles the same way Requirement/Architecture do).
        // - artifacts populate the create-form selects (artifact UUIDs are
        //   the actual TraceLink endpoint identifiers).
        // Title resolution spans every artifact type a TraceLink can reach
        // (REQ-L1-035). Non-Artifact-backed types (risk, issue, adr, need,
        // icd) are fetched too so endpoints never fall back to a raw UUID.
        // Each side fetch tolerates 404/failure via a catch → empty results.
        const emptyPage = { results: [] as unknown[] };
        const emptyCycles = { cycles: [] as UUID[][], count: 0 };
        const [
          linksResp,
          reqResp,
          archResp,
          tcResp,
          artifactsResp,
          riskResp,
          issueResp,
          adrResp,
          needResp,
          icdResp,
          cyclesResp,
        ] = await Promise.all([
          tracelinksApi.list(activeWorkspace.id),
          requirementsApi.list(activeWorkspace.id),
          architectureApi.list(activeWorkspace.id),
          testcasesApi.list(activeWorkspace.id),
          artifactsApi.list(activeWorkspace.id),
          risksApi.list(activeWorkspace.id).catch(() => emptyPage),
          issuesApi.list(activeWorkspace.id).catch(() => emptyPage),
          adrsApi.list(activeWorkspace.id).catch(() => emptyPage),
          stakeholderNeedApi.listByWorkspace(activeWorkspace.id).catch(() => emptyPage),
          icdsApi.list(activeWorkspace.id).catch(() => emptyPage),
          traceabilityApi.cycles(activeWorkspace.id).catch(() => emptyCycles),
        ]);
        if (cancelled) return;

        const titles: Record<UUID, string> = {};
        for (const r of reqResp.results as Requirement[]) {
          titles[r.id] = r.title || t("editor.untitled");
        }
        for (const el of archResp.results as ArchitectureElement[]) {
          titles[el.id] = el.title || t("editor.untitled");
        }
        for (const tc of tcResp.results) {
          titles[tc.id] = tc.title || t("editor.untitled");
        }
        for (const rk of riskResp.results as { id: UUID; title?: string }[]) {
          titles[rk.id] = rk.title || t("editor.untitled");
        }
        for (const is of issueResp.results as { id: UUID; title?: string }[]) {
          titles[is.id] = is.title || t("editor.untitled");
        }
        for (const ad of adrResp.results as { id: UUID; title?: string }[]) {
          titles[ad.id] = ad.title || t("editor.untitled");
        }
        for (const nd of needResp.results as { id: UUID; title?: string }[]) {
          titles[nd.id] = nd.title || t("editor.untitled");
        }
        for (const ic of icdResp.results as { id: UUID; name?: string }[]) {
          titles[ic.id] = ic.name || t("editor.untitled");
        }

        setState({
          links: linksResp.results,
          titles,
          artifacts: artifactsResp.results,
          cycles: cyclesResp.cycles,
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
            cycles: [],
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
          cycles: [],
          isLoading: false,
          error: msg,
        });
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, [activeWorkspace, isLoadingWorkspace, t, reloadKey]);

  const grouped = useMemo(() => groupByLinkType(state.links), [state.links]);
  const groupKeys = useMemo(() => orderedGroupKeys(grouped), [grouped]);

  async function handleExportPdf(): Promise<void> {
    if (!activeWorkspace) return;
    setIsExportingPdf(true);
    try {
      const blob = await workspacesApi.downloadPdfReport(
        activeWorkspace.id,
        "traceability_matrix"
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `traceability_matrix_${activeWorkspace.id.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("PDF export failed:", err);
    } finally {
      setIsExportingPdf(false);
    }
  }

  async function runImpact(): Promise<void> {
    if (!impactArtifact) return;
    setImpactLoading(true);
    setImpactError(null);
    try {
      const nodes = await traceabilityApi.impact(impactArtifact, {
        direction: impactDirection,
        maxDepth: 10,
      });
      setImpactNodes(nodes);
      setImpactRan(true);
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setImpactError(msg);
      setImpactNodes([]);
      setImpactRan(true);
    } finally {
      setImpactLoading(false);
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
        <div style={{ display: "flex", gap: "var(--space-2)" }}>
          <button
            type="button"
            data-testid="export-pdf-btn"
            onClick={handleExportPdf}
            disabled={!activeWorkspace || isExportingPdf}
            style={{
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-base)",
              fontWeight: 500,
              background: "var(--color-surface)",
              color: "var(--color-text)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-md)",
              cursor: activeWorkspace ? "pointer" : "not-allowed",
              opacity: isExportingPdf ? 0.6 : 1,
            }}
          >
            {isExportingPdf ? "Exporting…" : "Export PDF"}
          </button>
          {/* REQ-005: unified CreateTraceLinkDialog replaces the old inline form */}
          <button
            type="button"
            data-testid="tracelink-create-btn"
            onClick={() => setShowCreateDialog(true)}
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
        </div>
      </div>

      {state.cycles.length > 0 && (
        <div
          role="alert"
          data-testid="cycle-warning"
          style={{
            background: "var(--color-surface)",
            border: "1px solid var(--color-danger)",
            borderLeft: "4px solid var(--color-danger)",
            borderRadius: "var(--radius-md)",
            padding: "var(--space-4)",
            marginBottom: "var(--space-6)",
          }}
        >
          <strong style={{ color: "var(--color-danger)" }}>
            ⚠ {t("traceability.cycleWarning")} ({state.cycles.length})
          </strong>
          <ul
            style={{
              margin: "var(--space-2) 0 0",
              paddingLeft: "var(--space-5)",
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text-muted)",
            }}
          >
            {state.cycles.map((cycle, i) => (
              <li key={i} data-testid="cycle-item">
                {cycle
                  .map((id) => renderEndpoint(id, state.titles))
                  .join(" → ")}{" "}
                → {renderEndpoint(cycle[0], state.titles)}
              </li>
            ))}
          </ul>
        </div>
      )}

      <section
        data-testid="impact-panel"
        style={{
          background: "var(--color-surface)",
          border: "1px solid var(--color-border)",
          borderRadius: "var(--radius-lg)",
          padding: "var(--space-4) var(--space-5)",
          marginBottom: "var(--space-6)",
          boxShadow: "var(--shadow-card)",
        }}
      >
        <h3
          style={{
            margin: "0 0 var(--space-3)",
            fontSize: "var(--font-size-lg)",
            fontWeight: 600,
            color: "var(--color-text)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
          }}
        >
          {t("traceability.impactTitle")}
        </h3>
        <div
          style={{
            display: "flex",
            gap: "var(--space-3)",
            alignItems: "flex-end",
            flexWrap: "wrap",
          }}
        >
          <label
            style={{
              display: "flex",
              flexDirection: "column",
              gap: "var(--space-1)",
              fontSize: "var(--font-size-sm)",
              color: "var(--color-text)",
              flex: "1 1 260px",
            }}
          >
            <span>{t("traceability.impactArtifact")}</span>
            <select
              data-testid="impact-artifact-select"
              value={impactArtifact}
              onChange={(e) => setImpactArtifact(e.target.value)}
              disabled={!hasArtifacts || impactLoading}
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
                  {artifactLabel(a, state.titles)}
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
            <span>{t("traceability.impactDirection")}</span>
            <select
              data-testid="impact-direction-select"
              value={impactDirection}
              onChange={(e) =>
                setImpactDirection(e.target.value as ImpactDirection)
              }
              disabled={impactLoading}
              style={{
                padding: "var(--space-2)",
                borderRadius: "var(--radius-md)",
                border: "1px solid var(--color-border)",
                fontSize: "var(--font-size-base)",
              }}
            >
              <option value="outgoing">
                {t("traceability.impactDirOutgoing")}
              </option>
              <option value="incoming">
                {t("traceability.impactDirIncoming")}
              </option>
              <option value="both">{t("traceability.impactDirBoth")}</option>
            </select>
          </label>

          <button
            type="button"
            data-testid="impact-run-btn"
            onClick={runImpact}
            disabled={!impactArtifact || impactLoading}
            style={{
              padding: "var(--space-2) var(--space-4)",
              fontSize: "var(--font-size-base)",
              fontWeight: 500,
              background: "var(--color-primary)",
              color: "var(--color-on-primary, #fff)",
              border: "none",
              borderRadius: "var(--radius-md)",
              cursor:
                !impactArtifact || impactLoading ? "not-allowed" : "pointer",
            }}
          >
            {impactLoading
              ? t("traceability.impactRunning")
              : t("traceability.impactRun")}
          </button>
        </div>

        {impactError && (
          <p
            role="alert"
            data-testid="impact-error"
            style={{
              color: "var(--color-danger)",
              fontSize: "var(--font-size-sm)",
              marginTop: "var(--space-3)",
            }}
          >
            {impactError}
          </p>
        )}

        {impactRan && !impactError && (
          <div style={{ marginTop: "var(--space-4)" }}>
            {impactNodes.length === 0 ? (
              <p
                data-testid="impact-empty"
                style={{
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text-muted)",
                  margin: 0,
                }}
              >
                {t("traceability.impactEmpty")}
              </p>
            ) : (
              <ul
                data-testid="impact-result-list"
                style={{ listStyle: "none", margin: 0, padding: 0 }}
              >
                {impactNodes.map((node) => (
                  <li
                    key={`${node.artifact_id}-${node.depth}`}
                    data-testid="impact-node"
                    data-depth={node.depth}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "var(--space-2)",
                      padding: "var(--space-2) 0",
                      paddingLeft: `calc(${node.depth} * var(--space-5))`,
                      borderBottom: "1px solid var(--color-border)",
                      fontSize: "var(--font-size-base)",
                      color: "var(--color-text)",
                    }}
                  >
                    <span
                      style={{
                        fontSize: "var(--font-size-xs)",
                        color: "var(--color-text-muted)",
                      }}
                    >
                      {t("traceability.impactDepth")} {node.depth}
                    </span>
                    <span
                      data-testid="impact-node-type"
                      style={{
                        fontSize: "var(--font-size-xs)",
                        background: "var(--color-surface-raised)",
                        padding: "2px 8px",
                        borderRadius: "var(--radius-full)",
                        color: "var(--color-text-muted)",
                        fontWeight: 500,
                      }}
                    >
                      {node.artifact_type}
                    </span>
                    <span style={{ fontWeight: 500 }}>
                      {node.title || formatId(node.artifact_id)}
                    </span>
                    {node.uid && (
                      <span
                        style={{
                          fontSize: "var(--font-size-xs)",
                          color: "var(--color-text-muted)",
                        }}
                      >
                        {node.uid}
                      </span>
                    )}
                    <span
                      style={{
                        fontSize: "var(--font-size-xs)",
                        color: "var(--color-text-muted)",
                      }}
                    >
                      via {getLinkTypeLabel(node.link_type)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
      </section>

      {/* REQ-005: unified CreateTraceLinkDialog (global mode — no fixed sourceId) */}
      {activeWorkspace && (
        <CreateTraceLinkDialog
          workspaceId={activeWorkspace.id}
          isOpen={showCreateDialog}
          onClose={() => setShowCreateDialog(false)}
          onCreated={() => { setShowCreateDialog(false); setReloadKey((k) => k + 1); }}
          defaultLinkType={(activeWorkspace.default_link_type as LinkType) || 'derives-from'}
        />
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
                    {getLinkTypeLabel(linkType)}
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
                        {getLinkTypeLabel(link.link_type)}
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
