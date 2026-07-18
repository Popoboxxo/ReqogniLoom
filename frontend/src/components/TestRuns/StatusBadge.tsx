/**
 * ARCH-L1-001 ReactFrontend — TestRun StatusBadge (Presenter).
 *
 * leaf_id: COMP-RF-003
 * req_id:  REQ-050 (Container/Presenter decomposition of TestRunsList)
 *
 * Pure presentational pill for a test-run status. Extracted from the former
 * monolithic TestRunsList so both the list and the detail editor share it.
 */

import { getStatusBadgeStyle } from "../../utils/statusBadge";

/**
 * Human-readable labels for the raw backend status strings (see
 * persistence/models.py TestRun.status choices and step-result statuses).
 * Keys are the raw lowercase API values.
 */
const STATUS_LABELS: Record<string, string> = {
  in_progress: "In Progress",
  passed: "Passed",
  failed: "Failed",
  partial: "Partial",
  closed: "Closed",
  not_run: "Not Run",
  blocked: "Blocked",
  skipped: "Skipped",
};

/** Fallback humanizer: `some_status` -> `Some Status`. */
function humanizeStatus(status: string): string {
  return status
    .split("_")
    .map((word) => (word ? word[0].toUpperCase() + word.slice(1) : word))
    .join(" ");
}

export function StatusBadge({ status }: { status: string }): JSX.Element {
  // Shared token-based colors; render a readable label instead of the raw
  // API string (e.g. `in_progress` -> `In Progress`).
  const label = STATUS_LABELS[status] ?? humanizeStatus(status);
  return (
    <span
      style={{
        ...getStatusBadgeStyle(status),
        display: "inline-block",
        borderRadius: "var(--radius-sm)",
        fontWeight: 600,
        letterSpacing: "0.05em",
      }}
    >
      {label}
    </span>
  );
}
