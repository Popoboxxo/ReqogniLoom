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
}

// ---------------------------------------------------------------------------
// Status badge styles
// ---------------------------------------------------------------------------

const STATUS_STYLES: Record<DiffFieldStatus, React.CSSProperties> = {
  added: {
    background: "#c6f6d5",
    color: "#22543d",
    padding: "2px 8px",
    borderRadius: "4px",
    fontSize: "12px",
    fontWeight: 600,
  },
  removed: {
    background: "#fed7d7",
    color: "#9b2c2c",
    padding: "2px 8px",
    borderRadius: "4px",
    fontSize: "12px",
    fontWeight: 600,
  },
  modified: {
    background: "#fefcbf",
    color: "#744210",
    padding: "2px 8px",
    borderRadius: "4px",
    fontSize: "12px",
    fontWeight: 600,
  },
  unchanged: {
    background: "#e2e8f0",
    color: "#4a5568",
    padding: "2px 8px",
    borderRadius: "4px",
    fontSize: "12px",
    fontWeight: 600,
  },
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
      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: "8px",
          marginBottom: showLines ? "8px" : "0",
        }}
      >
        <strong style={{ fontSize: "14px", minWidth: "120px" }}>{field.name}</strong>
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
}: ArtifactDiffProps): JSX.Element {
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
        const from = below.length > 0 ? below[below.length - 1].version : sorted[0].version;
        setFromVersion(from);
        setToVersion(to);
      })
      .catch((err) => {
        if (!cancelled) setError(extractErrorMessage(err));
      });
    return () => { cancelled = true; };
  }, [entityId, versionsFetcher, currentVersion]);

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
      {/* Header */}
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "16px",
        }}
      >
        <h3 style={{ margin: 0, fontSize: "16px" }}>
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
          gap: "16px",
          alignItems: "center",
          marginBottom: "16px",
          padding: "8px",
          background: "var(--color-surface)",
          borderRadius: "4px",
        }}
      >
        <label style={{ fontSize: "13px", fontWeight: 500 }}>
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

        <span style={{ color: "var(--color-text-muted)" }}>→</span>

        <label style={{ fontSize: "13px", fontWeight: 500 }}>
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

      {/* Loading / Error */}
      {loading && (
        <div data-testid="diff-loading" style={{ padding: "16px", textAlign: "center" }}>
          Loading diff...
        </div>
      )}

      {error && (
        <div
          data-testid="diff-error"
          style={{
            padding: "12px",
            background: "#fed7d7",
            color: "#9b2c2c",
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
            background: "#bee3f8",
            color: "#2c5282",
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
