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
 * column. As of REQ-142 all 10 artifact kinds expose a `/diff/` endpoint,
 * so the "unsupported" empty state below is now unreachable in practice
 * but kept as a defensive fallback (UI standards §4.5).
 */
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
import type { ArtifactDiffResult, ArtifactVersion } from "../../../types";
import { ArtifactDiff, type DiffEntityType } from "../../ArtifactDiff/ArtifactDiff";
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
  artifactId: string | number;
  /** The "from" version of the diff (lower in the timeline). */
  leftVersion: number;
  /** The "to" version of the diff (higher in the timeline). */
  rightVersion: number;
}

// ---------------------------------------------------------------------------
// Mapping helper
// ---------------------------------------------------------------------------

/**
 * Maps an ArtifactKind to the DiffEntityType that `ArtifactDiff` accepts.
 * `DiffEntityType` is an alias of `ArtifactKind`, so this is the identity
 * for backend-supported kinds and null otherwise — the panel renders the
 * empty state when null.
 */
function mapKindToDiffEntityType(kind: ArtifactKind): DiffEntityType | null {
  return DIFF_SUPPORTED_KINDS.has(kind) ? kind : null;
}



// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function DiffPanel({
  kind,
  artifactId,
  leftVersion,
  rightVersion,
}: DiffPanelProps): JSX.Element {
  const { t } = useTranslation();
  const entityType = mapKindToDiffEntityType(kind);

  if (entityType === null) {
    return (
      <section
        className={styles.panel}
        role="region"
        aria-labelledby="inspector-diff-label"
        data-testid="inspector-diff-panel"
      >
        <h3 className={styles.title} id="inspector-diff-label">
          {t("sidebar.diff.title", "Diff")}
        </h3>
        <p className={styles.emptyMessage} data-testid="diff-unsupported">
          {t("sidebar.diff.unsupported", "Diff is not yet available for {{kind}} artifacts.", {
            kind,
          })}
        </p>
      </section>
    );
  }

  return (
    <section
      className={styles.panel}
      role="region"
      aria-labelledby="inspector-diff-label"
      data-testid="inspector-diff-panel"
    >
      <h3 className={styles.title} id="inspector-diff-label">
        {t("sidebar.diff.title", "Diff")}
      </h3>
      {/* Polite live region — assistive tech announces the comparison
          range when the diff finishes loading. (UI standards §9.1.) */}
      <div className={styles.liveRegion} role="status" aria-live="polite">
        {t("sidebar.diff.compareCurrent", "Comparing v{{from}} → v{{to}}", {
          from: leftVersion,
          to: rightVersion,
        })}
      </div>
      <div className={styles.diffFrame}>
        <ArtifactDiff
          entityId={String(artifactId)}
          entityType={entityType}
          currentVersion={rightVersion}
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
