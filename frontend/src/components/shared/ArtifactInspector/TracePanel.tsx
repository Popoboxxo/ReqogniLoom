/**
 * ArtifactInspector — TracePanel (REQ-L2-RF-037).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L2-RF-037 (TracePanel),
 *          REQ-L1-092 (TracePanel),
 *          REQ-L0-062 AC4 (inbound + outbound trace links with
 *                          link-type filtering)
 *
 * Renders inbound + outbound trace links for the inspected artifact
 * with 8 link-type filter chips.
 *
 * Data source (per UI standards §5.3 / `frontend/src/api/tracelinks.ts`):
 *   GET /api/v1/tracelinks/?workspace_id=<ws>&artifact_id=<id>
 *
 * The 8 link types surfaced as filter chips are the public frontend
 * subset of the 12-value backend enum (UI standards §5.1).
 *
 * Data fetching (REQ-141): uses tracelinksApi.listForArtifact() to
 *   fetch links from the backend. Handles loading/error/empty states
 *   and maps backend TraceLink records to TraceLinkRow with artifact
 *   titles and kinds pre-resolved from the API response.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { tracelinksApi } from "../../../api/tracelinks";
import { useWorkspace } from "../../../context/WorkspaceContext";
import type { TraceLink } from "../../../types";
import { getLinkTypeLabel } from "../../../constants/traceLinkLabels";
import { getArtifactRoute } from "../../../utils/artifactRoutes";
import {
  ALL_LINK_TYPES,
  type ArtifactKind,
  type LinkType,
  type TraceLinkRow,
} from "./types";
import styles from "./TracePanel.module.css";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TracePanelProps {
  kind: ArtifactKind;
  artifactId: string | number;
}

// ---------------------------------------------------------------------------
// Link type mapping — backend enum -> frontend subset
// ---------------------------------------------------------------------------

function normalizeLinkType(raw: string): LinkType | null {
  const normalized = raw.replace(/_/g, "-") as LinkType;
  return ALL_LINK_TYPES.includes(normalized) ? normalized : null;
}

/**
 * Map a backend artifact_type string (PascalCase) to ArtifactKind.
 * REQ-002: source_type / target_type are now supplied by the backend.
 */
function artifactTypeToKind(rawType: string | undefined): ArtifactKind {
  switch (rawType) {
    case "ArchitectureElement":
      return "architecture";
    case "TestCase":
      return "testCase";
    case "StakeholderNeed":
      return "stakeholderNeed";
    case "Adr":
      return "adr";
    case "Requirement":
    default:
      return "requirement";
  }
}

function mapTraceLink(
  link: TraceLink,
  currentArtifactId: string
): TraceLinkRow | null {
  const isSource = link.source_id === currentArtifactId;
  const isTarget = link.target_id === currentArtifactId;
  if (!isSource && !isTarget) return null;

  const linkType = normalizeLinkType(link.link_type);
  if (!linkType) return null;

  const otherId = isSource ? link.target_id : link.source_id;

  // REQ-002: use backend-supplied title and type; fall back to truncated UUID
  // when the API response pre-dates the REQ-002 changes.
  const rawTitle = isSource ? link.target_title : link.source_title;
  const rawType = isSource ? link.target_type : link.source_type;
  const title =
    rawTitle && rawTitle.length > 0 ? rawTitle : `${otherId.slice(0, 8)}…`;
  const otherKind = artifactTypeToKind(rawType);

  return {
    id: link.id,
    direction: isSource ? "outbound" : "inbound",
    linkType,
    otherArtifact: {
      id: otherId,
      title,
      kind: otherKind,
      route: getArtifactRoute(otherKind, otherId),
    },
    createdAt: link.created_at,
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

export function TracePanel({ kind, artifactId }: TracePanelProps): JSX.Element {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const [state, setState] = useState<LoadState>("idle");
  const [links, setLinks] = useState<TraceLinkRow[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [activeFilters, setActiveFilters] = useState<Set<LinkType>>(
    () => new Set<LinkType>(ALL_LINK_TYPES)
  );
  const chipRowRef = useRef<HTMLDivElement | null>(null);

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  const load = useCallback(async (): Promise<void> => {
    setState("loading");
    setErrorMessage(null);
    if (!activeWorkspace) {
      setLinks([]);
      setState("empty");
      return;
    }
    try {
      const paginated = await tracelinksApi.listForArtifact(
        activeWorkspace.id,
        String(artifactId)
      );
      const mapped = paginated.results
        .map((link) => mapTraceLink(link, String(artifactId)))
        .filter((row): row is TraceLinkRow => row !== null);
      if (mapped.length === 0) {
        setLinks([]);
        setState("empty");
        return;
      }
      setLinks(mapped);
      setState("ready");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setState("error");
    }
  }, [kind, artifactId, activeWorkspace]);

  useEffect(() => {
    void load();
  }, [load]);

  // -------------------------------------------------------------------------
  // Filtering
  // -------------------------------------------------------------------------

  const filteredLinks = useMemo<TraceLinkRow[]>(
    () => links.filter((l) => activeFilters.has(l.linkType)),
    [links, activeFilters]
  );

  const inbound = useMemo<TraceLinkRow[]>(
    () => filteredLinks.filter((l) => l.direction === "inbound"),
    [filteredLinks]
  );

  const outbound = useMemo<TraceLinkRow[]>(
    () => filteredLinks.filter((l) => l.direction === "outbound"),
    [filteredLinks]
  );

  function toggleFilter(linkType: LinkType): void {
    setActiveFilters((prev) => {
      const next = new Set(prev);
      if (next.has(linkType)) {
        next.delete(linkType);
      } else {
        next.add(linkType);
      }
      return next;
    });
  }

  function clearFilters(): void {
    setActiveFilters(new Set());
  }

  function selectAllFilters(): void {
    setActiveFilters(new Set(ALL_LINK_TYPES));
  }

  // -------------------------------------------------------------------------
  // Keyboard navigation across filter chips (UI standards §9.2)
  // -------------------------------------------------------------------------

  function onChipKeyDown(e: React.KeyboardEvent<HTMLButtonElement>, idx: number): void {
    if (!chipRowRef.current) return;
    const chips = Array.from(
      chipRowRef.current.querySelectorAll<HTMLButtonElement>("[data-chip='true']")
    );
    if (chips.length === 0) return;

    if (e.key === "ArrowRight") {
      e.preventDefault();
      const next = chips[(idx + 1) % chips.length]!;
      next.focus();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      const prev = chips[(idx - 1 + chips.length) % chips.length]!;
      prev.focus();
    } else if (e.key === " ") {
      e.preventDefault();
      const target = e.currentTarget;
      const value = target.dataset.value as LinkType | undefined;
      if (value) toggleFilter(value);
    }
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  function renderHeader(): JSX.Element {
    return (
      <h3 className={styles.title} id="inspector-trace-label">
        {t("sidebar.trace.title", "Trace Links")}
      </h3>
    );
  }

  function renderFilterRow(): JSX.Element {
    const allSelected = activeFilters.size === ALL_LINK_TYPES.length;
    return (
      <div
        className={styles.filterRow}
        ref={chipRowRef}
        role="group"
        aria-label={t("sidebar.trace.filter.label", "Filter by type")}
      >
        {ALL_LINK_TYPES.map((lt, idx) => {
          const active = activeFilters.has(lt);
          return (
            <button
              key={lt}
              type="button"
              role="switch"
              aria-pressed={active}
              data-chip="true"
              data-value={lt}
              data-testid={`trace-filter-chip-${lt}`}
              className={`${styles.chip} ${active ? styles.chipActive : ""}`}
              onClick={(): void => toggleFilter(lt)}
              onKeyDown={(e): void => onChipKeyDown(e, idx)}
            >
              {getLinkTypeLabel(lt)}
            </button>
          );
        })}
        <button
          type="button"
          className={styles.clearButton}
          data-testid="trace-filter-toggle-all"
          onClick={allSelected ? clearFilters : selectAllFilters}
        >
          {allSelected
            ? t("sidebar.trace.filter.clear", "Clear")
            : t("sidebar.trace.filter.allSelected", "All types")}
        </button>
      </div>
    );
  }

  function renderRow(link: TraceLinkRow): JSX.Element {
    return (
      <li key={link.id} className={styles.row} data-testid={`trace-row-${link.id}`}>
        <button
          type="button"
          className={styles.rowButton}
          data-testid={`trace-row-open-${link.id}`}
          // #261: react-router 7's navigate() returns void | Promise<void>
          // (async view-transition support) — an explicit `: void` return
          // annotation here no longer type-checks against that.
          onClick={() => { void navigate(link.otherArtifact.route); }}
        >
          <span className={styles.linkType}>{getLinkTypeLabel(link.linkType)}</span>
          <span className={styles.artifactTitle}>{link.otherArtifact.title}</span>
        </button>
      </li>
    );
  }

  function renderSection(heading: string, rows: TraceLinkRow[], id: string): JSX.Element {
    return (
      <div className={styles.section}>
        <h4 className={styles.sectionHeading} id={id}>
          {heading} ({rows.length})
        </h4>
        {rows.length === 0 ? (
          <p className={styles.emptyMessage}>{t("sidebar.trace.empty", "No trace links.")}</p>
        ) : (
          <ul className={styles.list} aria-labelledby={id}>
            {rows.map(renderRow)}
          </ul>
        )}
      </div>
    );
  }

  function renderSkeleton(): JSX.Element {
    return (
      <div aria-busy="true" aria-label={t("loading", "Loading...")}>
        <div className={styles.skeletonChips} aria-hidden="true">
          {ALL_LINK_TYPES.map((lt) => (
            <span key={lt} className={styles.skeletonChip} />
          ))}
        </div>
        <div className={styles.skeletonRows} aria-hidden="true">
          <span className={styles.skeletonRow} />
          <span className={styles.skeletonRow} />
          <span className={styles.skeletonRow} />
        </div>
      </div>
    );
  }

  function renderError(): JSX.Element {
    return (
      <div className={styles.errorBanner} role="alert" data-testid="trace-error">
        <span>
          {t("sidebar.trace.error", "Could not load trace links.")}
          {errorMessage ? ` (${errorMessage})` : ""}
        </span>
        <button
          type="button"
          className={styles.retryButton}
          data-testid="trace-retry"
          onClick={(): void => void load()}
        >
          {t("actions.reload", "Reload")}
        </button>
      </div>
    );
  }

  return (
    <section
      className={styles.panel}
      role="region"
      aria-labelledby="inspector-trace-label"
      data-testid="inspector-trace-panel"
    >
      {renderHeader()}
      {state === "loading" && renderSkeleton()}
      {state === "error" && renderError()}
      {(state === "ready" || state === "empty") && (
        <>
          {renderFilterRow()}
          {state === "empty" ? (
            <p className={styles.emptyMessage} data-testid="trace-empty">
              {t("sidebar.trace.empty", "No trace links.")}
            </p>
          ) : (
            <>
              {renderSection(
                t("sidebar.trace.inbound", "Inbound"),
                inbound,
                "inspector-trace-inbound"
              )}
              {renderSection(
                t("sidebar.trace.outbound", "Outbound"),
                outbound,
                "inspector-trace-outbound"
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
