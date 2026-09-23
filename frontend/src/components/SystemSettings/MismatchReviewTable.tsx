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
import styles from "./MismatchReviewTable.module.css";

function extractErrorMessage(err: unknown): string {
  const e = err as { error?: { message?: string }; message?: string };
  return e?.error?.message ?? e?.message ?? String(err);
}

const PAGE_SIZE = 25;

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
    <section className={styles.card} id="mismatch-review-card" data-testid="mismatch-review-section">
      <h3 className={styles.heading}>Mismatch Review</h3>

      {/* Filters */}
      <div className={styles.filters}>
        <select
          data-testid="mismatch-filter-capability"
          value={capability}
          onChange={(e) => setCapability(e.target.value as CapabilityKey | "")}
          className={styles.select}
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
          className={styles.select}
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
          className={styles.select}
          aria-label="Since"
        />
        <input
          type="date"
          data-testid="mismatch-filter-until"
          value={until}
          onChange={(e) => setUntil(e.target.value)}
          className={styles.select}
          aria-label="Until"
        />
      </div>

      {error && (
        <p role="alert" data-testid="mismatch-error" className={styles.errorText}>
          {error}
        </p>
      )}

      {loading ? (
        <p className={styles.loadingText}>…</p>
      ) : items.length === 0 ? (
        <p data-testid="mismatch-empty" className={styles.emptyText}>
          No mismatches recorded in this window — legacy and new decisions agree.
        </p>
      ) : (
        <div className={styles.tableScroll}>
          <table
            data-testid="mismatch-table"
            className={styles.table}
          >
            <thead>
              <tr>
                <th className={styles.th}>Time</th>
                <th className={styles.th}>Subject</th>
                <th className={styles.th}>Capability</th>
                <th className={styles.th}>Workspace</th>
                <th className={styles.th}>Artifact</th>
                <th className={styles.th}>Legacy</th>
                <th className={styles.th}>New</th>
              </tr>
            </thead>
            <tbody>
              {items.map((m) => (
                <tr
                  key={m.id}
                  data-testid={`mismatch-row-${m.id}`}
                  className={styles.rowWarn}
                >
                  <td className={styles.td}>
                    <span aria-hidden="true" className={styles.warnGlyph}>
                      ⚠
                    </span>
                    {fmtTime(m.created_at)}
                  </td>
                  <td className={styles.td + ' ' + styles.tdMono} title={m.subject_identifier}>
                    {m.subject_type ? `${m.subject_type}: ` : ""}
                    {m.subject_identifier.length > 24
                      ? `${m.subject_identifier.slice(0, 24)}…`
                      : m.subject_identifier}
                  </td>
                  <td className={styles.td}>{m.capability}</td>
                  <td className={styles.td}>
                    {m.workspace_id ? `${m.workspace_id.slice(0, 8)}…` : "tenant-wide"}
                  </td>
                  <td className={styles.td + ' ' + styles.tdMono}>
                    {m.artifact_id ? `${m.artifact_id.slice(0, 8)}…` : "—"}
                  </td>
                  <td className={styles.td}>{decision(m.legacy_decision)}</td>
                  <td className={styles.td}>{decision(m.new_decision)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Pagination */}
      {count > PAGE_SIZE && (
        <div className={styles.pagination}>
          <button
            type="button"
            data-testid="mismatch-prev"
            disabled={page <= 1 || loading}
            onClick={() => void load(page - 1)}
            className={styles.select + ' ' + (page <= 1 ? styles.pagerDisabled : styles.pagerEnabled)}
          >
            Previous
          </button>
          <span className={styles.pageIndicator}>
            Page {page} / {totalPages}
          </span>
          <button
            type="button"
            data-testid="mismatch-next"
            disabled={page >= totalPages || loading}
            onClick={() => void load(page + 1)}
            className={styles.select + ' ' + (page >= totalPages ? styles.pagerDisabled : styles.pagerEnabled)}
          >
            Next
          </button>
        </div>
      )}
    </section>
  );
}
