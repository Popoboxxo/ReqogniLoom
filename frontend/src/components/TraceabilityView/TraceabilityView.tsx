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
import { SplitView } from "../SplitView/SplitView";
import { PageHeader } from "../shared/PageHeader";
import { ListToolbar } from "../shared/ListToolbar";
import { EmptyState } from "../shared/EmptyState";
import { IMPACT_PRESET_STORAGE_KEY } from "../ImpactView/impact-preset";
import type { ImpactPreset } from "../ImpactView/impact-preset";
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


const MAX_TITLE_LENGTH = 60;

function formatId(id: UUID): string {
  return `${id.slice(0, 8)}…`;
}

// Truncate long titles so the artifact selector stays scannable (issue #51).
function truncateTitle(title: string): string {
  return title.length > MAX_TITLE_LENGTH
    ? `${title.slice(0, MAX_TITLE_LENGTH)}…`
    : title;
}

function renderEndpoint(id: UUID, titles: Record<UUID, string>): string {
  const title = titles[id];
  return title ? `${truncateTitle(title)} (${formatId(id)})` : formatId(id);
}

function artifactLabel(a: Artifact, titles: Record<UUID, string>): string {
  const title = titles[a.id];
  if (title) return `${a.artifact_type}: ${truncateTitle(title)} (${formatId(a.id)})`;
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
  // Impact-analysis artifact picker (REQ-L2-TE-019). Issue #184: the actual
  // reachability computation/rendering used to be duplicated here and on
  // the canonical `/impact` route — this panel now only pre-selects a
  // workspace-scoped artifact and hands it off to `/impact` (see
  // impact-preset.ts), instead of running its own second impact query.
  const [impactArtifact, setImpactArtifact] = useState<string>("");
  // REQ-005/#181: list-panel search + link-type filter (ListToolbar).
  const [listSearch, setListSearch] = useState<string>("");
  const [linkTypeFilter, setLinkTypeFilter] = useState<string>("");

  useEffect(() => {
    // Issue B: activeWorkspace starts as the DEFAULT_WORKSPACE placeholder
    // (truthy fake UUID) until isLoadingWorkspace flips to false, so a bare
    // `!activeWorkspace` guard fires against the fake id (401).
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
      if (!activeWorkspace) return;
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
        // Issue C: links/testcases/risks/issues/adrs/needs/icds are fetched
        // via listAll() so results beyond the backend's PAGE_SIZE=25 default
        // aren't silently dropped (both from the main list and from title
        // resolution).
        const emptyList: unknown[] = [];
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
          tracelinksApi.listAll(activeWorkspace.id),
          requirementsApi.list(activeWorkspace.id),
          architectureApi.list(activeWorkspace.id),
          testcasesApi.listAll(activeWorkspace.id),
          artifactsApi.list(activeWorkspace.id),
          risksApi.listAll(activeWorkspace.id).catch(() => emptyList),
          issuesApi.listAll(activeWorkspace.id).catch(() => emptyList),
          adrsApi.listAll(activeWorkspace.id).catch(() => emptyList),
          stakeholderNeedApi.listAll(activeWorkspace.id).catch(() => emptyList),
          icdsApi.listAll(activeWorkspace.id).catch(() => emptyList),
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
        for (const tc of tcResp) {
          titles[tc.id] = tc.title || t("editor.untitled");
        }
        for (const rk of riskResp as { id: UUID; title?: string }[]) {
          titles[rk.id] = rk.title || t("editor.untitled");
        }
        for (const is of issueResp as { id: UUID; title?: string }[]) {
          titles[is.id] = is.title || t("editor.untitled");
        }
        for (const ad of adrResp as { id: UUID; title?: string }[]) {
          titles[ad.id] = ad.title || t("editor.untitled");
        }
        for (const nd of needResp as { id: UUID; title?: string }[]) {
          titles[nd.id] = nd.title || t("editor.untitled");
        }
        for (const ic of icdResp as { id: UUID; name?: string }[]) {
          titles[ic.id] = ic.name || t("editor.untitled");
        }

        setState({
          links: linksResp,
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

  // #181: search across resolved endpoint titles/ids + link-type filter,
  // applied before grouping so both controls narrow the same result set the
  // count label reports.
  const filteredLinks = useMemo(() => {
    const q = listSearch.trim().toLowerCase();
    return state.links.filter((link) => {
      if (linkTypeFilter && link.link_type !== linkTypeFilter) return false;
      if (!q) return true;
      const sourceLabel = renderEndpoint(link.source_id, state.titles).toLowerCase();
      const targetLabel = renderEndpoint(link.target_id, state.titles).toLowerCase();
      const typeLabel = getLinkTypeLabel(link.link_type).toLowerCase();
      return sourceLabel.includes(q) || targetLabel.includes(q) || typeLabel.includes(q);
    });
  }, [state.links, state.titles, listSearch, linkTypeFilter]);

  const grouped = useMemo(() => groupByLinkType(filteredLinks), [filteredLinks]);
  const groupKeys = useMemo(() => orderedGroupKeys(grouped), [grouped]);
  const hasActiveListControls = Boolean(listSearch || linkTypeFilter);

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

  // #184: hand off to the canonical `/impact` route instead of duplicating
  // the reachability computation/rendering inline. Pre-resolves the preset
  // from data already loaded here (titles + artifacts), so ImpactView can
  // skip its own search step and load the tree directly.
  function openImpactAnalysis(): void {
    if (!impactArtifact) return;
    const artifact = state.artifacts.find((a) => a.id === impactArtifact);
    const preset: ImpactPreset = {
      id: impactArtifact,
      title: state.titles[impactArtifact] ?? formatId(impactArtifact),
      artifactType: artifact?.artifact_type ?? "",
    };
    try {
      sessionStorage.setItem(IMPACT_PRESET_STORAGE_KEY, JSON.stringify(preset));
    } catch {
      // sessionStorage unavailable (e.g. private mode) — ImpactView falls
      // back to its normal search flow, no functionality lost.
    }
    window.location.assign("/impact");
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

  // REQ-L2-RF-006 / ch. 17 step 6: Trace Links is an explicit Split-View
  // candidate — list on the left (grouped links, ch. 12.3-adjacent), the
  // Impact-Analysis tool on the right as a persistent "detail" pane. Unlike
  // an artifact list/detail split, the right pane is not selection-driven
  // (there is no single "trace link detail" view yet) — it is a standing
  // analysis panel, so the legacy leftPanel/rightPanel contract (resizable,
  // no null-detail collapse) fits better than the concept list/detail/spine
  // contract, which assumes a nullable per-row detail.
  const resetListFilters = (): void => {
    setListSearch("");
    setLinkTypeFilter("");
  };

  const listPanel = (
    <>
      <ListToolbar
        testIdPrefix="tracelink-list"
        searchValue={listSearch}
        onSearchChange={setListSearch}
        searchPlaceholder={t("editor.searchPlaceholder", "Search...")}
        filters={[
          {
            id: "link-type",
            allLabel: t("traceability.allLinkTypes", "Alle Verknüpfungstypen"),
            value: linkTypeFilter,
            options: LINK_TYPE_ORDER.map((lt) => ({ value: lt, label: getLinkTypeLabel(lt) })),
            onChange: setLinkTypeFilter,
          },
        ]}
        countLabel={
          hasActiveListControls
            ? t("editor.filteredCount", { shown: filteredLinks.length, total: state.links.length })
            : null
        }
      />

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

      {state.links.length === 0 ? (
        // ch. 13.3: "there is nothing" — offer the create action.
        <EmptyState
          variant="empty"
          testId="traceability-empty"
          title={t("traceability.emptyTitle", "Noch keine Verknüpfungen")}
          description={t("traceability.empty")}
          actions={[
            {
              label: t("traceability.create"),
              onClick: () => setShowCreateDialog(true),
              testId: "traceability-empty-create",
            },
          ]}
        />
      ) : filteredLinks.length === 0 ? (
        // ch. 13.3: "there is something, just not under this filter" — only
        // a filter/search reset, never a create action.
        <EmptyState variant="no-match" testId="traceability-no-match" onResetFilters={resetListFilters} />
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
    </>
  );

  // #184: this panel used to run its own reachability query
  // (traceabilityApi.impact) and render a duplicate result list — that
  // computation now lives solely on the canonical `/impact` route. This
  // panel keeps only the workspace-scoped artifact picker (a convenience
  // `/impact`'s free-text search doesn't have) and hands off via
  // openImpactAnalysis(). See impact-preset.ts for the rationale.
  const detailPanel = (
    <section
      data-testid="impact-panel"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--space-4) var(--space-5)",
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
      <p
        style={{
          margin: "0 0 var(--space-3)",
          fontSize: "var(--font-size-sm)",
          color: "var(--color-text-muted)",
        }}
      >
        {t(
          "traceability.impactHint",
          "Wähle ein Artefakt und öffne die vollständige Impact-Analyse (interaktiver Baum, beide Richtungen)."
        )}
      </p>
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
            disabled={!hasArtifacts}
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

        <button
          type="button"
          data-testid="impact-run-btn"
          onClick={openImpactAnalysis}
          disabled={!impactArtifact}
          style={{
            padding: "var(--space-2) var(--space-4)",
            fontSize: "var(--font-size-base)",
            fontWeight: 500,
            background: "var(--color-primary)",
            color: "var(--color-on-primary, #fff)",
            border: "none",
            borderRadius: "var(--radius-md)",
            cursor: !impactArtifact ? "not-allowed" : "pointer",
          }}
        >
          {t("traceability.impactRun", "Impact-Analyse öffnen")}
        </button>
      </div>
    </section>
  );

  return (
    <div
      data-testid="traceability-view"
      style={{
        height: "100%",
        display: "flex",
        flexDirection: "column",
        fontFamily: "var(--font-sans)",
        color: "var(--color-text)",
      }}
    >
      <PageHeader
        title={t("nav.traceability")}
        count={{ shown: state.links.length, total: state.links.length }}
        primaryAction={{
          label: t("traceability.create"),
          onClick: () => setShowCreateDialog(true),
          disabled: !activeWorkspace,
          testId: "tracelink-create-btn",
        }}
        overflowActions={[
          {
            label: isExportingPdf ? "Exporting…" : "Export PDF",
            onClick: () => void handleExportPdf(),
            disabled: !activeWorkspace || isExportingPdf,
            testId: "export-pdf-btn",
          },
        ]}
      />

      <div style={{ flex: "1 1 auto", minHeight: 0 }}>
        <SplitView
          moduleType="traceability"
          leftPanel={listPanel}
          rightPanel={detailPanel}
        />
      </div>

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
    </div>
  );
}
