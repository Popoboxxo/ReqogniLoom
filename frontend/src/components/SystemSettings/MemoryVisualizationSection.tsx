/**
 * Memory Admin UI Phase 5 (spec 2026-08-26) — System-Admin memory
 * visualization (List / Cluster / Scatter), mounted in the "memory" tab in
 * SystemSettings, right after `MemoryManagementSection`.
 *
 * Two independent, lazily-loaded data sources feed the three views:
 *   - `entries/` (List view only) — paginated, full-text-filterable.
 *   - `projection/` (Cluster + Scatter views) — PCA points + cluster_id,
 *     cached client-side per scope key so switching between Cluster and
 *     Scatter (or back to a previously-viewed scope) never re-fetches.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "../../context/WorkspaceContext";
import {
  memoryVisualizationApi,
  type MemoryEntryRow,
  type MemoryProjection,
  type MemoryVizScope,
} from "../../api/memory-visualization";
import styles from "./MemoryVisualizationSection.module.css";

type VizView = "list" | "cluster" | "scatter";

const PAGE_SIZE = 25;
const FILTER_DEBOUNCE_MS = 300;
const SNIPPET_MAX_LEN = 140;
const SCATTER_VIEWBOX_WIDTH = 600;
const SCATTER_VIEWBOX_HEIGHT = 400;
const SCATTER_PADDING = 24;
const SCATTER_POINT_RADIUS = 4;

/** Cycling palette of already-established semantic tokens — no new hex, no new dependency. */
const CLUSTER_COLOR_CLASSES = [
  styles.clusterColor0,
  styles.clusterColor1,
  styles.clusterColor2,
  styles.clusterColor3,
  styles.clusterColor4,
  styles.clusterColor5,
  styles.clusterColor6,
  styles.clusterColor7,
];

function clusterColorClass(clusterId: number): string {
  const idx = ((clusterId % CLUSTER_COLOR_CLASSES.length) + CLUSTER_COLOR_CLASSES.length) %
    CLUSTER_COLOR_CLASSES.length;
  return CLUSTER_COLOR_CLASSES[idx];
}

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function truncate(text: string, maxLen: number): string {
  return text.length > maxLen ? `${text.slice(0, maxLen)}…` : text;
}

function scopeKey(scope: MemoryVizScope, workspaceId: string | undefined): string {
  return `${scope}:${workspaceId ?? ""}`;
}

/** Linear min/max mapping of projection points into the fixed SVG viewBox. */
function mapPointsToViewBox(
  points: MemoryProjection["points"]
): Array<{ id: string; cx: number; cy: number; cluster_id: number; owner_label: string }> {
  if (points.length === 0) return [];
  const xs = points.map((p) => p.x);
  const ys = points.map((p) => p.y);
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const spanX = maxX - minX || 1;
  const spanY = maxY - minY || 1;
  const innerW = SCATTER_VIEWBOX_WIDTH - 2 * SCATTER_PADDING;
  const innerH = SCATTER_VIEWBOX_HEIGHT - 2 * SCATTER_PADDING;
  return points.map((p) => ({
    id: p.id,
    cx: SCATTER_PADDING + ((p.x - minX) / spanX) * innerW,
    // Flip Y: SVG y-axis grows downward, plot y should grow upward.
    cy: SCATTER_PADDING + innerH - ((p.y - minY) / spanY) * innerH,
    cluster_id: p.cluster_id,
    owner_label: p.owner_label,
  }));
}

export function MemoryVisualizationSection(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();

  const [scope, setScope] = useState<MemoryVizScope>(activeWorkspace ? "workspace" : "global");
  const [view, setView] = useState<VizView>("list");

  // --- List view state -------------------------------------------------
  const [entries, setEntries] = useState<MemoryEntryRow[]>([]);
  const [entriesCount, setEntriesCount] = useState(0);
  const [entriesPage, setEntriesPage] = useState(1);
  const [entriesLoading, setEntriesLoading] = useState(false);
  const [entriesError, setEntriesError] = useState<string | null>(null);
  const [entriesLoaded, setEntriesLoaded] = useState(false);
  const [filterInput, setFilterInput] = useState("");
  const [filterQuery, setFilterQuery] = useState("");
  const filterDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // --- Projection (Cluster + Scatter) state, cached per scope key -------
  const [projection, setProjection] = useState<MemoryProjection | null>(null);
  const [projectionLoading, setProjectionLoading] = useState(false);
  const [projectionError, setProjectionError] = useState<string | null>(null);
  const projectionCacheRef = useRef<Map<string, MemoryProjection>>(new Map());

  // Monotonically-increasing request ids so a slow, stale response (e.g. the
  // admin toggled scope A -> B -> A again before A's first request returned)
  // can never overwrite state with data for a scope that's no longer active.
  const entriesRequestIdRef = useRef(0);
  const projectionRequestIdRef = useRef(0);

  const workspaceId = activeWorkspace?.id;

  // Scope can only be "workspace" while a workspace is active.
  useEffect(() => {
    if (scope === "workspace" && !workspaceId) {
      setScope("global");
    }
  }, [scope, workspaceId]);

  const loadEntries = useCallback(
    (targetPage: number): void => {
      if (scope === "workspace" && !workspaceId) return;
      const requestId = ++entriesRequestIdRef.current;
      setEntriesLoading(true);
      setEntriesError(null);
      memoryVisualizationApi
        .listEntries({
          scope,
          workspaceId: scope === "workspace" ? workspaceId : undefined,
          page: targetPage,
          pageSize: PAGE_SIZE,
          q: filterQuery || undefined,
        })
        .then((resp) => {
          if (requestId !== entriesRequestIdRef.current) return;
          setEntries(resp.results);
          setEntriesCount(resp.count);
          setEntriesPage(resp.page);
          setEntriesLoaded(true);
        })
        .catch((err: unknown) => {
          if (requestId !== entriesRequestIdRef.current) return;
          setEntriesError(extractErrorMessage(err));
          setEntries([]);
          setEntriesLoaded(true);
        })
        .finally(() => {
          if (requestId === entriesRequestIdRef.current) setEntriesLoading(false);
        });
    },
    [scope, workspaceId, filterQuery]
  );

  // Reload the list from page 1 whenever scope or the (debounced) filter changes,
  // but only while the List view is actually visible.
  useEffect(() => {
    if (view !== "list") return;
    loadEntries(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, scope, workspaceId, filterQuery]);

  const loadProjection = useCallback(
    (force = false): void => {
      if (scope === "workspace" && !workspaceId) return;
      const key = scopeKey(scope, scope === "workspace" ? workspaceId : undefined);
      const cached = projectionCacheRef.current.get(key);
      if (cached && !force) {
        setProjection(cached);
        setProjectionError(null);
        return;
      }
      const requestId = ++projectionRequestIdRef.current;
      setProjectionLoading(true);
      setProjectionError(null);
      memoryVisualizationApi
        .getProjection({
          scope,
          workspaceId: scope === "workspace" ? workspaceId : undefined,
        })
        .then((resp) => {
          projectionCacheRef.current.set(key, resp);
          if (requestId !== projectionRequestIdRef.current) return;
          setProjection(resp);
        })
        .catch((err: unknown) => {
          if (requestId !== projectionRequestIdRef.current) return;
          setProjectionError(extractErrorMessage(err));
          setProjection(null);
        })
        .finally(() => {
          if (requestId === projectionRequestIdRef.current) setProjectionLoading(false);
        });
    },
    [scope, workspaceId]
  );

  // Fetch (or serve from cache) the projection once the Cluster/Scatter view
  // is opened for the current scope — never on List view, never redundantly.
  useEffect(() => {
    if (view !== "cluster" && view !== "scatter") return;
    loadProjection(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [view, scope, workspaceId]);

  const handleScopeChange = (next: MemoryVizScope): void => {
    if (next === scope) return;
    setScope(next);
    setEntriesPage(1);
  };

  const handleFilterChange = (value: string): void => {
    setFilterInput(value);
    if (filterDebounceRef.current) clearTimeout(filterDebounceRef.current);
    filterDebounceRef.current = setTimeout(() => setFilterQuery(value), FILTER_DEBOUNCE_MS);
  };

  const entriesTotalPages = Math.max(1, Math.ceil(entriesCount / PAGE_SIZE));

  const clusterGroups = useMemo(() => {
    if (!projection) return [];
    const groups = new Map<number, MemoryProjection["points"]>();
    for (const p of projection.points) {
      const arr = groups.get(p.cluster_id) ?? [];
      arr.push(p);
      groups.set(p.cluster_id, arr);
    }
    return [...groups.entries()].sort((a, b) => a[0] - b[0]);
  }, [projection]);

  const scatterPoints = useMemo(
    () => (projection ? mapPointsToViewBox(projection.points) : []),
    [projection]
  );

  return (
    <section className={styles.section} data-testid="memory-visualization-section">
      <h3>{t("systemSettings.memory.viz.heading")}</h3>
      <p className={styles.hint}>{t("systemSettings.memory.viz.hint")}</p>

      <div className={styles.switcherRow}>
        <div className={styles.switcherGroup} role="group" aria-label={t("systemSettings.memory.viz.scopeLabel")}>
          <button
            type="button"
            data-testid="memory-viz-scope-workspace"
            className={
              scope === "workspace" ? styles.switcherButtonActive : styles.switcherButton
            }
            disabled={!workspaceId}
            onClick={() => handleScopeChange("workspace")}
          >
            {t("systemSettings.memory.viz.scopeWorkspace")}
          </button>
          <button
            type="button"
            data-testid="memory-viz-scope-global"
            className={scope === "global" ? styles.switcherButtonActive : styles.switcherButton}
            onClick={() => handleScopeChange("global")}
          >
            {t("systemSettings.memory.viz.scopeGlobal")}
          </button>
        </div>

        <div className={styles.switcherGroup} role="group" aria-label={t("systemSettings.memory.viz.viewLabel")}>
          <button
            type="button"
            data-testid="memory-viz-view-list"
            className={view === "list" ? styles.switcherButtonActive : styles.switcherButton}
            onClick={() => setView("list")}
          >
            {t("systemSettings.memory.viz.viewList")}
          </button>
          <button
            type="button"
            data-testid="memory-viz-view-cluster"
            className={view === "cluster" ? styles.switcherButtonActive : styles.switcherButton}
            onClick={() => setView("cluster")}
          >
            {t("systemSettings.memory.viz.viewCluster")}
          </button>
          <button
            type="button"
            data-testid="memory-viz-view-scatter"
            className={view === "scatter" ? styles.switcherButtonActive : styles.switcherButton}
            onClick={() => setView("scatter")}
          >
            {t("systemSettings.memory.viz.viewScatter")}
          </button>
        </div>
      </div>

      {view === "list" && (
        <div data-testid="memory-viz-list-view">
          <div className={styles.filterRow}>
            <input
              type="text"
              data-testid="memory-viz-filter-input"
              className={styles.filterInput}
              placeholder={t("systemSettings.memory.viz.filterPlaceholder")}
              value={filterInput}
              onChange={(e) => handleFilterChange(e.target.value)}
              aria-label={t("systemSettings.memory.viz.filterPlaceholder")}
            />
          </div>

          {entriesError && (
            <p role="alert" data-testid="memory-viz-list-error" className={styles.error}>
              {entriesError}
            </p>
          )}

          {entriesLoading && (
            <p role="status" className={styles.loading}>
              {t("systemSettings.memory.viz.loading")}
            </p>
          )}

          {!entriesLoading && !entriesError && entriesLoaded && entries.length === 0 && (
            <p data-testid="memory-viz-list-empty" className={styles.empty}>
              {t("systemSettings.memory.viz.listEmpty")}
            </p>
          )}

          {!entriesLoading && entries.length > 0 && (
            <>
              <table className={styles.table} data-testid="memory-viz-list-table">
                <thead>
                  <tr>
                    <th>{t("systemSettings.memory.viz.colContent")}</th>
                    <th>{t("systemSettings.memory.viz.colTimestamp")}</th>
                    <th>{t("systemSettings.memory.viz.colConfidence")}</th>
                    <th>{t("systemSettings.memory.viz.colOwner")}</th>
                  </tr>
                </thead>
                <tbody>
                  {entries.map((row) => (
                    <tr key={row.id} data-testid={`memory-viz-row-${row.id}`}>
                      <td className={styles.contentCell} title={row.content}>
                        {truncate(row.content, SNIPPET_MAX_LEN)}
                      </td>
                      <td>{formatDate(row.created_at)}</td>
                      <td>{row.confidence.toFixed(2)}</td>
                      <td>{row.owner_label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {entriesCount > PAGE_SIZE && (
                <div className={styles.pagination}>
                  <button
                    type="button"
                    data-testid="memory-viz-list-prev"
                    className={styles.pageButton}
                    disabled={entriesPage <= 1 || entriesLoading}
                    onClick={() => loadEntries(entriesPage - 1)}
                  >
                    {t("systemSettings.memory.viz.prev")}
                  </button>
                  <span className={styles.pageInfo}>
                    {t("systemSettings.memory.viz.pageInfo", {
                      page: entriesPage,
                      totalPages: entriesTotalPages,
                    })}
                  </span>
                  <button
                    type="button"
                    data-testid="memory-viz-list-next"
                    className={styles.pageButton}
                    disabled={entriesPage >= entriesTotalPages || entriesLoading}
                    onClick={() => loadEntries(entriesPage + 1)}
                  >
                    {t("systemSettings.memory.viz.next")}
                  </button>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {(view === "cluster" || view === "scatter") && (
        <div data-testid={`memory-viz-${view}-view`}>
          {projectionError && (
            <p role="alert" data-testid="memory-viz-projection-error" className={styles.error}>
              {projectionError}
            </p>
          )}

          {projectionLoading && (
            <p role="status" className={styles.loading}>
              {t("systemSettings.memory.viz.loading")}
            </p>
          )}

          {!projectionLoading && !projectionError && projection && (
            <>
              {projection.sampled && (
                <p data-testid="memory-viz-sampled-notice" className={styles.notice}>
                  {t("systemSettings.memory.viz.sampledNotice", {
                    sampleSize: projection.sample_size,
                    totalSize: projection.total_size,
                  })}
                </p>
              )}
              {projection.excluded_no_embedding > 0 && (
                <p data-testid="memory-viz-excluded-notice" className={styles.notice}>
                  {t("systemSettings.memory.viz.excludedNoEmbeddingNotice", {
                    count: projection.excluded_no_embedding,
                  })}
                </p>
              )}

              {projection.points.length === 0 && (
                <p data-testid="memory-viz-projection-empty" className={styles.empty}>
                  {t("systemSettings.memory.viz.projectionEmpty")}
                </p>
              )}

              {view === "cluster" && projection.points.length > 0 && (
                <div className={styles.clusterList} data-testid="memory-viz-cluster-list">
                  {clusterGroups.map(([clusterId, members]) => (
                    <div
                      key={clusterId}
                      className={styles.clusterGroup}
                      data-testid={`memory-viz-cluster-group-${clusterId}`}
                    >
                      <div className={styles.clusterGroupHeader}>
                        <span
                          aria-hidden="true"
                          className={`${styles.clusterSwatch} ${clusterColorClass(clusterId)}`}
                        />
                        {t("systemSettings.memory.viz.clusterLabel", {
                          id: clusterId,
                          count: members.length,
                        })}
                      </div>
                      <div className={styles.clusterMembers}>
                        {members.map((m) => (
                          <span key={m.id} className={styles.clusterMember}>
                            {m.owner_label}
                          </span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {view === "scatter" && projection.points.length > 0 && (
                <div className={styles.scatterWrapper} data-testid="memory-viz-scatter-plot">
                  <svg
                    className={styles.scatterSvg}
                    viewBox={`0 0 ${SCATTER_VIEWBOX_WIDTH} ${SCATTER_VIEWBOX_HEIGHT}`}
                    role="img"
                    aria-label={t("systemSettings.memory.viz.scatterAriaLabel")}
                  >
                    {scatterPoints.map((p) => (
                      <circle
                        key={p.id}
                        data-testid={`memory-viz-scatter-point-${p.id}`}
                        className={`${styles.scatterPoint} ${clusterColorClass(p.cluster_id)}`}
                        cx={p.cx}
                        cy={p.cy}
                        r={SCATTER_POINT_RADIUS}
                      >
                        <title>{p.owner_label}</title>
                      </circle>
                    ))}
                  </svg>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </section>
  );
}
