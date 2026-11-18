/**
 * Audit dashboard — pure selectors and display helpers (S3.2 WP-5 split by
 * cohesion).
 *
 * Extracted verbatim from `audit-dashboard.tsx`: the scope/type option lists,
 * the label/expiry/error-code helpers and the four derived views over a run
 * (filtered rows, per-rule counters, shrink-on-resolve counts, rule groups).
 * None of these touches the DOM, an API or React state, so they are directly
 * unit-testable; the component keeps the hooks and all JSX.
 *
 * No behaviour change: the function bodies are the ones that used to live in
 * `audit-dashboard.tsx`, including the ordering of the filters and the
 * zero-clamping of the count corrections.
 */

import { ForbiddenError } from "../../api/errors";
import type {
  AuditCounts,
  AuditFinding,
  AuditScopeKind,
} from "../../api/audit";
import type { ApiError, Artifact } from "../../types";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const SCOPES: AuditScopeKind[] = ["project", "document", "global"];

/**
 * #1262: artifact types offered by the server-side `artifact_type` filter. The
 * backend resolves the type to the workspace's Artifact ids, so only types that
 * can carry SE-Auditor findings are listed.
 */
export const ARTIFACT_TYPE_OPTIONS = [
  "Requirement",
  "ArchitectureElement",
  "Icd",
  "TestCase",
  "StakeholderNeed",
  "Goal",
] as const;

/** All-zero counts — the value before the first report arrives. */
export const EMPTY_COUNTS: AuditCounts = {
  total: 0,
  blockers: 0,
  warnings: 0,
  suppressed: 0,
  suppressed_blockers: 0,
};

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------

/** Defensive label for an /artifacts/ row — the payload exposes no title/name
 * field today (same caveat as BaselinesView's document-scope picker), so we
 * read them optimistically and fall back to a truncated id. */
export function artifactLabel(a: Artifact): string {
  const named = a as Artifact & { title?: string; name?: string };
  const label = named.title ?? named.name ?? `${a.id.slice(0, 8)}…`;
  return `${a.artifact_type} — ${label}`;
}

/**
 * #569: the stable `error.code` of a thrown API error, if any.
 *
 * Two different shapes reach a caller: the non-2xx path of `apiFetch` throws
 * the parsed `{error: {code, message, details}}` body (so the code lives on
 * the object rather than on an `Error` subclass), but `apiFetch` intercepts
 * **403 before** that generic path and throws `ForbiddenError` — a plain
 * `Error` subclass that carries **no** `.error` property (client.ts:287-301).
 * Reading only `apiErr.error.code` therefore made the `PERMISSION_DENIED`
 * branch dead on REST: a real 403 (no Admin/Approver role, or an AUTHOR-tier
 * API key) resolved to `null` and the dedicated forbidden message was
 * unreachable. `ForbiddenError` is mapped back onto its stable code here so
 * both transports land on the same branch.
 *
 * Callers must branch on this code — not on the HTTP status, and never on 422
 * (which the waive paths deliberately never emit; see spec E18).
 */
export function waiverErrorCode(err: unknown): string | null {
  if (err instanceof ForbiddenError) return "PERMISSION_DENIED";
  const apiErr = err as Partial<ApiError> | null;
  return apiErr?.error?.code ?? null;
}

/** Render an ISO-8601 expiry for display; invalid input degrades to the raw string. */
export function formatExpiry(iso: string): string {
  const parsed = new Date(iso);
  return Number.isNaN(parsed.getTime()) ? iso : parsed.toLocaleDateString();
}

/** Counts never go below zero, even if a local action outruns the snapshot. */
export function decrement(value: number, by: number): number {
  return Math.max(0, value - by);
}

// ---------------------------------------------------------------------------
// Derived views over one run
// ---------------------------------------------------------------------------

/**
 * Client-side narrowing of the mounted rows. Kept as a pure function so the
 * order of the filters (severity → rule → suppressed) and their independence
 * from the badges is testable in isolation.
 */
export function filterFindings(
  findings: AuditFinding[],
  severityFilter: "all" | "blocker" | "warning",
  ruleFilter: string,
  showSuppressed: boolean,
): AuditFinding[] {
  let list =
    severityFilter === "all"
      ? findings
      : findings.filter((f) => f.severity === severityFilter);
  // #1262: rule filter (client-side) — the rule-id select shows per-rule
  // counters derived from the currently loaded findings.
  if (ruleFilter !== "all") list = list.filter((f) => f.rule_id === ruleFilter);
  // #569: the "show suppressed" filter (default on) hides suppressed rows
  // client-side only — the report keeps them marked, never silently.
  if (!showSuppressed) list = list.filter((f) => !f.suppressed);
  return list;
}

/** #1262: per-rule counters for the rule filter, ordered by rule id. */
export function buildRuleOptions(findings: AuditFinding[]): [string, number][] {
  const counts = new Map<string, number>();
  for (const f of findings) counts.set(f.rule_id, (counts.get(f.rule_id) ?? 0) + 1);
  return Array.from(counts.entries()).sort(([a], [b]) => a.localeCompare(b));
}

/**
 * The badges read the report's `counts`, which is the ground truth over the
 * FULL run. They are never derived from `findings.length`: that list holds
 * only the mounted windows. Client-side filters do not change these numbers
 * either — they describe the run, not the view.
 *
 * Shrink-on-resolve: the server counts are a snapshot taken during the last
 * run, so an Adopt or a Waive performed afterwards cannot change them. The
 * findings acted on since that snapshot are applied on top of it — a bounded,
 * explicit correction, not a recount of the DOM.
 */
export function computeCounts(
  reportCounts: AuditCounts | null,
  adoptedSinceRun: AuditFinding[],
  waivedSinceRun: AuditFinding[],
): AuditCounts {
  if (!reportCounts) return EMPTY_COUNTS;
  const adoptedBlockers = adoptedSinceRun.filter((f) => f.severity === "blocker").length;
  const adoptedSuppressed = adoptedSinceRun.filter((f) => f.suppressed).length;
  const adoptedSuppressedBlockers = adoptedSinceRun.filter(
    (f) => f.suppressed && f.severity === "blocker"
  ).length;
  const waivedBlockers = waivedSinceRun.filter((f) => f.severity === "blocker").length;
  return {
    total: decrement(reportCounts.total, adoptedSinceRun.length),
    // A waived blocker is excluded from the effective count too (#1150).
    blockers: decrement(reportCounts.blockers, adoptedBlockers + waivedBlockers),
    // Every adopted finding removed exactly one row from the run, so the
    // warnings are the adopted findings that were not blockers.
    warnings: decrement(reportCounts.warnings, adoptedSinceRun.length - adoptedBlockers),
    suppressed: Math.max(
      0,
      reportCounts.suppressed + waivedSinceRun.length - adoptedSuppressed
    ),
    suppressed_blockers: Math.max(
      0,
      reportCounts.suppressed_blockers + waivedBlockers - adoptedSuppressedBlockers
    ),
  };
}

/** Group the visible rows by rule id, with a stable rule-id ordering. */
export function groupFindingsByRule(
  findings: AuditFinding[],
): [string, AuditFinding[]][] {
  const groups = new Map<string, AuditFinding[]>();
  for (const f of findings) {
    const list = groups.get(f.rule_id) ?? [];
    list.push(f);
    groups.set(f.rule_id, list);
  }
  return Array.from(groups.entries()).sort(([a], [b]) => a.localeCompare(b));
}
