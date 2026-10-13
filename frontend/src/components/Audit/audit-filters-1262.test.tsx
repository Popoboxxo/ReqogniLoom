/**
 * audit-filters-1262.test.tsx
 *
 * #1262: the Auditor UI's rule filter (with per-rule counters), the
 * artifact-type filter (server-side) and the rule-id popover.
 */
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AuditDashboard } from "./audit-dashboard";
import { auditApi } from "../../api/audit";
import { artifactsApi } from "../../api/artifacts";
import type { AuditFinding, AuditReport } from "../../api/audit";

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
    activeWorkspace: { id: "ws-001", name: "Test Workspace", preset: "extended" },
  }),
}));

vi.mock("../../api/audit");
vi.mock("../../api/artifacts");
vi.mock("../../api/traceability");

function finding(index: number, ruleId: string, severity: "blocker" | "warning"): AuditFinding {
  return {
    rule_id: ruleId,
    severity,
    message: `${ruleId} finding ${index}`,
    artifact_ids: [],
    scope: "project",
    scope_artifact_id: null,
    index,
    finding_key: `${ruleId}\x1f${index}`,
    suppressed: false,
    suppressed_until: null,
    suppression_reason: null,
    suppression_id: null,
    remediation: {
      rule_id: ruleId,
      automatic: false,
      reason: "manual",
      finding_artifact_ids: [],
      action_kind: null,
      params: {},
    },
  };
}

const REPORT: AuditReport = {
  tier: "extended",
  scope: "project",
  scope_artifact_id: null,
  counts: { total: 3, blockers: 1, warnings: 2, suppressed: 0, suppressed_blockers: 0 },
  truncated: false,
  total_findings_available: 3,
  total_blockers_available: 1,
  total_effective_blockers: 1,
  total_warnings_available: 2,
  total_suppressed_available: 0,
  total_suppressed_blockers_available: 0,
  suppressed_filtered: 0,
  offset: 0,
  findings: [
    finding(0, "TRACE-P1", "blocker"),
    finding(1, "IFC-001", "warning"),
    finding(2, "IFC-001", "warning"),
  ],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(auditApi.run).mockResolvedValue(REPORT);
  vi.mocked(auditApi.waivers).mockResolvedValue({ waivers: [], counts: { active: 0, expired: 0 } });
  vi.mocked(auditApi.rules).mockResolvedValue({
    rules: [
      {
        rule_id: "TRACE-P1",
        title: "Root requirement derives from a stakeholder need",
        description: "Every root requirement must derive from a need.",
        severity: "blocker",
        standard_ref: "SysEng §2.2",
        remediation_hint: "Add the missing link.",
        active_tiers: ["standard", "extended"],
        is_scope_aware: false,
        deferred: false,
      },
      {
        rule_id: "IFC-001",
        title: "ICD not anchored in the architecture",
        description: "Every ICD must reference an architecture element.",
        severity: "warning",
        standard_ref: "SysEng (interface coverage)",
        remediation_hint: "Link the ICD to an element.",
        active_tiers: ["standard", "extended"],
        is_scope_aware: false,
        deferred: false,
      },
    ],
  });
  vi.mocked(artifactsApi.list).mockResolvedValue({
    count: 0,
    next: null,
    previous: null,
    results: [],
  });
});

describe("AuditDashboard — rule filter (#1262)", () => {
  it("shows a rule filter with per-rule counters", async () => {
    render(<AuditDashboard />);
    await screen.findByTestId("audit-finding-0");

    const select = screen.getByTestId("audit-rule-filter") as HTMLSelectElement;
    const options = Array.from(select.options).map((o) => o.textContent);
    expect(options).toContain("TRACE-P1 (1)");
    expect(options).toContain("IFC-001 (2)");
  });

  it("hides other rule groups when a rule is selected", async () => {
    render(<AuditDashboard />);
    await screen.findByTestId("audit-finding-0");

    fireEvent.change(screen.getByTestId("audit-rule-filter"), {
      target: { value: "IFC-001" },
    });

    await waitFor(() => {
      expect(screen.queryByTestId("audit-group-TRACE-P1")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("audit-group-IFC-001")).toBeInTheDocument();
  });
});

describe("AuditDashboard — rule info popover (#1262)", () => {
  it("reveals catalogue metadata when the rule id is clicked", async () => {
    render(<AuditDashboard />);
    await screen.findByTestId("audit-finding-0");

    fireEvent.click(screen.getByTestId("audit-rule-info-IFC-001"));

    const popover = await screen.findByTestId("audit-rule-popover-IFC-001");
    expect(popover.textContent).toContain("ICD not anchored in the architecture");
    expect(popover.textContent).toContain("Every ICD must reference an architecture element.");
  });
});

describe("AuditDashboard — artifact-type filter (#1262)", () => {
  it("sends the artifact type to the server when selected", async () => {
    render(<AuditDashboard />);
    await screen.findByTestId("audit-finding-0");

    fireEvent.change(screen.getByTestId("audit-artifact-type-filter"), {
      target: { value: "Icd" },
    });

    await waitFor(() => {
      expect(auditApi.run).toHaveBeenCalledWith(
        "ws-001",
        expect.objectContaining({ artifactType: "Icd" })
      );
    });
  });
});
