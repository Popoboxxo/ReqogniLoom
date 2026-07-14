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

export function StatusBadge({ status }: { status: string }): JSX.Element {
  // Shared token-based colors; keep the uppercase pill look specific to test runs.
  return (
    <span
      style={{
        ...getStatusBadgeStyle(status),
        display: "inline-block",
        borderRadius: "var(--radius-sm)",
        fontWeight: 600,
        textTransform: "uppercase",
        letterSpacing: "0.05em",
      }}
    >
      {status}
    </span>
  );
}
