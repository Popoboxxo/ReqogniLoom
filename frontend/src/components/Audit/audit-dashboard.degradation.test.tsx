/**
 * audit-dashboard — degradation paths (#598 S2).
 *
 * Companion to `audit-dashboard.test.tsx`, which stays unchanged as the
 * behavioural baseline of the extraction. This file pins the non-critical
 * read that has no test of its own: a failed rule-catalogue request must
 * degrade to the bare rule id instead of hiding the finding or blocking the
 * page.
 */

import { render, screen } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";

import { AuditDashboard } from "./audit-dashboard";
import { auditApi } from "../../api/audit";
import type { AuditFinding, AuditReport } from "../../api/audit";
import { artifactsApi } from "../../api/artifacts";
import { traceabilityApi } from "../../api/traceability";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

vi.mock("react-router-dom", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-1", name: "WS", preset: "extended" },
  }),
  useOptionalWorkspace: () => ({
    activeWorkspace: { id: "ws-1", name: "WS", preset: "extended" },
  }),
}));

vi.mock("../../api/audit");
vi.mock("../../api/artifacts");
vi.mock("../../api/traceability");

function finding(ruleId: string, message: string, index: number): AuditFinding {
  return {
    rule_id: ruleId,
    severity: "warning",
    message,
    artifact_ids: [],
    scope: "project",
    scope_artifact_id: null,
    index,
    finding_key: `${ruleId}\u001f${index}`,
    suppressed: false,
    suppressed_until: null,
    suppression_reason: null,
    suppression_id: null,
    remediation: {
      rule_id: ruleId,
      automatic: false,
      reason: "Manual correction.",
      finding_artifact_ids: [],
      action_kind: "manual",
    },
  };
}

function report(findings: AuditFinding[]): AuditReport {
  const counts = {
    total: findings.length,
    blockers: 0,
    warnings: findings.length,
    suppressed: 0,
    suppressed_blockers: 0,
  };
  return {
    tier: "extended",
    scope: "project",
    scope_artifact_id: null,
    counts,
    page_counts: counts,
    truncated: false,
    total_findings_available: findings.length,
    total_blockers_available: 0,
    total_effective_blockers: 0,
    total_warnings_available: findings.length,
    total_suppressed_available: 0,
    total_suppressed_blockers_available: 0,
    suppressed_filtered: 0,
    offset: 0,
    next_offset: null,
    findings,
  };
}

describe("AuditDashboard degradation (#598 S2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(auditApi.waivers).mockResolvedValue({ waivers: [] });
    vi.mocked(artifactsApi.list).mockResolvedValue({
      results: [],
      count: 0,
      next: null,
      previous: null,
    });
    vi.mocked(traceabilityApi.resolve).mockResolvedValue([]);
  });

  it("keeps the bare rule id when the rule catalogue request fails", async () => {
    vi.mocked(auditApi.rules).mockRejectedValue(new Error("catalogue offline"));
    vi.mocked(auditApi.run).mockResolvedValue(
      report([finding("TRACE-P1", "Rule catalogue is optional.", 0)])
    );

    render(<AuditDashboard />);

    expect(await screen.findByTestId("audit-group-TRACE-P1")).toBeInTheDocument();
    expect(screen.getByText("Rule catalogue is optional.")).toBeInTheDocument();
  });
});
