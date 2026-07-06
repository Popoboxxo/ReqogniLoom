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
 * Today: rich field-level rendering is implemented for `requirement` and
 * `architecture` only (the two kinds the backend exposes a `/diff/`
 * endpoint for — see `docs/UI_STANDARDS.md` §4.5 and §11 Backend gaps
 * column). The 8 remaining kinds (`icd`, `diagram`, `adr`, `risk`,
 * `issue`, `glossary`, `stakeholderNeed`, `testCase`) fall through to a
 * generic "no field-level renderer for this kind" view that shows a
 * `from: X, to: Y` summary plus the raw `ArtifactDiffResult` JSON in a
 * `<details>` block. DiffPanel already short-circuits to an empty state
 * for the unsupported kinds (UI standards §4.5), so this fallback is a
 * safety net, not the primary path.
 *
 * Interfaces:
 *   IF-RF-INT-001  ← RequirementEditor / ArchitectureEditor opens this view
 *   IF-RF-EXT-OUT-001 → GET /api/v1/requirements/{id}/diff/
 *                        GET /api/v1/requirements/{id}/versions/
 */

import { useState, useEffect, useCallback } from "react";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  DiffField,
  DiffFieldStatus,
  UUID,
} from "../../types";
import type { ArtifactKind } from "../shared/ArtifactInspector/types";

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

/** The two kinds the backend currently exposes a `/diff/` endpoint for. */
const RICH_DIFF_KINDS: ReadonlySet<ArtifactKind> = new Set([
  "requirement",
  "architecture",
]);

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
  const [fromVersion, setFromVersion] = useState(0);
  const [toVersion, setToVersion] = useState(currentVersion);
  const [diffResult, setDiffResult] = useState<ArtifactDiffResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load available versions
  useEffect(() => {
    let cancelled = false;
    versionsFetcher(entityId)
      .then((v) => {
        if (!cancelled) setVersions(v);
      })
      .catch((err) => {
        if (!cancelled) setError(String(err));
      });
    return () => { cancelled = true; };
  }, [entityId, versionsFetcher]);

  // Fetch diff when versions change
  const fetchDiff = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await diffFetcher(entityId, fromVersion, toVersion);
      setDiffResult(result);
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, [entityId, fromVersion, toVersion, diffFetcher]);

  useEffect(() => {
    fetchDiff();
  }, [fetchDiff]);

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
            value={fromVersion}
            onChange={(e) => setFromVersion(Number(e.target.value))}
            style={{ ...selectStyle, marginLeft: "8px" }}
          >
            {versions.map((v) => (
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
            value={toVersion}
            onChange={(e) => setToVersion(Number(e.target.value))}
            style={{ ...selectStyle, marginLeft: "8px" }}
          >
            {versions.map((v) => (
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

      {/* Fallback — generic summary for the 8 kinds without a field-level
          renderer. The DiffPanel already short-circuits to an empty state
          for these (UI standards §4.5), so this branch is a safety net
          for the day a backend endpoint is wired for one of them. */}
      {diffResult && !loading && !RICH_DIFF_KINDS.has(entityType) && (
        <div data-testid="diff-generic-fallback" data-kind={entityType}>
          {/* TODO(backend): wire real diff for {entityType}. */}
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
