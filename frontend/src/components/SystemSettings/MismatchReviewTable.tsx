/**
 * REQ-187 — MismatchReviewTable (SCR-206 Card 3).
 *
 * Read-only, paginated view of shadow-phase legacy-vs-new access-decision
 * mismatches, feeding the "regression-risk visibility" that gates the
 * enforcement flip. Every row is by definition a mismatch, so the whole table
 * carries a uniform soft-warning tint plus a "⚠" glyph (never color-only).
 * No row actions — the underlying log is append-only.
 */

import { useCallback, useEffect, useState } from "react";
import {
  permissionDefaultsApi,
  CAPABILITY_KEYS,
  type CapabilityKey,
  type MismatchQuery,
  type MismatchSubjectType,
  type PermissionDecisionMismatch,
} from "../../api/permission-defaults";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

const PAGE_SIZE = 25;

const cardStyle: React.CSSProperties = {
  background: "var(--color-surface)",
  border: "1px solid var(--color-border)",
  borderRadius: "var(--radius-lg)",
  padding: "var(--space-5)",
  marginBottom: "var(--space-5)",
  boxShadow: "var(--shadow-card)",
};

const headingStyle: React.CSSProperties = {
  fontSize: "var(--font-size-lg)",
  fontWeight: 600,
  color: "var(--color-text)",
  margin: "0 0 var(--space-4) 0",
};

const selectStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  borderRadius: "var(--radius-md)",
  border: "1px solid var(--color-border)",
  background: "var(--color-surface-raised)",
  color: "var(--color-text)",
  fontSize: "var(--font-size-sm)",
};

const thStyle: React.CSSProperties = {
  textAlign: "left",
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-xs)",
  fontWeight: 600,
  color: "var(--color-text-muted)",
  textTransform: "uppercase",
  letterSpacing: "0.05em",
  borderBottom: "1px solid var(--color-border)",
};

const tdStyle: React.CSSProperties = {
  padding: "var(--space-2) var(--space-3)",
  fontSize: "var(--font-size-sm)",
  color: "var(--color-text)",
  borderBottom: "1px solid var(--color-border)",
  verticalAlign: "middle",
};

const SUBJECT_TYPES: MismatchSubjectType[] = ["user", "apikey", "agent"];

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString();
}

function decision(value: boolean): string {
  return value ? "✓" : "✗";
}

export function MismatchReviewTable(): JSX.Element {
  const [items, setItems] = useState<PermissionDecisionMismatch[]>([]);
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [capability, setCapability] = useState<CapabilityKey | "">("");
  const [subjectType, setSubjectType] = useState<MismatchSubjectType | "">("");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");

  const load = useCallback(
    async (targetPage: number): Promise<void> => {
      setLoading(true);
      setError(null);
      const query: MismatchQuery = {
        page: targetPage,
        page_size: PAGE_SIZE,
      };
      if (capability) query.capability = capability;
      if (subjectType) query.subject_type = subjectType;
      if (since) query.since = new Date(since).toISOString();
      if (until) query.until = new Date(until).toISOString();
      try {
        const resp = await permissionDefaultsApi.listMismatches(query);
        setItems(resp.results);
        setCount(resp.count);
        setPage(targetPage);
      } catch (err) {
        setError(extractErrorMessage(err));
        setItems([]);
      } finally {
        setLoading(false);
      }
    },
    [capability, subjectType, since, until]
  );

  // Reload from page 1 whenever a filter changes.
  useEffect(() => {
    void load(1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [capability, subjectType, since, until]);

  const totalPages = Math.max(1, Math.ceil(count / PAGE_SIZE));

  return (
    <section style={cardStyle} id="mismatch-review-card" data-testid="mismatch-review-section">
      <h3 style={headingStyle}>Mismatch Review</h3>

      {/* Filters */}
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          gap: "var(--space-2)",
          marginBottom: "var(--space-4)",
        }}
      >
        <select
          data-testid="mismatch-filter-capability"
          value={capability}
          onChange={(e) => setCapability(e.target.value as CapabilityKey | "")}
          style={selectStyle}
          aria-label="Filter by capability"
        >
          <option value="">All capabilities</option>
          {CAPABILITY_KEYS.map((cap) => (
            <option key={cap} value={cap}>
              {cap}
            </option>
          ))}
        </select>
        <select
          data-testid="mismatch-filter-subject-type"
          value={subjectType}
          onChange={(e) =>
            setSubjectType(e.target.value as MismatchSubjectType | "")
          }
          style={selectStyle}
          aria-label="Filter by subject type"
        >
          <option value="">All subjects</option>
          {SUBJECT_TYPES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <input
          type="date"
          data-testid="mismatch-filter-since"
          value={since}
          onChange={(e) => setSince(e.target.value)}
          style={selectStyle}
          aria-label="Since"
        />
        <input
          type="date"
          data-testid="mismatch-filter-until"
          value={until}
          onChange={(e) => setUntil(e.target.value)}
          style={selectStyle}
          aria-label="Until"
        />
      </div>

      {error && (
        <p role="alert" data-testid="mismatch-error" style={{ color: "var(--color-danger)" }}>
          {error}
        </p>
      )}

      {loading ? (
        <p style={{ color: "var(--color-text-muted)" }}>…</p>
      ) : items.length === 0 ? (
        <p data-testid="mismatch-empty" style={{ color: "var(--color-text-muted)", fontSize: "var(--font-size-sm)" }}>
          No mismatches recorded in this window — legacy and new decisions agree.
        </p>
      ) : (
        <div style={{ overflowX: "auto" }}>
          <table
            data-testid="mismatch-table"
            style={{ width: "100%", borderCollapse: "collapse" }}
          >
            <thead>
              <tr>
                <th style={thStyle}>Time</th>
                <th style={thStyle}>Subject</th>
                <th style={thStyle}>Capability</th>
                <th style={thStyle}>Workspace</th>
                <th style={thStyle}>Artifact</th>
                <th style={thStyle}>Legacy</th>
                <th style={thStyle}>New</th>
              </tr>
            </thead>
            <tbody>
              {items.map((m) => (
                <tr
                  key={m.id}
                  data-testid={`mismatch-row-${m.id}`}
                  style={{ background: "rgba(245,158,11,0.08)" }}
                >
                  <td style={tdStyle}>
                    <span aria-hidden="true" style={{ marginRight: "4px" }}>
                      ⚠
                    </span>
                    {fmtTime(m.created_at)}
                  </td>
                  <td style={{ ...tdStyle, fontFamily: "monospace" }} title={m.subject_identifier}>
                    {m.subject_type ? `${m.subject_type}: ` : ""}
                    {m.subject_identifier.length > 24
                      ? `${m.subject_identifier.slice(0, 24)}…`
                      : m.subject_identifier}
                  </td>
                  <td style={tdStyle}>{m.capability}</td>
                  <td style={tdStyle}>
                    {m.workspace_id ? `${m.workspace_id.slice(0, 8)}…` : "tenant-wide"}
                  </td>
                  <td style={{ ...tdStyle, fontFamily: "monospace" }}>
                    {m.artifact_id ? `${m.artifact_id.slice(0, 8)}…` : "—"}
                  </td>
                  <td style={tdStyle}>{decision(m.legacy_decision)}</td>
                  <td style={tdStyle}>{decision(m.new_decision)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {count > PAGE_SIZE && (
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "var(--space-3)",
            marginTop: "var(--space-3)",
          }}
        >
          <button
            type="button"
            data-testid="mismatch-prev"
            disabled={page <= 1 || loading}
            onClick={() => void load(page - 1)}
            style={{ ...selectStyle, cursor: page <= 1 ? "not-allowed" : "pointer" }}
          >
            Previous
          </button>
          <span style={{ fontSize: "var(--font-size-sm)", color: "var(--color-text-muted)" }}>
            Page {page} / {totalPages}
          </span>
          <button
            type="button"
            data-testid="mismatch-next"
            disabled={page >= totalPages || loading}
            onClick={() => void load(page + 1)}
            style={{ ...selectStyle, cursor: page >= totalPages ? "not-allowed" : "pointer" }}
          >
            Next
          </button>
        </div>
      )}
    </section>
  );
}
