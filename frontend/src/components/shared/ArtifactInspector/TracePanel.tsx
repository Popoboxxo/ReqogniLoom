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
 * with one link-type filter chip per catalog type.
 *
 * Data source (per UI standards §5.3 / `frontend/src/api/tracelinks.ts`):
 *   GET /api/v1/tracelinks/?workspace_id=<ws>&artifact_id=<id>
 *
 * The chip list comes from the per-workspace link-type catalog
 * (`useLinkTypes()`), not from a static frontend table. This panel used to
 * carry its own hardcoded 8-value `ALL_LINK_TYPES` list and *drop* every
 * link whose type was not in it — a second source of truth that survived
 * the catalog migration and silently hid five of the eight real types.
 * Nothing is dropped any more: a link whose type the catalog does not know
 * still renders, under a chip labelled with its raw key (the same
 * fallback-to-raw-key convention `getTriLabel` uses).
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
import { useLinkTypes } from "../../../context/LinkTypeContext";
import { useWorkspace } from "../../../context/WorkspaceContext";
import type { TraceLink } from "../../../types";
import { getLinkTypeLabel } from "../../../constants/traceLinkLabels";
import { getArtifactRoute } from "../../../utils/artifactRoutes";
import { type ArtifactKind, type LinkType, type TraceLinkRow } from "./types";
import styles from "./TracePanel.module.css";

/** How many chips the skeleton draws before the catalog has loaded. */
const SKELETON_CHIP_COUNT = 8;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TracePanelProps {
  kind: ArtifactKind;
  artifactId: string | number;
}

// ---------------------------------------------------------------------------
// Link type mapping
// ---------------------------------------------------------------------------

/**
 * Normalize a backend link-type key for display/filtering.
 *
 * Underscores only: this is a spelling fix (`derives_from` -> `derives-from`),
 * never a membership test. Filtering an unknown key out here is exactly the
 * bug this panel used to have.
 */
function normalizeLinkType(raw: string): LinkType {
  return raw.replace(/_/g, "-");
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
  const { linkTypes, labelFor } = useLinkTypes();
  const [state, setState] = useState<LoadState>("idle");
  const [links, setLinks] = useState<TraceLinkRow[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // Tracked as the *de*selected set, not the selected one: the chip list is
  // async (catalog) plus data-driven (types actually present on this
  // artifact), so a "selected" set would have to be re-seeded every time it
  // grows — and any chip missed by that re-seed would hide links. Everything
  // is visible until the user switches something off.
  const [deselected, setDeselected] = useState<Set<LinkType>>(
    () => new Set<LinkType>()
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

  /**
   * Chips: the workspace catalog first (stable order, includes types this
   * artifact has no link of yet), then any type actually present on the
   * artifact that the catalog does not list — a retired, tenant-invented or
   * not-yet-loaded key. The second half is what keeps a link visible instead
   * of silently dropping it.
   */
  const chipTypes = useMemo<LinkType[]>(() => {
    const fromCatalog = linkTypes.map((row) => row.key);
    const known = new Set(fromCatalog);
    const extras = [...new Set(links.map((l) => l.linkType))].filter(
      (key) => !known.has(key)
    );
    return [...fromCatalog, ...extras];
  }, [linkTypes, links]);

  const chipLabel = useCallback(
    (key: LinkType): string => {
      const fromCatalog = labelFor(key, "en", "neutral");
      // labelFor already falls back to the raw key; prefer the static
      // built-in table over a bare key so a pre-catalog render still reads
      // like a label.
      return fromCatalog === key ? getLinkTypeLabel(key) : fromCatalog;
    },
    [labelFor]
  );

  const filteredLinks = useMemo<TraceLinkRow[]>(
    () => links.filter((l) => !deselected.has(l.linkType)),
    [links, deselected]
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
    setDeselected((prev) => {
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
    setDeselected(new Set(chipTypes));
  }

  function selectAllFilters(): void {
    setDeselected(new Set());
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
    const allSelected = chipTypes.every((lt) => !deselected.has(lt));
    return (
      <div
        className={styles.filterRow}
        ref={chipRowRef}
        role="group"
        aria-label={t("sidebar.trace.filter.label", "Filter by type")}
      >
        {chipTypes.map((lt, idx) => {
          const active = !deselected.has(lt);
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
              {chipLabel(lt)}
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
          <span className={styles.linkType}>{chipLabel(link.linkType)}</span>
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
          {Array.from({ length: SKELETON_CHIP_COUNT }, (_, i) => (
            <span key={i} className={styles.skeletonChip} />
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
