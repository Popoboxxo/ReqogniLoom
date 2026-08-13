/**
 * ARCH-L1-001 ReactFrontend — ImpactView (Impact-Graph-Visualisierung).
 *
 * NOTE ON REQ-ID: this component was requested under "REQ-006", but
 * REQ-006 in docs/REQUIREMENTS.md already denotes "Soft-Delete-Statusmodell"
 * (unrelated). No REQ-ID for an impact-tree visualization exists yet — see
 * the final task report for a flag to the `requirements` agent to register
 * the correct ID before this file is committed.
 *
 * Autonomous architecture decision (per task brief): no external graph
 * library. MVP renders the impact/trace graph as an expandable, lazily
 * loaded recursive tree instead of a canvas/SVG graph — avoids a new
 * dependency and keeps the interaction model consistent with the existing
 * WorkspaceTree pattern (REQ-003).
 *
 * Each node fetches its own upstream+downstream trace links on first
 * expand (tracelinksApi.listForArtifact) and groups them by link_type +
 * direction. Recursion is capped at MAX_DEPTH to keep the tree bounded
 * even in cyclic or densely-linked graphs.
 *
 * Interfaces consumed:
 *   IF-RF-EXT-OUT-001 → GET /api/v1/search/?q=...&workspace_id=<id>
 *   IF-RF-EXT-OUT-001 → GET /api/v1/tracelinks/?workspace_id=<id>&artifact_id=<id>
 *
 * issue #184: this is the canonical impact-analysis surface. TraceabilityView
 * used to run a second, overlapping reachability query inline — that panel
 * now only pre-selects an artifact and hands it off here via sessionStorage
 * (see impact-preset.ts), so the root can be loaded directly without a
 * repeat search.
 *
 * issue #415: the tree traverses trace links in *both* directions, so without
 * a visited set every edge can be walked straight back (`L1 -> L2 -> L1 -> …`)
 * — five artifacts and four links expanded into 25+ nodes. Each node now
 * carries the set of artifact ids on its path from the root; a child already
 * on that path is rendered once, marked as a cycle, and cannot be expanded
 * again. The root additionally derives its own title from the endpoint
 * metadata of its first link fetch, so a handed-off root without a resolved
 * title no longer stays a bare UUID while its children show titles.
 */

import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { tracelinksApi } from "../../api/tracelinks";
import { searchApi } from "../../api/search";
import type { SearchHit } from "../../api/search";
import { useWorkspace } from "../../context/WorkspaceContext";
import { getLinkTypeLabel } from "../../constants/traceLinkLabels";
import { PageHeader } from "../shared/PageHeader";
import { IMPACT_PRESET_STORAGE_KEY } from "./impact-preset";
import {
  endpointOf,
  formatShortId,
  neighborOf,
  type TraceDirection,
} from "../../utils/traceEndpoints";
import styles from "./ImpactView.module.css";
import type { TraceLink, UUID } from "../../types";

/** Maximum tree depth — bounds recursion for cyclic/dense trace graphs. */
const MAX_DEPTH = 4;

/** Stable empty path set for the root node (#415) — avoids a new Set per render. */
const EMPTY_VISITED: ReadonlySet<UUID> = new Set<UUID>();

/** A resolved artifact endpoint of a trace link (id + display metadata). */
interface TreeArtifact {
  id: UUID;
  title: string;
  artifactType: string;
}

/** One outgoing/incoming trace-link edge from a tree node to a child artifact. */
interface ChildEdge {
  link: TraceLink;
  direction: TraceDirection;
  child: TreeArtifact;
  /** #415: child already occurs on the path from the root — do not recurse. */
  isCycle: boolean;
}

/**
 * Builds child edges from the raw TraceLink list returned for a node.
 * "outgoing" means the current node is the link's source ("A derives-from B"
 * read as A -> B); "incoming" means the current node is the target.
 *
 * #415: duplicate edges (same direction, link type and child) collapse into
 * one, and edges pointing back onto the node's own path are flagged so the
 * renderer can stop the traversal there instead of oscillating forever.
 */
function toChildEdges(
  nodeId: UUID,
  links: TraceLink[],
  visitedIds: ReadonlySet<UUID>
): ChildEdge[] {
  const selfIds: ReadonlySet<UUID> = new Set([nodeId]);
  const edges: ChildEdge[] = [];
  const seen = new Set<string>();
  for (const link of links) {
    const neighbor = neighborOf(link, selfIds);
    if (!neighbor) continue; // self-link or unrelated link
    const dedupeKey = `${neighbor.direction}:${link.link_type}:${neighbor.endpoint.id}`;
    if (seen.has(dedupeKey)) continue;
    seen.add(dedupeKey);
    edges.push({
      link,
      direction: neighbor.direction,
      child: neighbor.endpoint,
      isCycle: visitedIds.has(neighbor.endpoint.id),
    });
  }
  return edges;
}

/**
 * #415: the artifact a node was fetched for appears on one side of every link
 * returned for it, with its title resolved by the backend — so a node handed
 * in without a title can recover its own from the first fetch.
 */
function selfTitleFromLinks(nodeId: UUID, links: TraceLink[]): TreeArtifact | null {
  for (const link of links) {
    for (const side of ["source", "target"] as const) {
      const endpoint = endpointOf(link, side);
      if (endpoint.id === nodeId && endpoint.title) {
        return { id: nodeId, title: endpoint.title, artifactType: endpoint.artifactType };
      }
    }
  }
  return null;
}

/** Groups child edges by "direction:link_type" so the tree renders one
 * sub-heading per trace-link kind (e.g. "-> derives from", "<- satisfies"). */
function groupEdges(edges: ChildEdge[]): [string, ChildEdge[]][] {
  const groups = new Map<string, ChildEdge[]>();
  for (const edge of edges) {
    const key = `${edge.direction}:${edge.link.link_type}`;
    const bucket = groups.get(key);
    if (bucket) bucket.push(edge);
    else groups.set(key, [edge]);
  }
  return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
}

// ---------------------------------------------------------------------------
// ArtifactTreeNode — recursive, lazily-expandable tree node
// ---------------------------------------------------------------------------

interface ArtifactTreeNodeProps {
  workspaceId: UUID;
  node: TreeArtifact;
  depth: number;
  onlyActive: boolean;
  /**
   * #415: artifact ids on the path from the root down to (and including) this
   * node. A child already in this set closes a cycle and is not expandable.
   */
  visitedIds: ReadonlySet<UUID>;
  /** #415: this node closes a cycle — render it, but never traverse further. */
  isCycle?: boolean;
}

function ArtifactTreeNode({
  workspaceId,
  node,
  depth,
  onlyActive,
  visitedIds,
  isCycle = false,
}: ArtifactTreeNodeProps): JSX.Element {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<boolean>(false);
  const [edges, setEdges] = useState<ChildEdge[] | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  // #415: title recovered from the node's own link fetch when the caller could
  // not supply one (e.g. a root handed over from the traceability view).
  const [resolvedSelf, setResolvedSelf] = useState<TreeArtifact | null>(null);

  const atMaxDepth = depth >= MAX_DEPTH;
  const childVisitedIds = useMemo(
    () => new Set<UUID>([...visitedIds, node.id]),
    [visitedIds, node.id]
  );

  const toggle = async (): Promise<void> => {
    if (atMaxDepth || isCycle) return;
    if (expanded) {
      setExpanded(false);
      return;
    }
    if (edges === null) {
      setLoading(true);
      setError(null);
      try {
        const resp = await tracelinksApi.listForArtifact(workspaceId, node.id);
        setEdges(toChildEdges(node.id, resp.results, childVisitedIds));
        if (!node.title) setResolvedSelf(selfTitleFromLinks(node.id, resp.results));
      } catch (err: unknown) {
        const msg =
          (err as { error?: { message?: string } })?.error?.message ??
          String(err);
        setError(msg);
        setEdges([]);
      } finally {
        setLoading(false);
      }
    }
    setExpanded(true);
  };

  // "Active" links are those resolving to a real, still-existing artifact
  // title. Dangling links (empty title — e.g. orphaned/deleted target) are
  // hidden when the filter is on. No dedicated "active" flag exists on
  // TraceLink yet (see header note).
  const visibleEdges = (edges ?? []).filter(
    (edge) => !onlyActive || edge.child.title !== ""
  );
  const groups = groupEdges(visibleEdges);

  // #415: root and child nodes share one title code path — backend-resolved
  // title first, then the title recovered from this node's own links, then a
  // shortened id (never the full raw UUID the audit saw on the root).
  const displayType = node.artifactType || resolvedSelf?.artifactType || "?";
  const displayTitle =
    node.title || resolvedSelf?.title || formatShortId(node.id);
  const toggleDisabled = atMaxDepth || isCycle;

  return (
    <div style={{ marginLeft: depth === 0 ? 0 : "var(--space-5)" }}>
      <div
        data-testid="impact-tree-node"
        data-depth={depth}
        data-cycle={isCycle ? "true" : undefined}
        style={{
          display: "flex",
          alignItems: "center",
          gap: "var(--space-2)",
          padding: "var(--space-2) var(--space-1)",
          borderBottom: "1px solid var(--color-border)",
        }}
      >
        <button
          type="button"
          data-testid="impact-node-toggle"
          onClick={() => void toggle()}
          disabled={toggleDisabled}
          aria-expanded={expanded}
          title={
            isCycle
              ? t("impact.cycleDetected", "Bereits im Pfad enthalten (Zyklus)")
              : atMaxDepth
                ? t("impact.maxDepthReached", "Maximale Tiefe erreicht")
                : undefined
          }
          style={{
            background: "none",
            border: "none",
            cursor: toggleDisabled ? "not-allowed" : "pointer",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
            width: "1.25em",
            padding: 0,
          }}
        >
          {toggleDisabled ? "·" : expanded ? "▼" : "▶"}
        </button>
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
          {displayType}
        </span>
        <span style={{ fontWeight: 500, color: "var(--color-text)" }}>
          {displayTitle}
        </span>
        {isCycle && (
          <span data-testid="impact-cycle-badge" className={styles.cycleBadge}>
            ↺ {t("impact.cycleBadge", "Zyklus")}
          </span>
        )}
      </div>

      {expanded && (
        <div>
          {loading && (
            <p
              role="status"
              style={{
                fontSize: "var(--font-size-sm)",
                color: "var(--color-text-muted)",
                margin: "var(--space-2) 0 var(--space-2) var(--space-5)",
              }}
            >
              {t("loading")}
            </p>
          )}
          {error && (
            <p
              role="alert"
              data-testid="impact-node-error"
              style={{
                color: "var(--color-danger)",
                fontSize: "var(--font-size-sm)",
                margin: "var(--space-2) 0 var(--space-2) var(--space-5)",
              }}
            >
              {error}
            </p>
          )}
          {!loading && !error && groups.length === 0 && (
            <p
              data-testid="impact-node-empty"
              style={{
                fontSize: "var(--font-size-sm)",
                color: "var(--color-text-muted)",
                margin: "var(--space-2) 0 var(--space-2) var(--space-5)",
              }}
            >
              {t("impact.noLinks", "Keine weiteren Verknüpfungen.")}
            </p>
          )}
          {!loading &&
            !error &&
            groups.map(([key, groupEdgesForKey]) => {
              const [direction, linkType] = key.split(":");
              const arrow = direction === "outgoing" ? "→" : "←";
              return (
                <div
                  key={key}
                  data-testid="impact-link-group"
                  data-link-type={linkType}
                  style={{ marginLeft: "var(--space-5)" }}
                >
                  <div
                    style={{
                      fontSize: "var(--font-size-xs)",
                      color: "var(--color-text-muted)",
                      fontWeight: 600,
                      textTransform: "uppercase",
                      letterSpacing: "0.03em",
                      padding: "var(--space-2) 0 var(--space-1)",
                    }}
                  >
                    {arrow} {getLinkTypeLabel(linkType)}
                  </div>
                  {groupEdgesForKey.map((edge) => (
                    <ArtifactTreeNode
                      key={edge.link.id}
                      workspaceId={workspaceId}
                      node={edge.child}
                      depth={depth + 1}
                      onlyActive={onlyActive}
                      visitedIds={childVisitedIds}
                      isCycle={edge.isCycle}
                    />
                  ))}
                </div>
              );
            })}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ImpactView — search-driven root selector + recursive tree
// ---------------------------------------------------------------------------

export function ImpactView(): JSX.Element {
  const { t } = useTranslation();
  const { activeWorkspace } = useWorkspace();
  const [query, setQuery] = useState<string>("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [searching, setSearching] = useState<boolean>(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [rootArtifact, setRootArtifact] = useState<TreeArtifact | null>(null);
  const [onlyActive, setOnlyActive] = useState<boolean>(false);

  // issue #184: one-shot preset handoff from TraceabilityView's artifact
  // picker — read once on mount, then cleared so a later plain visit to
  // /impact always starts from the normal search flow.
  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(IMPACT_PRESET_STORAGE_KEY);
      if (!raw) return;
      sessionStorage.removeItem(IMPACT_PRESET_STORAGE_KEY);
      const preset = JSON.parse(raw) as { id?: string; title?: string; artifactType?: string };
      // #415: only the id is mandatory. Requiring title+type meant a handoff
      // whose title could not be resolved was dropped entirely; the node now
      // recovers both from its own trace-link fetch.
      if (preset.id) {
        setRootArtifact({
          id: preset.id,
          title: preset.title ?? "",
          artifactType: preset.artifactType ?? "",
        });
        if (preset.title) setQuery(preset.title);
      }
    } catch {
      // Malformed/absent preset — fall back to the normal search flow.
    }
  }, []);

  const runSearch = async (): Promise<void> => {
    if (!activeWorkspace || !query.trim()) return;
    setSearching(true);
    setSearchError(null);
    try {
      const resp = await searchApi.search(query.trim(), activeWorkspace.id, {
        limit: 10,
      });
      setHits(resp.results);
    } catch (err: unknown) {
      const msg =
        (err as { error?: { message?: string } })?.error?.message ??
        String(err);
      setSearchError(msg);
      setHits([]);
    } finally {
      setSearching(false);
    }
  };

  const selectHit = (hit: SearchHit): void => {
    setRootArtifact({
      id: hit.id,
      title: hit.title,
      artifactType: hit.artifact_type,
    });
    setHits([]);
    setQuery(hit.title);
  };

  return (
    <div data-testid="impact-view">
      <PageHeader
        title={t("nav.impact", "Impact-Analyse")}
        summary={
          rootArtifact
            ? t("impact.summaryRootSelected", "Ausgehend von: {{title}}", {
                title: rootArtifact.title,
              })
            : t("impact.summaryNoRoot", "Kein Artefakt ausgewählt")
        }
      />

      {!activeWorkspace ? (
        <p style={{ color: "var(--color-text-muted)" }}>
          {t("traceability.noArtifacts", "Keine Architekturelemente verfügbar. Bitte zuerst Elemente anlegen.")}
        </p>
      ) : (
        <>
          <section
            style={{
              background: "var(--color-surface)",
              border: "1px solid var(--color-border)",
              borderRadius: "var(--radius-lg)",
              padding: "var(--space-4) var(--space-5)",
              marginBottom: "var(--space-6)",
              boxShadow: "var(--shadow-card)",
            }}
          >
            <div style={{ display: "flex", gap: "var(--space-3)", flexWrap: "wrap" }}>
              <input
                type="search"
                data-testid="impact-search-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    void runSearch();
                  }
                }}
                placeholder={t(
                  "impact.searchPlaceholder",
                  "Start-Artefakt suchen (Name oder ID)…"
                )}
                style={{
                  flex: "1 1 320px",
                  padding: "var(--space-2) var(--space-3)",
                  borderRadius: "var(--radius-md)",
                  border: "1px solid var(--color-border)",
                  fontSize: "var(--font-size-base)",
                }}
              />
              <button
                type="button"
                data-testid="impact-search-btn"
                onClick={() => void runSearch()}
                disabled={!query.trim() || searching}
                style={{
                  padding: "var(--space-2) var(--space-4)",
                  fontSize: "var(--font-size-base)",
                  fontWeight: 500,
                  background: "var(--color-primary)",
                  color: "var(--color-on-primary)",
                  border: "none",
                  borderRadius: "var(--radius-md)",
                  cursor: !query.trim() || searching ? "not-allowed" : "pointer",
                }}
              >
                {searching
                  ? t("nav.searching", "Suche läuft...")
                  : t("impact.load", "Artefakt laden")}
              </button>
            </div>

            {searchError && (
              <p
                role="alert"
                data-testid="impact-search-error"
                style={{
                  color: "var(--color-danger)",
                  fontSize: "var(--font-size-sm)",
                  marginTop: "var(--space-3)",
                }}
              >
                {searchError}
              </p>
            )}

            {hits.length > 0 && (
              <ul
                data-testid="impact-search-results"
                style={{
                  listStyle: "none",
                  margin: "var(--space-3) 0 0",
                  padding: 0,
                  border: "1px solid var(--color-border)",
                  borderRadius: "var(--radius-md)",
                  overflow: "hidden",
                }}
              >
                {hits.map((hit) => (
                  <li key={hit.id}>
                    <button
                      type="button"
                      data-testid="impact-search-result"
                      onClick={() => selectHit(hit)}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: "var(--space-2)",
                        width: "100%",
                        padding: "var(--space-2) var(--space-3)",
                        border: "none",
                        borderBottom: "1px solid var(--color-border)",
                        background: "var(--color-surface)",
                        color: "var(--color-text)",
                        fontSize: "var(--font-size-base)",
                        textAlign: "left",
                        cursor: "pointer",
                      }}
                    >
                      <span
                        style={{
                          fontSize: "var(--font-size-xs)",
                          background: "var(--color-surface-raised)",
                          padding: "2px 8px",
                          borderRadius: "var(--radius-full)",
                          color: "var(--color-text-muted)",
                          fontWeight: 500,
                        }}
                      >
                        {hit.artifact_type}
                      </span>
                      <span>{hit.title}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {rootArtifact && (
            <section
              data-testid="impact-tree-panel"
              style={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "var(--radius-lg)",
                padding: "var(--space-4) var(--space-5)",
                boxShadow: "var(--shadow-card)",
              }}
            >
              <label
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: "var(--space-2)",
                  fontSize: "var(--font-size-sm)",
                  color: "var(--color-text)",
                  marginBottom: "var(--space-4)",
                  cursor: "pointer",
                }}
              >
                <input
                  type="checkbox"
                  data-testid="impact-only-active-toggle"
                  checked={onlyActive}
                  onChange={(e) => setOnlyActive(e.target.checked)}
                />
                {t("impact.onlyActive", "Nur aktive Verknüpfungen")}
              </label>

              <ArtifactTreeNode
                workspaceId={activeWorkspace.id}
                node={rootArtifact}
                depth={0}
                onlyActive={onlyActive}
                visitedIds={EMPTY_VISITED}
              />
            </section>
          )}
        </>
      )}
    </div>
  );
}
