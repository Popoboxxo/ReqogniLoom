/**
 * audit-dashboard.test.tsx
 *
 * Unit tests for AuditDashboard (SysEng 2.0 Phase 3, "Auditor UI").
 *
 * Covers:
 *   - Findings render grouped by rule_id, with blocker/warning count badges
 *   - Adopt success: POSTs remediate, removes the finding, shows a toast
 *   - Adopt 422 (not automatically fixable): finding flips into the
 *     "Modify" state in-place instead of leaving a dead Adopt button
 *   - Scope switch (project -> document) re-runs the audit with the
 *     selected scope_artifact_id
 *   - data-testid attributes present (E2E contract)
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AuditDashboard } from "./audit-dashboard";
import { auditApi } from "../../api/audit";
import { artifactsApi } from "../../api/artifacts";
import { UnprocessableEntityError } from "../../api/errors";
import type { AuditReport } from "../../api/audit";
import type { Artifact, PaginatedResponse } from "../../types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, fallback?: string) => fallback ?? key,
  }),
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", name: "Test Workspace", preset: "extended" },
  }),
}));

vi.mock("../../api/audit");
vi.mock("../../api/artifacts");

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PROJECT_REPORT: AuditReport = {
  tier: "extended",
  scope: "project",
  scope_artifact_id: null,
  counts: { total: 2, blockers: 1, warnings: 1 },
  findings: [
    {
      rule_id: "TRACE-P1",
      severity: "blocker",
      message: "Requirement REQ-1 has no derives-from link.",
      artifact_ids: ["11111111-1111-1111-1111-111111111111"],
      scope: "project",
      scope_artifact_id: null,
      index: 0,
      remediation: {
        rule_id: "TRACE-P1",
        automatic: true,
        reason: "Exactly one plausible parent found; will create a derives-from link.",
        finding_artifact_ids: ["11111111-1111-1111-1111-111111111111"],
        action_kind: "create_trace_link",
        params: { source_id: "11111111-1111-1111-1111-111111111111", target_id: "22222222-2222-2222-2222-222222222222", link_type: "derives-from" },
      },
    },
    {
      rule_id: "TRACE-P4",
      severity: "warning",
      message: "Architecture element ARCH-2 has a dangling parent.",
      artifact_ids: ["33333333-3333-3333-3333-333333333333"],
      scope: "project",
      scope_artifact_id: null,
      index: 1,
      remediation: {
        rule_id: "TRACE-P4",
        automatic: false,
        reason: "A dangling parent cannot be invented automatically.",
        finding_artifact_ids: ["33333333-3333-3333-3333-333333333333"],
        action_kind: null,
        params: {},
      },
    },
  ],
};

const DOCUMENT_REPORT: AuditReport = {
  tier: "extended",
  scope: "document",
  scope_artifact_id: "44444444-4444-4444-4444-444444444444",
  counts: { total: 0, blockers: 0, warnings: 0 },
  findings: [],
};

function setupDefaultMocks(): void {
  vi.mocked(auditApi.run).mockImplementation((_wsId, options) => {
    if (options?.scope === "document") return Promise.resolve(DOCUMENT_REPORT);
    return Promise.resolve(PROJECT_REPORT);
  });
  const artifactsPage: PaginatedResponse<Artifact> = {
    results: [
      {
        id: "44444444-4444-4444-4444-444444444444",
        workspace_id: "ws-001",
        artifact_type: "Requirement",
        parent_id: null,
        version: 1,
        created_at: "",
        updated_at: "",
      },
    ],
    count: 1,
    next: null,
    previous: null,
  };
  vi.mocked(artifactsApi.list).mockResolvedValue(artifactsPage);
}

describe("AuditDashboard (SysEng 2.0 Phase 3)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  // ---- Rendering / grouping ----

  it("renders findings grouped by rule_id with severity badges", async () => {
    render(<AuditDashboard />);

    expect(await screen.findByTestId("audit-group-TRACE-P1")).toBeInTheDocument();
    expect(screen.getByTestId("audit-group-TRACE-P4")).toBeInTheDocument();
    expect(screen.getByTestId("audit-finding-0")).toBeInTheDocument();
    expect(screen.getByTestId("audit-finding-1")).toBeInTheDocument();
    expect(screen.getByTestId("audit-finding-severity-0").textContent).toMatch(/blocker/i);
    expect(screen.getByTestId("audit-finding-severity-1").textContent).toMatch(/warning/i);
  });

  it("shows total/blocker/warning count badges", async () => {
    render(<AuditDashboard />);

    await screen.findByTestId("audit-finding-0");
    expect(screen.getByTestId("audit-count-total").textContent).toContain("2");
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("1");
    expect(screen.getByTestId("audit-count-warnings").textContent).toContain("1");
  });

  it("shows an Adopt button for automatic findings and a disabled Modify button otherwise", async () => {
    render(<AuditDashboard />);

    expect(await screen.findByTestId("audit-adopt-0")).toBeInTheDocument();
    const modifyBtn = screen.getByTestId("audit-modify-1");
    expect(modifyBtn).toBeInTheDocument();
    expect(modifyBtn).toBeDisabled();
    expect(modifyBtn).toHaveAttribute(
      "title",
      "A dangling parent cannot be invented automatically."
    );
  });

  // ---- Adopt: success ----

  it("removes the finding and shows a success toast when Adopt succeeds", async () => {
    vi.mocked(auditApi.remediate).mockResolvedValue({
      applied: true,
      finding_resolved: true,
      created_link_id: "link-001",
      proposal: PROJECT_REPORT.findings[0].remediation,
    });

    render(<AuditDashboard />);

    const adoptBtn = await screen.findByTestId("audit-adopt-0");
    fireEvent.click(adoptBtn);

    await waitFor(() => {
      expect(screen.queryByTestId("audit-finding-0")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("audit-toast")).toBeInTheDocument();
    expect(auditApi.remediate).toHaveBeenCalledWith("ws-001", {
      rule_id: "TRACE-P1",
      artifact_ids: ["11111111-1111-1111-1111-111111111111"],
      scope: "project",
      scope_artifact_id: undefined,
    });
  });

  // ---- Adopt: 422 (not automatically fixable) ----

  it("flips a finding into the Modify state when remediate returns 422", async () => {
    vi.mocked(auditApi.remediate).mockRejectedValue(
      new UnprocessableEntityError("Candidate became ambiguous; pick manually.")
    );

    render(<AuditDashboard />);

    const adoptBtn = await screen.findByTestId("audit-adopt-0");
    fireEvent.click(adoptBtn);

    const modifyBtn = await screen.findByTestId("audit-modify-0");
    expect(modifyBtn).toBeDisabled();
    expect(modifyBtn).toHaveAttribute("title", "Candidate became ambiguous; pick manually.");
    expect(screen.getByTestId("audit-finding-error-0").textContent).toBe(
      "Candidate became ambiguous; pick manually."
    );
    // The finding is still present (not removed) — only its action state changed.
    expect(screen.getByTestId("audit-finding-0")).toBeInTheDocument();
  });

  // ---- Scope switch ----

  it("re-runs the audit with scope=document and the selected artifact once a scope artifact is available", async () => {
    render(<AuditDashboard />);

    await screen.findByTestId("audit-finding-0");

    fireEvent.change(screen.getByTestId("audit-scope-select"), {
      target: { value: "document" },
    });

    await waitFor(() => {
      expect(screen.getByTestId("audit-scope-artifact-select")).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(auditApi.run).toHaveBeenCalledWith(
        "ws-001",
        expect.objectContaining({
          scope: "document",
          scopeArtifactId: "44444444-4444-4444-4444-444444444444",
        })
      );
    });

    expect(await screen.findByTestId("audit-empty")).toBeInTheDocument();
  });
});
