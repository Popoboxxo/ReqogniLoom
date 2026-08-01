/**
 * Shared StatusBadge — single presentation of workflow/artifact status.
 *
 * req_id: REQ-L2-RF-030 (generic reusable frontend components)
 *
 * Consolidates three previously divergent implementations (issue #173):
 * - AdrForm.tsx used getStatusBadgeStyle directly (color-coded)
 * - RiskForm/IssueForm/TestCaseForm copy-pasted a neutral-gray inline style
 * - RequirementForm/NeedForm/ArchitectureForm showed no status badge at all
 *
 * Uses the same `getStatusBadgeStyle` token mapping already relied on by
 * every List component (AdrList, IssueList, NeedList, RiskList,
 * TestCaseList) so a given status renders identically in list and detail
 * views.
 */

import { getStatusBadgeStyle, type BadgeVariant } from "../../utils/statusBadge";

interface StatusBadgeProps {
  status: string;
  /** Optional override for the rendered label (defaults to the raw status). */
  label?: string;
  /**
   * UI concept ch. 8.2.1: the semantic variant should come from the workflow
   * definition so that workspace-defined states are coloured deliberately
   * instead of by string match. No backend field carries it yet — passing
   * `undefined` keeps the name-based fallback in resolveBadgeVariant().
   */
  badgeVariant?: BadgeVariant | null;
  testId?: string;
}

export function StatusBadge({
  status,
  label,
  badgeVariant,
  testId = "status-badge",
}: StatusBadgeProps): JSX.Element {
  return (
    <span data-testid={testId} style={getStatusBadgeStyle(status, badgeVariant)}>
      {label ?? status}
    </span>
  );
}
