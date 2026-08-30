/**
 * ARCH-L1-001 ReactFrontend — ArtifactDiff (COMP-RF-014).
 *
 * leaf_id: COMP-RF-014
 * req_id:  REQ-L2-RF-014 (visual diff rendering),
 *          REQ-L1-040 (visual artifact diff),
 *          REQ-L1-095 (Adoption on 10 artifact types)
 *
 * Renders a field-level diff between two artifact versions.
 * - Status badges: green=added, red=removed, yellow=modified, gray=unchanged
 * - Text fields show unified diff with line-level highlighting
 * - Version selector dropdowns for from/to
 * - Close button
 *
 * As of REQ-142, rich field-level rendering is implemented for all 10
 * artifact kinds — every kind now exposes a `/diff/` endpoint on the
 * backend (diagram and glossary were the last two, wired against their
 * immutable DiagramVersion / GlossaryTermVersion history tables). The
 * generic "no field-level renderer for this kind" fallback below is kept
 * as a defensive safety net for any future kind added ahead of its
 * backend endpoint, not the primary path.
 *
 * Interfaces:
 *   IF-RF-INT-001  ← RequirementEditor / ArchitectureEditor opens this view
 *   IF-RF-EXT-OUT-001 → GET /api/v1/requirements/{id}/diff/
 *                        GET /api/v1/requirements/{id}/versions/
 */

import { useState, useEffect, useCallback, useRef } from "react";
import { useTranslation } from "react-i18next";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  DiffField,
  DiffFieldStatus,
  UUID,
} from "../../types";
import type { ArtifactKind } from "../shared/ArtifactInspector/types";
import { DIFF_SUPPORTED_KINDS } from "../shared/ArtifactInspector/types";
import { extractErrorMessage } from "../../api/client";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/**
 * The set of artifact kinds accepted by this component.
 *
 * Aliased to the single source of truth in
 * `frontend/src/components/shared/ArtifactInspector/types.ts` so the
 * public `DiffEntityType` name keeps working for `DiffPanel` and other
 * callers (UI standards §4.5 / §11 open question #3).
 */
export type DiffEntityType = ArtifactKind;

/**
 * Kinds the backend exposes a `/diff/` endpoint for. All of them return
 * the same field-level `ArtifactDiffResult`, so they share the rich
 * renderer. Mirrors DIFF_SUPPORTED_KINDS (single source of truth).
 */
const RICH_DIFF_KINDS: ReadonlySet<ArtifactKind> = DIFF_SUPPORTED_KINDS;

/** Header label per kind. Kept here so the title text is co-located. */
const ENTITY_LABELS: Record<ArtifactKind, string> = {
  requirement: "Requirement",
  architecture: "Architecture Element",
  icd: "ICD",
  diagram: "Diagram",
  adr: "ADR",
  risk: "Risk",
  issue: "Issue",
  glossary: "Glossary",
  stakeholderNeed: "Stakeholder Need",
  testCase: "Test Case",
  goal: "Goal",
  mainGoal: "Main Goal",
};

/**
 * The comparison this component has actually resolved and is displaying.
 *
 * M-04: hosts used to describe the comparison from their own state, which is
 * only a *request* — the resolved range is decided here, from the fetched
 * version list. Reporting it back is what lets a host label the panel with
 * the range on screen instead of the one it asked for.
 */
export interface ArtifactDiffRange {
  from: number;
  to: number;
  /**
   * True when `from` is the synthetic, empty "creation baseline" (version 0)
   * and no content-bearing version sits between it and `to` — i.e. `to` has
   * no stored predecessor to be compared against, so what is on screen is the
   * artifact's initial state rather than a change set.
   */
  isInitialState: boolean;
}

/**
 * Version number of the synthetic "creation baseline" the backend prepends to
 * every version list. It holds no field values, which is why a comparison
 * starting at it reports every field as "added" (see `ArtifactDiffService`
 * and issue #213).
 */
const CREATION_BASELINE_VERSION = 0;

interface ArtifactDiffProps {
  entityId: UUID;
  entityType: DiffEntityType;
  currentVersion: number;
  diffFetcher: (
    id: UUID,
    fromVersion: number,
    toVersion: number
  ) => Promise<ArtifactDiffResult>;
  versionsFetcher: (id: UUID) => Promise<ArtifactVersion[]>;
  onClose: () => void;
  /**
   * Preferred left-hand side of the comparison, e.g. the version a host's
   * "Compare to current" action picked. Honoured only when it names a version
   * that exists and sits strictly below the resolved right-hand side;
   * otherwise the automatic seeding below applies. Before M-04 the host's
   * choice had no way in at all and was silently discarded.
   */
  initialFromVersion?: number;
  /** Notified whenever the resolved comparison changes (M-04). */
  onRangeChange?: (range: ArtifactDiffRange | null) => void;
}

// ---------------------------------------------------------------------------
// Status badge styles
// ---------------------------------------------------------------------------

/**
 * Shared badge geometry. H-03: `flex: 0 0 auto` + `nowrap` keep the badge at
 * its natural size when the surrounding row wraps in the narrow
 * ArtifactInspector column — without it the badge itself shrank and its label
 * broke mid-word.
 */
const STATUS_BADGE_BASE: React.CSSProperties = {
  padding: "2px 8px",
  borderRadius: "4px",
  fontSize: "12px",
  fontWeight: 600,
  whiteSpace: "nowrap",
  flex: "0 0 auto",
};

const STATUS_STYLES: Record<DiffFieldStatus, React.CSSProperties> = {
  added: {
    ...STATUS_BADGE_BASE,
    background: "var(--color-diff-added-bg)",
    color: "var(--color-diff-added-text)",
  },
  removed: {
    ...STATUS_BADGE_BASE,
    background: "var(--color-diff-removed-bg)",
    color: "var(--color-diff-removed-text)",
  },
  modified: {
    ...STATUS_BADGE_BASE,
    background: "var(--color-diff-modified-bg)",
    color: "var(--color-diff-modified-text)",
  },
  unchanged: {
    ...STATUS_BADGE_BASE,
    background: "var(--color-diff-unchanged-bg)",
    color: "var(--color-diff-unchanged-text)",
  },
};

/**
 * M-04 — framing for a version that has no stored predecessor. Reuses the
 * existing "note" palette (the limitation banner below) so the two read as
 * the same class of message rather than as an error.
 */
const initialStateNoticeStyle: React.CSSProperties = {
  padding: "8px 12px",
  background: "var(--color-diff-note-bg)",
  color: "var(--color-diff-note-text)",
  borderRadius: "4px",
  fontSize: "12px",
  lineHeight: 1.5,
  marginBottom: "12px",
};

const STATUS_LABELS: Record<DiffFieldStatus, string> = {
  added: "Added",
  removed: "Removed",
  modified: "Modified",
  unchanged: "Unchanged",
};

// ---------------------------------------------------------------------------
// Diff line renderer
// ---------------------------------------------------------------------------

function DiffLines({ lines }: { lines: string[] }): JSX.Element {
  return (
    <pre
      data-testid="diff-lines"
      style={{
        background: "var(--color-surface)",
        border: "1px solid var(--color-border)",
        borderRadius: "4px",
        padding: "8px",
        marginTop: "4px",
        fontSize: "12px",
        fontFamily: "monospace",
        overflowX: "auto",
        whiteSpace: "pre-wrap",
        lineHeight: "1.6",
      }}
    >
      {lines.map((line, i) => {
        let color = "var(--color-text-muted)";
        if (line.startsWith("+")) color = "var(--color-success)";
        else if (line.startsWith("-")) color = "var(--color-danger)";
        else if (line.startsWith("@@")) color = "var(--color-primary)";

        return (
          <div key={i} style={{ color }}>
            {line}
          </div>
        );
      })}
    </pre>
  );
}

// ---------------------------------------------------------------------------
// Field diff row
// ---------------------------------------------------------------------------

function FieldDiffRow({ field }: { field: DiffField }): JSX.Element {
  const showLines = field.status === "modified" && field.lines && field.lines.length > 0;

  return (
    <div
      data-testid={`diff-field-${field.name}`}
      style={{
        borderBottom: "1px solid var(--color-border)",
        padding: "12px 0",
      }}
    >
      {/* H-03: the field name reserved a fixed 120px and the row never
          wrapped, so inside the narrow ArtifactInspector column the status
          badge was pushed past the right edge and rendered clipped ("Add…").
          The name now shrinks and the badge wraps below it instead. */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "8px",
          rowGap: "4px",
          marginBottom: showLines ? "8px" : "0",
        }}
      >
        <strong style={{ fontSize: "14px", flex: "1 1 auto", minWidth: 0, overflowWrap: "anywhere" }}>
          {field.name}
        </strong>
        <span style={STATUS_STYLES[field.status]}>
          {STATUS_LABELS[field.status]}
        </span>
      </div>

      {field.status === "added" && (
        <div style={{ color: "var(--color-success)", fontSize: "13px" }}>
          {field.to}
        </div>
      )}

      {field.status === "removed" && (
        <div style={{ color: "var(--color-danger)", fontSize: "13px", textDecoration: "line-through" }}>
          {field.from}
        </div>
      )}

      {field.status === "modified" && !showLines && (
        <div style={{ fontSize: "13px" }}>
          <div style={{ color: "var(--color-danger)", textDecoration: "line-through" }}>
            {field.from}
          </div>
          <div style={{ color: "var(--color-success)" }}>
            {field.to}
          </div>
        </div>
      )}

      {showLines && <DiffLines lines={field.lines!} />}

      {field.status === "unchanged" && (
        <div style={{ color: "var(--color-text-muted)", fontSize: "13px" }}>
          {field.from}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export function ArtifactDiff({
  entityId,
  entityType,
  currentVersion,
  diffFetcher,
  versionsFetcher,
  onClose,
  initialFromVersion,
  onRangeChange,
}: ArtifactDiffProps): JSX.Element {
  const { t } = useTranslation();
  const [versions, setVersions] = useState<ArtifactVersion[]>([]);
  // `null` until the version list has loaded — prevents a premature diff
  // fetch with a meaningless from=0/to=currentVersion pair before the user
  // has real options to select from.
  const [fromVersion, setFromVersion] = useState<number | null>(null);
  const [toVersion, setToVersion] = useState<number | null>(null);
  const [diffResult, setDiffResult] = useState<ArtifactDiffResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Defensive hardening (see the longer note on fetchDiff below): a
  // monotonically-increasing id identifying the "latest" fetchDiff call —
  // lets an out-of-order/late response from a superseded request be ignored
  // instead of appending a spurious error banner to fresher state.
  const diffRequestIdRef = useRef(0);

  // Versions sorted ascending by version number — used for both the option
  // lists and the initial from/to selection.
  const sortedVersions = [...versions].sort((a, b) => a.version - b.version);
  const maxVersion =
    sortedVersions.length > 0 ? sortedVersions[sortedVersions.length - 1].version : null;

  // Load available versions and seed the initial from/to selection.
  useEffect(() => {
    let cancelled = false;
    versionsFetcher(entityId)
      .then((v) => {
        if (cancelled) return;
        setVersions(v);
        if (v.length === 0) return;
        const sorted = [...v].sort((a, b) => a.version - b.version);
        const last = sorted[sorted.length - 1].version;
        // Default "to" is the current version when present, else the latest.
        const to = sorted.some((x) => x.version === currentVersion)
          ? currentVersion
          : last;
        // Default "from" is the highest version strictly below "to" so the
        // initial diff is a valid forward comparison; falls back to the
        // lowest version (only meaningful when a single version exists).
        const below = sorted.filter((x) => x.version < to);
        const auto =
          below.length > 0 ? below[below.length - 1].version : sorted[0].version;
        // M-04: a host-requested left version wins, but only when it is a
        // real entry below "to". Hosts seed it from their own notion of the
        // current version, which is frequently equal to "to" (a comparison of
        // a version against itself) or a version that never existed — neither
        // may be allowed to produce an empty or backwards range.
        const requested =
          initialFromVersion !== undefined &&
          initialFromVersion < to &&
          sorted.some((x) => x.version === initialFromVersion)
            ? initialFromVersion
            : null;
        setFromVersion(requested ?? auto);
        setToVersion(to);
      })
      .catch((err) => {
        if (!cancelled) setError(extractErrorMessage(err));
      });
    return () => { cancelled = true; };
  }, [entityId, versionsFetcher, currentVersion, initialFromVersion]);

  // Fetch diff only once both endpoints are chosen (guards the premature
  // from=0 fetch and any backwards from >= to selection).
  //
  // Hardening (not a fix for a confirmed production bug — see below):
  // `currentVersion` seeds `toVersion`, and can change shortly after mount
  // (e.g. right after the artifact's first save). That re-seed can fire a
  // new diff fetch while a PREVIOUS one is still in flight. `diffResult` is
  // never cleared on error (see the `{diffResult && !loading && ...}` render
  // below), so a late, superseded rejection landing after a fresher success
  // cannot hide `diff-fields` — it can only add a spurious error banner
  // above an otherwise-correct diff. That is a real but cosmetic bug on its
  // own; it does NOT explain the originally reported ">30s timeout" symptom
  // (SYSTEMAUDIT_2026-08-18 §4, BUG-04), which needs `diffResult` to stay
  // `null` or `loading` to stay `true` indefinitely — this component has no
  // code path that does that. Live re-execution of
  // e2e/tests/artifact-diff.spec.ts against a freshly booted dev backend +
  // Vite server reproduced the exact `page.waitForResponse` 30000ms timeout
  // once (in `saveWithChangeReason`, unrelated to version selection) and
  // then passed cleanly 5/5 times afterward on warm re-runs — consistent
  // with the compose/cold-start issues fixed the same day in #614 (890bfed:
  // stale dev image, crash-loop, OOM-tuned limits), not a deterministic
  // application defect. Root cause for BUG-04 could not be confirmed as
  // application code; see the PR description for the full write-up.
  //
  // The `requestId` ref below still closes a genuine (if cosmetic) staleness
  // gap — kept as defensive hardening, mirroring the `cancelled` flag the
  // sibling `versionsFetcher` effect above already uses for the same class
  // of problem. It is bumped unconditionally at the top of every call
  // (including the early-return branch) so an in-flight request is always
  // marked superseded the moment fetchDiff runs again, even when the new
  // run turns out to have nothing to fetch.
  const fetchDiff = useCallback(async () => {
    const requestId = ++diffRequestIdRef.current;
    if (fromVersion === null || toVersion === null || fromVersion >= toVersion) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await diffFetcher(entityId, fromVersion, toVersion);
      if (requestId !== diffRequestIdRef.current) return; // superseded — ignore
      setDiffResult(result);
    } catch (err) {
      if (requestId !== diffRequestIdRef.current) return; // superseded — ignore
      setError(extractErrorMessage(err));
    } finally {
      if (requestId === diffRequestIdRef.current) setLoading(false);
    }
  }, [entityId, fromVersion, toVersion, diffFetcher]);

  useEffect(() => {
    fetchDiff();
  }, [fetchDiff]);

  // -------------------------------------------------------------------------
  // M-04 — "this version has no predecessor"
  // -------------------------------------------------------------------------
  //
  // Version 0 is the synthetic, empty creation baseline, so a comparison that
  // starts there is not a change set: every field is reported as "added"
  // simply because the left side holds nothing. That is only misleading when
  // there is genuinely nothing else to compare against — which is exactly the
  // case for the artifact's first version. When real snapshots do sit between
  // 0 and "to", the user has deliberately widened the range back to creation
  // and the added-everything reading is the correct answer to what was asked.
  const hasStoredPredecessor =
    toVersion !== null &&
    sortedVersions.some(
      (v) => v.version > CREATION_BASELINE_VERSION && v.version < toVersion,
    );
  const isInitialState =
    fromVersion === CREATION_BASELINE_VERSION &&
    toVersion !== null &&
    !hasStoredPredecessor;

  // Report the *resolved* range upward so a host labels the panel with what is
  // on screen. Before M-04 the ArtifactInspector announced its own requested
  // range, which seeded left and right to the same version and therefore
  // claimed a comparison of a version against itself ("v1 → v1") above a
  // panel that was in fact showing 0 → 1.
  useEffect(() => {
    if (!onRangeChange) return;
    if (fromVersion === null || toVersion === null) {
      onRangeChange(null);
      return;
    }
    onRangeChange({ from: fromVersion, to: toVersion, isInitialState });
  }, [onRangeChange, fromVersion, toVersion, isInitialState]);

  // "From" cannot be the latest version (nothing sits above it); "To" is
  // restricted to versions strictly greater than the current "From". With
  // only one version total, those exclusions would leave both selects with
  // zero options (empty dropdowns, e.g. every freshly created artifact) --
  // fall back to offering the sole version in both instead.
  const fromOptions =
    sortedVersions.length <= 1
      ? sortedVersions
      : sortedVersions.filter((v) => maxVersion === null || v.version < maxVersion);
  const toOptions =
    sortedVersions.length <= 1
      ? sortedVersions
      : sortedVersions.filter((v) => fromVersion === null || v.version > fromVersion);

  // Keep "To" valid when the user moves "From" forward past it.
  const handleFromChange = (next: number): void => {
    setFromVersion(next);
    if (toVersion !== null && toVersion <= next) {
      const above = sortedVersions.find((v) => v.version > next);
      if (above) setToVersion(above.version);
    }
  };

  const selectStyle: React.CSSProperties = {
    padding: "4px 8px",
    borderRadius: "4px",
    border: "1px solid var(--color-border)",
    fontSize: "13px",
    background: "var(--color-surface-raised)",
    color: "var(--color-text)",
    // H-03: a select sizes to its widest option by default and overflowed the
    // narrow inspector column, cutting off the dropdown arrow.
    maxWidth: "100%",
  };

  return (
    <div
      data-testid="artifact-diff-view"
      style={{
        background: "var(--color-surface-raised)",
        border: "1px solid var(--color-border)",
        borderRadius: "8px",
        padding: "16px",
        marginTop: "16px",
        color: "var(--color-text)",
      }}
    >
      {/* Header — H-03: wraps so the title and the Close button stop
          overlapping once the inspector column narrows. */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          flexWrap: "wrap",
          gap: "8px",
          marginBottom: "16px",
        }}
      >
        <h3 style={{ margin: 0, fontSize: "16px", overflowWrap: "anywhere" }}>
          {ENTITY_LABELS[entityType]} Diff
        </h3>
        <button
          data-testid="diff-close-btn"
          onClick={onClose}
          style={{
            background: "none",
            border: "1px solid var(--color-border)",
            borderRadius: "4px",
            padding: "4px 12px",
            cursor: "pointer",
            fontSize: "13px",
            color: "var(--color-text)",
          }}
        >
          Close
        </button>
      </div>

      {/* Version selectors */}
      <div
        data-testid="diff-version-selectors"
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "16px",
          rowGap: "8px",
          alignItems: "center",
          marginBottom: "16px",
          padding: "8px",
          background: "var(--color-surface)",
          borderRadius: "4px",
        }}
      >
        <label style={{ fontSize: "13px", fontWeight: 500, minWidth: 0 }}>
          From:
          <select
            data-testid="diff-from-version"
            value={fromVersion ?? ""}
            onChange={(e) => handleFromChange(Number(e.target.value))}
            style={{ ...selectStyle, marginLeft: "8px" }}
          >
            {fromOptions.map((v) => (
              <option key={v.version} value={v.version}>
                {v.label}
              </option>
            ))}
          </select>
        </label>

        <span style={{ color: "var(--color-text-muted)" }} aria-hidden="true">
          →
        </span>

        <label style={{ fontSize: "13px", fontWeight: 500, minWidth: 0 }}>
          To:
          <select
            data-testid="diff-to-version"
            value={toVersion ?? ""}
            onChange={(e) => setToVersion(Number(e.target.value))}
            style={{ ...selectStyle, marginLeft: "8px" }}
          >
            {toOptions.map((v) => (
              <option key={v.version} value={v.version}>
                {v.label}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* M-04: name the situation instead of letting an all-"Added" field
          list read as a change set. The values below are still the only
          content view available for a first version, so they stay — what was
          missing was the framing that they are an initial state and not a
          comparison. */}
      {isInitialState && !loading && (
        <div
          data-testid="diff-initial-state"
          style={initialStateNoticeStyle}
        >
          <strong>{t("diff.initialState.title", "Ausgangszustand")}</strong>{" "}
          {t(
            "diff.initialState.body",
            "Diese Version hat keinen gespeicherten Vorgänger. Angezeigt werden die Werte bei der Erstellung — deshalb ist jedes Feld als hinzugefügt markiert.",
          )}
        </div>
      )}

      {/* Loading / Error */}
      {loading && (
        <div data-testid="diff-loading" style={{ padding: "16px", textAlign: "center" }}>
          Loading diff...
        </div>
      )}

      {error && (
        <div
          role="alert"
          data-testid="diff-error"
          style={{
            padding: "12px",
            background: "var(--color-diff-removed-bg)",
            color: "var(--color-diff-removed-text)",
            borderRadius: "4px",
            fontSize: "13px",
          }}
        >
          Error: {error}
        </div>
      )}

      {/* Note (limitation notice) */}
      {diffResult?.note && (
        <div
          data-testid="diff-note"
          style={{
            padding: "8px 12px",
            background: "var(--color-diff-note-bg)",
            color: "var(--color-diff-note-text)",
            borderRadius: "4px",
            fontSize: "12px",
            marginBottom: "12px",
          }}
        >
          {diffResult.note}
        </div>
      )}

      {/* Field diffs — rich rendering for the two backend-supported kinds. */}
      {diffResult && !loading && RICH_DIFF_KINDS.has(entityType) && (
        <div data-testid="diff-fields">
          {diffResult.fields.map((field) => (
            <FieldDiffRow key={field.name} field={field} />
          ))}
        </div>
      )}

      {/* Fallback — generic summary for any kind without a field-level
          renderer. All 10 kinds are backend-backed as of REQ-142
          (RICH_DIFF_KINDS === DIFF_SUPPORTED_KINDS === all kinds), so
          this branch is unreachable today; kept as a defensive safety
          net for a future 11th kind added ahead of its backend
          endpoint. */}
      {diffResult && !loading && !RICH_DIFF_KINDS.has(entityType) && (
        <div data-testid="diff-generic-fallback" data-kind={entityType}>
          <p
            style={{
              fontSize: "13px",
              color: "var(--color-text-muted)",
              margin: "0 0 8px 0",
            }}
          >
            No field-level renderer for this artifact kind. Showing raw
            payload.
          </p>
          <div
            style={{
              fontSize: "13px",
              marginBottom: "8px",
            }}
          >
            from: v{diffResult.from_version}, to: v{diffResult.to_version}
          </div>
          <details>
            <summary
              style={{ cursor: "pointer", fontSize: "13px" }}
              data-testid="diff-generic-raw-toggle"
            >
              Raw JSON
            </summary>
            <pre
              data-testid="diff-generic-raw"
              style={{
                background: "var(--color-surface)",
                border: "1px solid var(--color-border)",
                borderRadius: "4px",
                padding: "8px",
                marginTop: "4px",
                fontSize: "12px",
                fontFamily: "monospace",
                overflowX: "auto",
                whiteSpace: "pre-wrap",
                lineHeight: "1.6",
              }}
            >
              {JSON.stringify(diffResult, null, 2)}
            </pre>
          </details>
        </div>
      )}
    </div>
  );
}

export default ArtifactDiff;
