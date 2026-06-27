/**
 * ARCH-L1-001 ReactFrontend — ArtifactDiff (COMP-RF-014).
 *
 * leaf_id: COMP-RF-014
 * req_id:  REQ-L2-RF-014 (visual diff rendering),
 *          REQ-L1-040 (visual artifact diff)
 *
 * Renders a field-level diff between two artifact versions.
 * - Status badges: green=added, red=removed, yellow=modified, gray=unchanged
 * - Text fields show unified diff with line-level highlighting
 * - Version selector dropdowns for from/to
 * - Close button
 *
 * Interfaces:
 *   IF-RF-INT-001  ← RequirementEditor / ArchitectureEditor opens this view
 *   IF-RF-EXT-OUT-001 → GET /api/v1/requirements/{id}/diff/
 *                        GET /api/v1/requirements/{id}/versions/
 */

import React, { useState, useEffect, useCallback } from "react";
import type {
  ArtifactDiffResult,
  ArtifactVersion,
  DiffField,
  DiffFieldStatus,
  UUID,
} from "../../types";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export type DiffEntityType = "requirement" | "architecture";

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
        background: "#f7fafc",
        border: "1px solid #e2e8f0",
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
        let color = "#4a5568";
        if (line.startsWith("+")) color = "#22543d";
        else if (line.startsWith("-")) color = "#9b2c2c";
        else if (line.startsWith("@@")) color = "#2b6cb0";

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
        borderBottom: "1px solid #e2e8f0",
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
        <div style={{ color: "#22543d", fontSize: "13px" }}>
          {field.to}
        </div>
      )}

      {field.status === "removed" && (
        <div style={{ color: "#9b2c2c", fontSize: "13px", textDecoration: "line-through" }}>
          {field.from}
        </div>
      )}

      {field.status === "modified" && !showLines && (
        <div style={{ fontSize: "13px" }}>
          <div style={{ color: "#9b2c2c", textDecoration: "line-through" }}>
            {field.from}
          </div>
          <div style={{ color: "#22543d" }}>
            {field.to}
          </div>
        </div>
      )}

      {showLines && <DiffLines lines={field.lines!} />}

      {field.status === "unchanged" && (
        <div style={{ color: "#718096", fontSize: "13px" }}>
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
    border: "1px solid #cbd5e0",
    fontSize: "13px",
    background: "#fff",
  };

  return (
    <div
      data-testid="artifact-diff-view"
      style={{
        background: "#fff",
        border: "1px solid #e2e8f0",
        borderRadius: "8px",
        padding: "16px",
        marginTop: "16px",
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
          {entityType === "requirement" ? "Requirement" : "Architecture Element"} Diff
        </h3>
        <button
          data-testid="diff-close-btn"
          onClick={onClose}
          style={{
            background: "none",
            border: "1px solid #cbd5e0",
            borderRadius: "4px",
            padding: "4px 12px",
            cursor: "pointer",
            fontSize: "13px",
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
          background: "#f7fafc",
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

        <span style={{ color: "#718096" }}>→</span>

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

      {/* Field diffs */}
      {diffResult && !loading && (
        <div data-testid="diff-fields">
          {diffResult.fields.map((field) => (
            <FieldDiffRow key={field.name} field={field} />
          ))}
        </div>
      )}
    </div>
  );
}

export default ArtifactDiff;
