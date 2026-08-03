/**
 * Human-readable labels for TestRun / TestRunResult raw status strings.
 *
 * req_id: REQ-050 (Container/Presenter decomposition of TestRunsList)
 *
 * Test-run execution states (`in_progress`, `passed`, `failed`, ...) are a
 * different semantic domain from artifact workflow status (`draft`,
 * `approved`, ...), but both render through the single
 * `shared/StatusBadge` — see Task 1.6 (UI-Konzept-Vollrollout). This module
 * only supplies the domain-specific label text; the badge markup and color
 * tokens stay in `shared/StatusBadge.tsx` / `utils/statusBadge.ts`.
 */

/**
 * Keys are the raw lowercase API values (see persistence/models.py
 * TestRun.status choices and step-result statuses).
 */
const TEST_RUN_STATUS_LABELS: Record<string, string> = {
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

/** Human-readable label for a raw test-run/result status string. */
export function getTestRunStatusLabel(status: string): string {
  return TEST_RUN_STATUS_LABELS[status] ?? humanizeStatus(status);
}
