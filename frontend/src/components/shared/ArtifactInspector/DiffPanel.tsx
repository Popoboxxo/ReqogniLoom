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
 * column and renders a "Diff not yet available" empty state for the 8
 * artifact kinds whose backend has no `/diff/` endpoint today
 * (UI standards §4.5, §11).
 *
 * TODO(backend): extend `DiffEntityType` in
 *   `frontend/src/components/ArtifactDiff/ArtifactDiff.tsx` from
 *   `"requirement" | "architecture"` to the full 10-value union and
 *   wire `diffFetcher`/`versionsFetcher` per kind (see UI standards
 *   §4.5). Today: only requirement + architecture are supported; the
 *   other 8 kinds show the "unsupported" empty state.
 */
import { useTranslation } from "react-i18next";
import { requirementsApi } from "../../../api/requirements";
import { architectureApi } from "../../../api/architecture";
import { ArtifactDiff, type DiffEntityType } from "../../ArtifactDiff/ArtifactDiff";
import { DIFF_SUPPORTED_KINDS, type ArtifactKind } from "./types";
import styles from "./DiffPanel.module.css";

// ---------------------------------------------------------------------------
// Real fetcher dispatch — requirement + architecture only.
// ---------------------------------------------------------------------------

function diffFetcherFor(kind: ArtifactKind) {
  if (kind === "requirement") {
    return (id: string, from: number, to: number) =>
      requirementsApi.diff(id, from, to);
  }
  if (kind === "architecture") {
    return (id: string, from: number, to: number) =>
      architectureApi.diff(id, from, to);
  }
  throw new Error(`Unsupported diff kind: ${kind}`);
}

function versionsFetcherFor(kind: ArtifactKind) {
  if (kind === "requirement") {
    return (id: string) => requirementsApi.versions(id);
  }
  if (kind === "architecture") {
    return (id: string) => architectureApi.versions(id);
  }
  throw new Error(`Unsupported versions kind: ${kind}`);
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
 * Maps the 10-value ArtifactKind to the 2-value DiffEntityType that
 * `ArtifactDiff` accepts. Returns null when the kind is not yet
 * supported — the panel renders the empty state in that case.
 */
function mapKindToDiffEntityType(kind: ArtifactKind): DiffEntityType | null {
  if (!DIFF_SUPPORTED_KINDS.has(kind)) return null;
  if (kind === "requirement") return "requirement";
  if (kind === "architecture") return "architecture";
  return null;
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
