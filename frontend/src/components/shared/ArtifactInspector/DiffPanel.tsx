/**
 * ArtifactInspector — DiffPanel (REQ-L2-RF-036).
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L2-RF-036 (DiffPanel),
 *          REQ-L1-091 (DiffPanel),
 *          REQ-L2-RF-014 (visual diff rendering — reuses ArtifactDiff),
 *          REQ-L0-062 AC6 (field-level diff between two versions)
 *
 * Wraps the existing `ArtifactDiff` component into a 360-px-friendly
 * column. All twelve artifact kinds expose a `/diff/` endpoint (REQ-142,
 * GH-1200), so the former "unsupported" empty state is deleted (#1762/M8,
 * I-15) — there is no kind left without a comparison.
 */
import { useCallback, useState } from "react";
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
import type { ArtifactDiffResult, ArtifactVersion } from "../../../types";
import {
  ArtifactDiff,
  type ArtifactDiffRange,
  type DiffEntityType,
} from "../../ArtifactDiff/ArtifactDiff";
import { DIFF_SUPPORTED_KINDS, type ArtifactKind } from "./types";
import styles from "./DiffPanel.module.css";

// ---------------------------------------------------------------------------
// Fetcher dispatch — every kind the backend exposes a `/diff/` endpoint for.
// ---------------------------------------------------------------------------

type DiffFetcher = (id: string, from: number, to: number) => Promise<ArtifactDiffResult>;
type VersionsFetcher = (id: string) => Promise<ArtifactVersion[]>;

const DIFF_FETCHERS: Partial<Record<ArtifactKind, DiffFetcher>> = {
  requirement: (id, from, to) => requirementsApi.diff(id, from, to),
  architecture: (id, from, to) => architectureApi.diff(id, from, to),
  stakeholderNeed: (id, from, to) => stakeholderNeedApi.diff(id, from, to),
  adr: (id, from, to) => adrsApi.diff(id, from, to),
  risk: (id, from, to) => risksApi.diff(id, from, to),
  issue: (id, from, to) => issuesApi.diff(id, from, to),
  testCase: (id, from, to) => testcasesApi.diff(id, from, to),
  icd: (id, from, to) => icdsApi.diff(id, from, to),
  diagram: (id, from, to) => diagramsApi.diff(id, from, to),
  glossary: (id, from, to) => glossaryApi.diff(id, from, to),
  // GH-1200: Goal/MainGoal expose a lineage-anchored `/diff/` action now.
  goal: (id, from, to) => goalsApi.diff(id, from, to),
  mainGoal: (id, from, to) => mainGoalApi.diff(id, from, to),
};

const VERSIONS_FETCHERS: Partial<Record<ArtifactKind, VersionsFetcher>> = {
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
  // GH-1200: matching `/versions/` fetchers for the two Goal kinds.
  goal: (id) => goalsApi.versions(id),
  mainGoal: (id) => mainGoalApi.versions(id),
};

function diffFetcherFor(kind: ArtifactKind): DiffFetcher {
  const fetcher = DIFF_FETCHERS[kind];
  if (!fetcher) throw new Error(`Unsupported diff kind: ${kind}`);
  return fetcher;
}

function versionsFetcherFor(kind: ArtifactKind): VersionsFetcher {
  const fetcher = VERSIONS_FETCHERS[kind];
  if (!fetcher) throw new Error(`Unsupported versions kind: ${kind}`);
  return fetcher;
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface DiffPanelProps {
  kind: ArtifactKind;
  /**
   * The **domain-entity** id (`Requirement.id`, `ArchitectureElement.id`, …)
   * — `ArtifactDiff` fetches `/<kind>/<id>/diff/`, which is keyed on it, not
   * on the backing Artifact UUID (see the shell's prop docs, #1763).
   */
  entityId: string | number;
  /**
   * Requested "from" version of the diff (lower in the timeline). A request,
   * not a guarantee: `ArtifactDiff` owns the version list and falls back to
   * its own seeding when this value is not a real version below the "to" side
   * (M-04).
   */
  leftVersion: number;
  /** The "to" version of the diff (higher in the timeline). */
  rightVersion: number;
  /**
   * The range `ArtifactDiff` actually resolved. The tab form renders its one
   * pair line ("Basis … → Arbeitsstand vN") from this — never from the
   * request above (M-04).
   */
  onRangeResolved?: (range: ArtifactDiffRange | null) => void;
  /**
   * `"panel"` is the legacy stacked form (kept for the panel's own contract
   * tests): own `h3` heading and
   * own polite live region. `"tab"` drops both — the tab label names the area
   * and the shell owns the single live region (#1762, spec §2.1/§5.3).
   */
  variant?: "panel" | "tab";
}

// ---------------------------------------------------------------------------
// Mapping helper
// ---------------------------------------------------------------------------

/**
 * Maps an ArtifactKind to the DiffEntityType that `ArtifactDiff` accepts.
 * `DiffEntityType` is an alias of `ArtifactKind` and every kind is backend-
 * backed (`DIFF_SUPPORTED_KINDS` covers all twelve, I-15) — so this is the
 * identity, and the old "unsupported" branch is gone (#1762/M8). The runtime
 * set check stays as a guard for a kind added to the union but missed in the
 * backend: it fails loudly in development instead of silently rendering an
 * empty state that pretends the comparison succeeded.
 */
function mapKindToDiffEntityType(kind: ArtifactKind): DiffEntityType {
  if (!DIFF_SUPPORTED_KINDS.has(kind)) {
    throw new Error(`DiffPanel: unsupported ArtifactKind "${kind}" (no /diff/ endpoint)`);
  }
  return kind;
}



// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DiffPanel({
  kind,
  entityId,
  leftVersion,
  rightVersion,
  onRangeResolved,
  variant = "panel",
}: DiffPanelProps): JSX.Element {
  const { t } = useTranslation();
  const isTab = variant === "tab";
  const entityType = mapKindToDiffEntityType(kind);
  // M-04: the range actually resolved and rendered by ArtifactDiff. `null`
  // until the version list has loaded.
  const [range, setRange] = useState<ArtifactDiffRange | null>(null);
  // Stable identity so it does not re-trigger ArtifactDiff's seeding effect.
  const handleRangeChange = useCallback(
    (next: ArtifactDiffRange | null): void => {
      setRange((prev) =>
        prev &&
        next &&
        prev.from === next.from &&
        prev.to === next.to &&
        prev.isInitialState === next.isInitialState
          ? prev
          : next,
      );
      onRangeResolved?.(next);
    },
    [onRangeResolved],
  );

  const sectionLabels = isTab
    ? { "aria-label": t("sidebar.diff.title") }
    : { "aria-labelledby": "inspector-diff-label" };

  return (
    <section className={styles.panel} role="region" {...sectionLabels} data-testid="inspector-diff-panel">
      {!isTab && (
        <h3 className={styles.title} id="inspector-diff-label">
          {t("sidebar.diff.title")}
        </h3>
      )}
      {/* Polite live region — assistive tech announces the comparison
          range when the diff finishes loading. (UI standards §9.1.)

          M-04: this used to read the panel's own `leftVersion`/`rightVersion`
          props, which the ArtifactInspector seeds to the *same* number — so
          it announced "Comparing v1 → v1", a comparison of a version against
          itself, while the panel below was in fact showing 0 → 1. It now
          reports the range ArtifactDiff resolved, and names the
          no-predecessor case instead of dressing it up as a comparison.

          Tab form (#1762): the shell owns the single polite region; a second
          one here would speak the same fact twice (spec §5.3). */}
      {!isTab && (
        <div className={styles.liveRegion} role="status" aria-live="polite">
          {range === null
            ? ""
            : range.isInitialState
              ? t("sidebar.diff.initialState", "Ausgangszustand v{{to}} — kein Vorgänger vorhanden", {
                  to: range.to,
                })
              : t("sidebar.diff.compareCurrent", "Comparing v{{from}} → v{{to}}", {
                  from: range.from,
                  to: range.to,
                })}
        </div>
      )}
      <div className={styles.diffFrame}>
        <ArtifactDiff
          entityId={String(entityId)}
          entityType={entityType}
          currentVersion={rightVersion}
          initialFromVersion={leftVersion}
          onRangeChange={handleRangeChange}
          diffFetcher={diffFetcherFor(kind)}
          versionsFetcher={versionsFetcherFor(kind)}
          onClose={(): void => {
            /* no-op — the inspector is persistent; per UI standards §1.2
               the close button must not unmount the inspector. */
          }}
        />
      </div>
    </section>
  );
}
