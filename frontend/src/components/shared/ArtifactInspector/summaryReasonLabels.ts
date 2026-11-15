/**
 * Shared i18n wiring for the two summary surfaces (S2 panel, S8 overview).
 *
 * The four degradation reasons are a **closed** vocabulary (spec §9/E11), so
 * the key and the English fallback live in one place: a second copy in the
 * overview would drift the moment a reason is renamed.
 *
 * leaf_id: COMP-RF-014 (ArtifactInspector)
 * req_id:  REQ-L1-089, REQ-L1-093
 */

import type { SummaryDegradedReason } from "../../../api/artifact-summary";

export const REASON_LABEL_KEYS: Record<SummaryDegradedReason, string> = {
  budget_exhausted: "summary.reason.budget_exhausted",
  provider_unavailable: "summary.reason.provider_unavailable",
  stale: "summary.reason.stale",
  disabled: "summary.reason.disabled",
};

export const REASON_FALLBACKS: Record<SummaryDegradedReason, string> = {
  budget_exhausted: "The AI budget for this period is exhausted.",
  provider_unavailable: "The AI provider is currently unavailable.",
  stale: "The stored summary is out of date.",
  disabled: "AI summaries are disabled for this workspace.",
};

/** Locale-aware rendering; an unparsable value is shown verbatim. */
export function formatGeneratedAt(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}
