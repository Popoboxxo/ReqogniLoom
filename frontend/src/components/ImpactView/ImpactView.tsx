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
 */

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { tracelinksApi } from "../../api/tracelinks";
import { searchApi } from "../../api/search";
import type { SearchHit } from "../../api/search";
import { useWorkspace } from "../../context/WorkspaceContext";
import { getLinkTypeLabel } from "../../constants/traceLinkLabels";
import type { TraceLink, UUID } from "../../types";

/** Maximum tree depth — bounds recursion for cyclic/dense trace graphs. */
const MAX_DEPTH = 4;

/** A resolved artifact endpoint of a trace link (id + display metadata). */
interface TreeArtifact {
  id: UUID;
  title: string;
  artifactType: string;
}

/** One outgoing/incoming trace-link edge from a tree node to a child artifact. */
interface ChildEdge {
  link: TraceLink;
  direction: "outgoing" | "incoming";
  child: TreeArtifact;
}

/**
 * Builds child edges from the raw TraceLink list returned for a node.
 * "outgoing" means the current node is the link's source ("A derives-from B"
 * read as A -> B); "incoming" means the current node is the target.
 */
function toChildEdges(nodeId: UUID, links: TraceLink[]): ChildEdge[] {
  return links
    .map((link) => {
      const outgoing = link.source_id === nodeId;
      const child: TreeArtifact = outgoing
        ? {
            id: link.target_id,
            title: link.target_title ?? "",
            artifactType: link.target_type ?? "",
          }
        : {
            id: link.source_id,
            title: link.source_title ?? "",
            artifactType: link.source_type ?? "",
          };
      return { link, direction: outgoing ? "outgoing" : "incoming", child } as ChildEdge;
    })
    .filter((edge) => edge.child.id !== nodeId);
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
}

function ArtifactTreeNode({
  workspaceId,
  node,
  depth,
  onlyActive,
}: ArtifactTreeNodeProps): JSX.Element {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState<boolean>(false);
  const [edges, setEdges] = useState<ChildEdge[] | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const atMaxDepth = depth >= MAX_DEPTH;

  const toggle = async (): Promise<void> => {
    if (atMaxDepth) return;
    if (expanded) {
      setExpanded(false);
      return;
    }
    if (edges === null) {
      setLoading(true);
      setError(null);
      try {
        const resp = await tracelinksApi.listForArtifact(workspaceId, node.id);
        setEdges(toChildEdges(node.id, resp.results));
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

  return (
    <div style={{ marginLeft: depth === 0 ? 0 : "var(--space-5)" }}>
      <div
        data-testid="impact-tree-node"
        data-depth={depth}
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
          disabled={atMaxDepth}
          aria-expanded={expanded}
          title={
            atMaxDepth
              ? t("impact.maxDepthReached", "Maximale Tiefe erreicht")
              : undefined
          }
          style={{
            background: "none",
            border: "none",
            cursor: atMaxDepth ? "not-allowed" : "pointer",
            fontSize: "var(--font-size-sm)",
            color: "var(--color-text-muted)",
            width: "1.25em",
            padding: 0,
          }}
        >
          {atMaxDepth ? "·" : expanded ? "▼" : "▶"}
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
          {node.artifactType || "?"}
        </span>
        <span style={{ fontWeight: 500, color: "var(--color-text)" }}>
          {node.title || node.id}
        </span>
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
      <h2
        style={{
          fontSize: "var(--font-size-2xl)",
          fontWeight: 700,
          color: "var(--color-text)",
          margin: "0 0 var(--space-6)",
        }}
      >
        {t("nav.impact", "Impact-Analyse")}
      </h2>

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
                  color: "var(--color-on-primary, #fff)",
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
              />
            </section>
          )}
        </>
      )}
    </div>
  );
}
