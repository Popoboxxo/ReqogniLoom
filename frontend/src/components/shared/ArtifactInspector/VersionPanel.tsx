/**
 * ArtifactInspector — VersionPanel (REQ-L2-RF-035).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L2-RF-035 (VersionPanel),
 *          REQ-L1-090 (VersionPanel),
 *          REQ-L0-062 AC5 (Version list, switch/compare affordance)
 *
 * Renders the version list of the inspected artifact inside the
 * ArtifactInspector right sidebar.
 *
 * Data source (per UI standards §5.1):
 *   GET /api/v1/<kind>/<id>/versions/   (all 10 kinds, REQ-142)
 *
 * All 10 artifact kinds now expose a `/versions/` endpoint. diagram and
 * glossary were the last two, wired in REQ-142 against their immutable
 * DiagramVersion / GlossaryTermVersion history tables.
 *
 * Issue #213 — not every listed version has content behind it. Types with a
 * real version table (diagram, glossary, goal, mainGoal, icd) return one row
 * per stored snapshot; single-row types return only the creation baseline and
 * the current state, numbered by an optimistic-lock counter. Rows report this
 * via `content_available`, and the panel disables actions that would need a
 * snapshot that was never stored.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { requirementsApi } from "../../../api/requirements";
import { architectureApi } from "../../../api/architecture";
import { stakeholderNeedApi } from "../../../api/stakeholder-need";
import { adrsApi } from "../../../api/adrs";
import { risksApi } from "../../../api/risks";
import { issuesApi } from "../../../api/issues";
import { testcasesApi } from "../../../api/testcases";
import { icdsApi } from "../../../api/icds";
import { diagramsApi } from "../../../api/diagrams";
import { glossaryApi } from "../../../api/glossary";
import { goalsApi } from "../../../api/goals";
import { mainGoalApi } from "../../../api/main-goal";
import type { ArtifactVersion } from "../../../types";
import {
  DIFF_SUPPORTED_KINDS,
  type ArtifactKind,
  type BaselineSummary,
  type VersionRef,
} from "./types";
import styles from "./VersionPanel.module.css";

// ---------------------------------------------------------------------------
// API dispatch — every kind the backend exposes a `/versions/` endpoint for.
// The base set mirrors DIFF_SUPPORTED_KINDS (same backend coverage), plus a
// few kinds that only expose `/versions/` without a matching `/diff/`
// endpoint yet (goal, mainGoal — REQ-L2-TE-020).
// ---------------------------------------------------------------------------

const VERSION_SUPPORTED_KINDS: ReadonlySet<ArtifactKind> = new Set([
  ...DIFF_SUPPORTED_KINDS,
  "goal",
  "mainGoal",
]);

/** Maps an ArtifactKind to its `versions(id)` fetcher. */
const VERSIONS_FETCHERS: Partial<
  Record<ArtifactKind, (id: string) => Promise<ArtifactVersion[]>>
> = {
  requirement: (id) => requirementsApi.versions(id),
  architecture: (id) => architectureApi.versions(id),
  stakeholderNeed: (id) => stakeholderNeedApi.versions(id),
  adr: (id) => adrsApi.versions(id),
  risk: (id) => risksApi.versions(id),
  issue: (id) => issuesApi.versions(id),
  testCase: (id) => testcasesApi.versions(id),
  icd: (id) => icdsApi.versions(id),
  diagram: (id) => diagramsApi.versions(id),
  glossary: (id) => glossaryApi.versions(id),
  goal: (id) => goalsApi.versions(id),
  mainGoal: (id) => mainGoalApi.versions(id),
};

function fetchVersions(kind: ArtifactKind, artifactId: string | number): Promise<VersionRef[]> {
  const map = (v: ArtifactVersion): VersionRef => ({
    version: v.version,
    label: v.label,
    createdAt: v.modified_at ?? null,
    baselineIds: [],
    // Backends that predate issue #213 omit the flag — assume retrievable.
    contentAvailable: v.content_available ?? true,
  });

  const fetcher = VERSIONS_FETCHERS[kind];
  if (!fetcher) return Promise.resolve([]);
  return fetcher(String(artifactId)).then((list) => list.map(map));
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface VersionPanelProps {
  kind: ArtifactKind;
  artifactId: string | number;
  /** The currently-active version (clicking another row emits onSwitch). */
  currentVersion: VersionRef | undefined;
  /** Emit when the user picks "Switch to v{n}" in the overflow menu. */
  onSwitch: (version: number) => void;
  /**
   * Emit when the user picks "Compare to current" in the overflow menu.
   * `a` is the version clicked, `b` is the currently-active version.
   */
  onCompare: (a: number, b: number) => void;
  /**
   * Optional baseline list (resolved by the parent hook). When provided
   * each version row renders a chip if it is pinned by one or more
   * baselines.
   */
  baselines?: ReadonlyArray<BaselineSummary>;
}



// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

type LoadState = "idle" | "loading" | "ready" | "empty" | "error";

export function VersionPanel({
  kind,
  artifactId,
  currentVersion,
  onSwitch,
  onCompare,
  baselines,
}: VersionPanelProps): JSX.Element {
  const { t } = useTranslation();
  const [state, setState] = useState<LoadState>("idle");
  const [versions, setVersions] = useState<VersionRef[]>([]);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [openMenuFor, setOpenMenuFor] = useState<number | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  // -------------------------------------------------------------------------
  // Data fetching
  // -------------------------------------------------------------------------

  const load = useCallback(async (): Promise<void> => {
    setState("loading");
    setErrorMessage(null);
    if (!VERSION_SUPPORTED_KINDS.has(kind)) {
      setVersions([]);
      setState("empty");
      return;
    }
    try {
      const list = await fetchVersions(kind, artifactId);
      if (list.length === 0) {
        // Both "no history" and "endpoint not implemented for this kind"
        // collapse to the same empty state today (UI standards §5.1 / §11).
        setVersions([]);
        setState("empty");
        return;
      }
      setVersions(list);
      setState("ready");
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : String(err));
      setState("error");
    }
  }, [kind, artifactId]);

  useEffect(() => {
    void load();
  }, [load]);

  // -------------------------------------------------------------------------
  // Overflow menu — close on outside click
  // -------------------------------------------------------------------------

  useEffect(() => {
    if (openMenuFor === null) return;
    function onDown(e: MouseEvent): void {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setOpenMenuFor(null);
      }
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [openMenuFor]);

  // -------------------------------------------------------------------------
  // Baseline chip lookup
  // -------------------------------------------------------------------------

  function baselinesForVersion(v: number): BaselineSummary[] {
    if (!baselines) return [];
    return baselines.filter((b) => b.pinnedVersion === v);
  }

  // -------------------------------------------------------------------------
  // Render
  // -------------------------------------------------------------------------

  function renderHeader(): JSX.Element {
    return (
      <h3 className={styles.title} id="inspector-version-label">
        {/* TODO(i18n): drop the literal fallback once en.json is deployed. */}
        {t("sidebar.version.title", "Version")}
      </h3>
    );
  }

  function renderSkeleton(): JSX.Element {
    return (
      <ol className={styles.list} aria-busy="true" aria-label={t("loading", "Loading...")}>
        {[0, 1, 2].map((i) => (
          <li key={i} className={styles.skeletonRow} aria-hidden="true" />
        ))}
      </ol>
    );
  }

  function renderEmpty(): JSX.Element {
    return (
      <p className={styles.emptyMessage} data-testid="version-empty">
        {/* TODO(i18n): copy will diverge once the backend supports more
            kinds — see UI standards §5.1. */}
        {t("sidebar.version.empty", "No version history for this artifact.")}
      </p>
    );
  }

  function renderError(): JSX.Element {
    return (
      <div className={styles.errorBanner} role="alert" data-testid="version-error">
        <span>
          {t("sidebar.version.error", "Could not load versions.")}
          {errorMessage ? ` (${errorMessage})` : ""}
        </span>
        <button
          type="button"
          className={styles.retryButton}
          data-testid="version-retry"
          onClick={(): void => void load()}
        >
          {/* TODO(i18n): add sidebar.version.retry key. */}
          {t("actions.reload", "Reload")}
        </button>
      </div>
    );
  }

  function renderRow(entry: VersionRef): JSX.Element {
    const isCurrent = currentVersion?.version === entry.version;
    // Issue #213: for single-row artifact types the version number is an
    // optimistic-lock counter, so only the current state (and the empty
    // creation baseline) has content behind it. Rows without a snapshot must
    // not offer "switch"/"compare" — the backend would 404 or, worse, answer
    // with the current state pretending it is history.
    const hasContent = entry.contentAvailable !== false;
    // Version 0 is the empty creation baseline: nothing to switch to, but it
    // is still a valid left-hand side for a diff ("everything was added").
    const canSwitch = hasContent && !isCurrent;
    const canCompare =
      (hasContent || entry.version === 0) && !isCurrent && currentVersion !== undefined;
    const chips = baselinesForVersion(entry.version);
    const chipLabel =
      chips.length === 1
        ? t("sidebar.version.baselineChip", { name: chips[0]!.name })
        : chips.length > 1
          ? t("sidebar.version.baselineChipPlural", { n: chips.length })
          : null;

    return (
      <li
        key={entry.version}
        className={`${styles.row} ${isCurrent ? styles.rowCurrent : ""}`}
        data-testid={`version-row-${entry.version}`}
      >
        <div className={styles.rowMain}>
          {isCurrent && (
            <span
              className={styles.currentDot}
              aria-label={t("sidebar.version.currentLabel", "Current")}
              title={t("sidebar.version.currentLabel", "Current")}
            />
          )}
          {/* H-03: the label truncates with an ellipsis on a narrow
              inspector (e.g. "Creation baseline"), so the full text has to
              stay reachable on hover. */}
          <span className={styles.versionLabel} title={entry.label}>
            {entry.label}
          </span>
          {chipLabel && (
            <span
              className={styles.baselineChip}
              title={chips.map((c) => c.name).join(", ")}
              data-testid={`version-baseline-${entry.version}`}
            >
              {chipLabel}
            </span>
          )}
          <span className={styles.date}>
            {entry.createdAt ? new Date(entry.createdAt).toLocaleString() : "—"}
          </span>
        </div>
        <div className={styles.rowActions} ref={openMenuFor === entry.version ? menuRef : null}>
          <button
            type="button"
            className={styles.overflowButton}
            aria-haspopup="menu"
            aria-expanded={openMenuFor === entry.version}
            // #741: the label named the row ("Version v3") but not the
            // action, so the "⋯" trigger announced identically to the row's
            // own version heading. Now says what activating it does, like
            // PageHeader's overflow trigger (pageHeader.moreLabel).
            aria-label={t("sidebar.version.menu.trigger", {
              n: entry.version,
              defaultValue: "Aktionen für Version v{{n}} öffnen",
            })}
            title={t("sidebar.version.menu.trigger", {
              n: entry.version,
              defaultValue: "Aktionen für Version v{{n}} öffnen",
            })}
            onClick={(): void =>
              setOpenMenuFor((prev) => (prev === entry.version ? null : entry.version))
            }
            data-testid={`version-overflow-${entry.version}`}
          >
            <span aria-hidden="true">⋯</span>
          </button>
          {openMenuFor === entry.version && (
            <ul className={styles.menu} role="menu">
              <li role="none">
                <button
                  type="button"
                  role="menuitem"
                  className={styles.menuItem}
                  disabled={!canSwitch}
                  title={
                    !hasContent
                      ? t(
                          "sidebar.version.noSnapshot",
                          "No stored snapshot for this version.",
                        )
                      : undefined
                  }
                  onClick={(): void => {
                    setOpenMenuFor(null);
                    onSwitch(entry.version);
                  }}
                  data-testid={`version-switch-${entry.version}`}
                >
                  {t("sidebar.version.menu.switch", { n: entry.version })}
                </button>
              </li>
              <li role="none">
                <button
                  type="button"
                  role="menuitem"
                  className={styles.menuItem}
                  disabled={!canCompare}
                  onClick={(): void => {
                    setOpenMenuFor(null);
                    if (currentVersion) onCompare(entry.version, currentVersion.version);
                  }}
                  data-testid={`version-compare-${entry.version}`}
                >
                  {t("sidebar.version.menu.compare", "Compare to current")}
                </button>
              </li>
            </ul>
          )}
        </div>
      </li>
    );
  }

  function renderList(): JSX.Element {
    return (
      <ol className={styles.list} aria-labelledby="inspector-version-label">
        {versions.map(renderRow)}
      </ol>
    );
  }

  return (
    <section
      className={styles.panel}
      role="region"
      aria-labelledby="inspector-version-label"
      data-testid="inspector-version-panel"
    >
      {renderHeader()}
      {state === "loading" && renderSkeleton()}
      {state === "empty" && renderEmpty()}
      {state === "error" && renderError()}
      {state === "ready" && renderList()}
    </section>
  );
}
