/**
 * ARCH-L1-001 ReactFrontend — audit dashboard filters (#598 S2).
 *
 * Extracted from `audit-dashboard.tsx`: the severity filter, the client-side
 * rule filter, the server-side artifact-type filter and the "show suppressed"
 * switch. They are independent of the run state and the waive/adopt workflows.
 *
 * Note the split: `artifactTypeFilter` is sent to the server and therefore part
 * of the run context; severity/rule/suppressed only narrow the mounted rows.
 * The badges never derive from these filters — they describe the run.
 */

import { useCallback, useState } from "react";

export type AuditSeverityFilter = "all" | "blocker" | "warning";

export interface UseAuditFiltersResult {
  severityFilter: AuditSeverityFilter;
  setSeverityFilter: (value: AuditSeverityFilter) => void;
  ruleFilter: string;
  setRuleFilter: (value: string) => void;
  artifactTypeFilter: string;
  setArtifactTypeFilter: (value: string) => void;
  showSuppressed: boolean;
  setShowSuppressed: (value: boolean) => void;
  /** Reset the client-side filters (the server-side type filter is kept). */
  resetClientFilters: () => void;
}

export function useAuditFilters(): UseAuditFiltersResult {
  const [severityFilter, setSeverityFilter] = useState<AuditSeverityFilter>("all");
  const [ruleFilter, setRuleFilter] = useState("all");
  const [artifactTypeFilter, setArtifactTypeFilter] = useState("all");
  // #569: "show suppressed" is on by default — nothing is hidden by default
  // (O3). The report itself always keeps suppressed findings.
  const [showSuppressed, setShowSuppressed] = useState(true);

  const resetClientFilters = useCallback((): void => {
    setSeverityFilter("all");
    setRuleFilter("all");
    setShowSuppressed(true);
  }, []);

  return {
    severityFilter,
    setSeverityFilter,
    ruleFilter,
    setRuleFilter,
    artifactTypeFilter,
    setArtifactTypeFilter,
    showSuppressed,
    setShowSuppressed,
    resetClientFilters,
  };
}
