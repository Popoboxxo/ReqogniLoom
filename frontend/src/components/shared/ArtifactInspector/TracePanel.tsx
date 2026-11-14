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
import { CreateTraceLinkDialog } from "../CreateTraceLinkDialog";
import { LINKS_ROWS_ONLY, isSpineLinkType } from "./inspectorContract";
import { useInspectorAnnouncer, useInspectorCounts } from "./InspectorLiveRegions";
import { type ArtifactKind, type LinkType, type TraceLinkRow } from "./types";
import styles from "./TracePanel.module.css";

/** How many chips the skeleton draws before the catalog has loaded. */
const SKELETON_CHIP_COUNT = 8;

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface TracePanelProps {
  kind: ArtifactKind;
  /**
   * The **domain-entity** id (`Requirement.id`, `ArchitectureElement.id`, …).
   * `GET /tracelinks/?artifact_id=` accepts either id space and resolves the
   * entity-side id server-side (`TraceLinkService.list_links_for_entity`), so
   * this panel deliberately stays on the entity side — the backing Artifact
   * UUID is not published for every kind (#1763).
   */
  entityId: string | number;
  /**
   * `"panel"` (default) is the stacked RightSidebar form: own `h3` heading,
   * own `role="alert"` banner, every link type as a row.
   *
   * `"tab"` is the Links tab of the tabbed shell (#1762). It follows spec
   * §2.3: derivation/verification links are read as rows only in the spine,
   * so this tab summarises them in **one** line with a jump and lists only the
   * remaining types. The shell owns the live regions, so the panel announces
   * through it instead of rendering its own.
   *
   * The tab also owns the create entry (`CreateTraceLinkDialog`, #1827): it
   * replaced the stacked panel whose header carried it, and it has to stay
   * reachable when the artifact has no links at all.
   */
  variant?: "panel" | "tab";
  /**
   * Jump into the trace spine (spec §2.3 rule 1). Only meaningful in the tab
   * form; without it the summary line stays a plain count (types without a
   * spine never show the line at all).
   */
  onShowInSpine?: () => void;
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

  // REQ-002: use backend-supplied title and type. A missing title is kept
  // empty here — the row supplies a readable-id / localised fallback, so a
  // nameless neighbour never renders a meaningless UUID fragment (C-L9).
  const rawTitle = isSource ? link.target_title : link.source_title;
  const rawType = isSource ? link.target_type : link.source_type;
  const rawUid = isSource ? link.target_uid : link.source_uid;
  const title = rawTitle ?? "";
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
      // Readable id when the API supplies one — the row uses it as its
      // title fallback (see renderRow). Undefined on today's serializer.
      uid: rawUid,
    },
    createdAt: link.created_at,
  };
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

export function TracePanel({
  kind,
  entityId,
  variant = "panel",
  onShowInSpine,
}: TracePanelProps): JSX.Element {
  const { t } = useTranslation();
  // Async callbacks must not depend on `t`'s identity: some hosts (and test
  // harnesses) return a fresh function per render, which would turn the
  // fetch effect into a loop. The ref keeps the latest `t` without re-keying
  // the callback.
  const tRef = useRef(t);
  tRef.current = t;
  const navigate = useNavigate();
  const { activeWorkspace } = useWorkspace();
  const { linkTypes, labelFor } = useLinkTypes();
  const announcer = useInspectorAnnouncer();
  const reportCount = useInspectorCounts()?.reportCount;
  const isTab = variant === "tab";
  // Spec §2.3 rule 5: without a spine the tab lists every type as a row.
  const rowsOnly = LINKS_ROWS_ONLY.has(kind);
  // A retry announces its own outcome, never an extra `linksLoaded`.
  const retryingRef = useRef(false);
  // Late fetch after unmount must not announce (see VersionPanel).
  const mountedRef = useRef(true);
  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);
  const [state, setState] = useState<LoadState>("idle");
  const [links, setLinks] = useState<TraceLinkRow[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // #1762 M2 follow-up: the tab replaced the stacked `TraceLinkPanel`, whose
  // header carried the "new link" entry. Without it the empty state had no way
  // out — read "no links yet", leave, find another surface (#1827).
  const [createOpen, setCreateOpen] = useState(false);
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
    const panelLabel = tRef.current("sidebar.inspector.tab.links", "Links");
    const wasRetry = retryingRef.current;
    const announceOutcome = (total: number, derived: number): void => {
      reportCount?.("links", total);
      retryingRef.current = false;
      if (!isTab || !announcer) return;
      announcer.polite(
        wasRetry
          ? tRef.current("sidebar.inspector.live.retrySucceeded", {
              panel: panelLabel,
              defaultValue: "{{panel}} loaded.",
            })
          : tRef.current("sidebar.inspector.live.linksLoaded", {
              count: total,
              derived,
              defaultValue: "{{count}} links loaded, {{derived}} shown in the spine.",
            }),
      );
    };
    if (!activeWorkspace) {
      setLinks([]);
      setState("empty");
      announceOutcome(0, 0);
      return;
    }
    try {
      const paginated = await tracelinksApi.listForArtifact(
        activeWorkspace.id,
        String(entityId)
      );
      const mapped = paginated.results
        .map((link) => mapTraceLink(link, String(entityId)))
        .filter((row): row is TraceLinkRow => row !== null);
      if (!mountedRef.current) return;
      if (mapped.length === 0) {
        setLinks([]);
        setState("empty");
        announceOutcome(0, 0);
        return;
      }
      setLinks(mapped);
      setState("ready");
      announceOutcome(mapped.length, mapped.filter((row) => isSpineLinkType(row.linkType)).length);
    } catch (err) {
      if (!mountedRef.current) return;
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setState("error");
      if (isTab && announcer) {
        retryingRef.current = false;
        announcer.alert(
          wasRetry
            ? tRef.current("sidebar.inspector.live.retryFailed", {
                panel: panelLabel,
                defaultValue: "{{panel}} still unavailable.",
              })
            : tRef.current("sidebar.inspector.error.links", {
                panel: panelLabel,
                defaultValue: "{{panel}} could not be loaded. Try again.",
              }),
        );
      }
    }
    // `kind` is deliberately NOT a dependency: the fetch is keyed by
    // `activeWorkspace` + `entityId` only, and a `kind`-only change cannot
    // alter the result set (it previously just triggered a redundant refetch).
  }, [entityId, activeWorkspace, isTab, announcer, reportCount]);

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
      // N3: trim before testing — a whitespace-only catalog label ("   ") is
      // just as unnamed as an empty one and used to win the branch below.
      const fromCatalog = labelFor(key, "en", "neutral").trim();
      // labelFor already falls back to the raw key; prefer the static
      // built-in table over a bare key so a pre-catalog render still reads
      // like a label. An empty (or whitespace-only) catalog label — a
      // workspace can save one — is treated the same way: it would otherwise
      // render a nameless chip and trace-row button (C-L9).
      if (fromCatalog && fromCatalog !== key) return fromCatalog;
      return getLinkTypeLabel(key).trim() || key;
    },
    [labelFor]
  );

  const filteredLinks = useMemo<TraceLinkRow[]>(
    () => links.filter((l) => !deselected.has(l.linkType)),
    [links, deselected]
  );

  // Spec §2.3: with a spine, the derivation/verification group is read there
  // and only summarised here; without one, every type stays a row. The
  // partitioning is a **tab-form** rule — the stacked panel keeps showing
  // every link (its routes have no spine tab yet, M2–M7).
  const partition = isTab && !rowsOnly;

  const spineLinks = useMemo<TraceLinkRow[]>(
    () => (partition ? filteredLinks.filter((l) => isSpineLinkType(l.linkType)) : []),
    [partition, filteredLinks]
  );

  const rowLinks = useMemo<TraceLinkRow[]>(
    () =>
      partition
        ? filteredLinks.filter((l) => !isSpineLinkType(l.linkType))
        : filteredLinks,
    [partition, filteredLinks]
  );

  const inbound = useMemo<TraceLinkRow[]>(
    () => rowLinks.filter((l) => l.direction === "inbound"),
    [rowLinks]
  );

  const outbound = useMemo<TraceLinkRow[]>(
    () => rowLinks.filter((l) => l.direction === "outbound"),
    [rowLinks]
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
    // Tab form: the tab label names the area; a second heading inside the tab
    // panel would break the "one heading per area" rule (spec §2.1/§7).
    //
    // The create entry still has to live here. In the stacked form it is the
    // `TraceLinkPanel` header that offers it; the tab has no such header, so
    // without this row an artifact with zero links rendered a dead end — the
    // `links-empty` message and nothing to act on (#1827).
    if (isTab) {
      // No workspace, no link to create: the dialog needs a `workspaceId` to
      // resolve targets, so the action is withheld instead of failing later.
      if (!activeWorkspace) return <></>;
      return (
        <div className={styles.actionsRow}>
          <button
            type="button"
            className="btn-primary"
            data-testid="trace-link-panel-open-dialog"
            onClick={(): void => setCreateOpen(true)}
          >
            {t("actions.newLink")}
          </button>
        </div>
      );
    }
    return (
      <h3 className={styles.title} id="inspector-trace-label">
        {t("sidebar.trace.title")}
      </h3>
    );
  }

  /**
   * Spec §2.3 rule 1: the derivation/verification group is read in the spine.
   * Here it is exactly one line with a jump — a counter plus an affordance,
   * not a second list of the same links.
   */
  function renderSpineSummary(): JSX.Element {
    return (
      <div className={styles.summaryRow} data-testid="inspector-links-summary">
        <span className={styles.summaryText}>
          {t("sidebar.inspector.linksSummary", {
            count: spineLinks.length,
            defaultValue: "{{count}} derivation and verification links — in the spine",
          })}
        </span>
        {onShowInSpine && spineLinks.length > 0 && (
          <button
            type="button"
            className="btn-ghost"
            onClick={onShowInSpine}
            data-testid="inspector-links-show-in-spine"
          >
            {t("sidebar.inspector.action.showInSpine")}
          </button>
        )}
      </div>
    );
  }

  function renderFilterRow(): JSX.Element {
    const allSelected = chipTypes.every((lt) => !deselected.has(lt));
    return (
      <div
        className={styles.filterRow}
        ref={chipRowRef}
        role="group"
        aria-label={t("sidebar.trace.filter.label")}
      >
        {chipTypes.map((lt, idx) => {
          const active = !deselected.has(lt);
          return (
            <button
              key={lt}
              type="button"
              role="switch"
              // `role="switch"` requires `aria-checked` (jsx-a11y
              // role-has-required-aria-props); `aria-pressed` belongs to the
              // toggle-button pattern. The other three switches in this
              // codebase (SidebarNavigation, DiagramGraphEditorPage,
              // WorkflowEditorHeader) already use `aria-checked`.
              aria-checked={active}
              data-chip="true"
              data-value={lt}
              data-testid={`trace-filter-chip-${lt}`}
              className={`btn-ghost ${styles.chip} ${active ? styles.chipActive : ""}`}
              onClick={(): void => toggleFilter(lt)}
              onKeyDown={(e): void => onChipKeyDown(e, idx)}
            >
              {chipLabel(lt)}
            </button>
          );
        })}
        <button
          type="button"
          className={`btn-ghost ${styles.clearButton}`}
          data-testid="trace-filter-toggle-all"
          onClick={allSelected ? clearFilters : selectAllFilters}
        >
          {allSelected
            ? t("sidebar.trace.filter.clear")
            : t("sidebar.trace.filter.allSelected")}
        </button>
      </div>
    );
  }

  function renderRow(link: TraceLinkRow): JSX.Element {
    const typeLabel = chipLabel(link.linkType);
    const rawTitle = link.otherArtifact.title.trim();
    // C-L9: a link whose other endpoint has no title rendered an empty button
    // label. Fall back to the readable id, then to a localised placeholder, so
    // every row carries content (and therefore an accessible name).
    const title = rawTitle || link.otherArtifact.uid || t("sidebar.trace.untitled");
    // No `aria-label`: `title` is never empty, so the two visible spans
    // already name the button in both locales (First Rule of ARIA — do not
    // duplicate visible text into an attribute).

    return (
      <li key={link.id} className={styles.row} data-testid={`trace-row-${link.id}`}>
        <button
          type="button"
          className={`btn-ghost ${styles.rowButton}`}
          data-testid={`trace-row-open-${link.id}`}
          // #261: react-router 7's navigate() returns void | Promise<void>
          // (async view-transition support) — an explicit `: void` return
          // annotation here no longer type-checks against that.
          onClick={() => { void navigate(link.otherArtifact.route); }}
        >
          <span className={styles.linkType}>{typeLabel}</span>
          <span className={styles.artifactTitle}>{title}</span>
        </button>
      </li>
    );
  }

  function renderSection(heading: string, rows: TraceLinkRow[], id: string): JSX.Element {
    // Spec §7: the inspector has h2 (surface) → h3 (area) only; the tab form
    // must not introduce a fourth level.
    const SectionHeading = isTab ? "h3" : "h4";
    return (
      <div className={styles.section}>
        <SectionHeading className={styles.sectionHeading} id={id}>
          {heading} ({rows.length})
        </SectionHeading>
        {rows.length === 0 ? (
          <p className={styles.emptyMessage}>{t("sidebar.trace.empty")}</p>
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
      <div aria-busy="true" aria-label={t("loading")}>
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
      <div
        className={styles.errorBanner}
        role={isTab ? undefined : "alert"}
        data-testid="trace-error"
      >
        <span>
          {t("sidebar.trace.error")}
          {errorMessage ? ` (${errorMessage})` : ""}
        </span>
        <button
          type="button"
          className={`btn-secondary ${styles.retryButton}`}
          data-testid="trace-retry"
          onClick={(): void => {
            retryingRef.current = true;
            void load();
          }}
        >
          {t("actions.reload")}
        </button>
      </div>
    );
  }

  const sectionLabels = isTab
    ? { "aria-label": t("sidebar.inspector.tab.links") }
    : { "aria-labelledby": "inspector-trace-label" };

  return (
    <section
      className={styles.panel}
      role="region"
      {...sectionLabels}
      data-testid="inspector-trace-panel"
    >
      {renderHeader()}
      {state === "loading" && renderSkeleton()}
      {state === "error" && renderError()}
      {(state === "ready" || state === "empty") && (
        <>
          {isTab && !rowsOnly && renderSpineSummary()}
          {renderFilterRow()}
          {state === "empty" ? (
            <p className={styles.emptyMessage} data-testid={isTab ? "links-empty" : "trace-empty"}>
              {isTab
                ? rowsOnly
                  ? t("sidebar.inspector.empty.linksAll")
                  : t("sidebar.inspector.empty.linksOther")
                : t("sidebar.trace.empty")}
            </p>
          ) : (
            <>
              {renderSection(
                t("sidebar.trace.inbound"),
                inbound,
                "inspector-trace-inbound"
              )}
              {renderSection(
                t("sidebar.trace.outbound"),
                outbound,
                "inspector-trace-outbound"
              )}
            </>
          )}
        </>
      )}
      {/* Same modal the stacked `TraceLinkPanel` mounts (REQ-005). `entityId`
          is the domain-entity id the dialog's element list is keyed on, so the
          two surfaces create identical links. */}
      {isTab && activeWorkspace && (
        <CreateTraceLinkDialog
          workspaceId={activeWorkspace.id}
          sourceId={String(entityId)}
          isOpen={createOpen}
          onClose={(): void => setCreateOpen(false)}
          onCreated={(): void => {
            setCreateOpen(false);
            // Exactly one refetch and one announcement: `load()` reports the
            // new count through the shell's live region, the create action
            // itself stays silent.
            void load();
          }}
          defaultLinkType={activeWorkspace.default_link_type || "derives-from"}
        />
      )}
    </section>
  );
}
