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
 *   - Modify (GitHub #451): enabled and navigates to the affected artifact's
 *     editor; not rendered at all when that artifact cannot be resolved
 *   - Scope switch (project -> document) re-runs the audit with the
 *     selected scope_artifact_id
 *   - data-testid attributes present (E2E contract)
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AuditDashboard } from "./audit-dashboard";
import { auditApi } from "../../api/audit";
import { artifactsApi } from "../../api/artifacts";
import { traceabilityApi } from "../../api/traceability";
import { UnprocessableEntityError } from "../../api/errors";
import type { AuditReport } from "../../api/audit";
import type { Artifact, PaginatedResponse } from "../../types";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    // Mimics i18next's {{placeholder}} interpolation for the `truncated`
    // banner (the only call site in this component that passes options).
    t: (key: string, fallback?: string, options?: Record<string, unknown>) => {
      const text = fallback ?? key;
      if (!options) return text;
      return Object.entries(options).reduce(
        // split/join instead of replaceAll: replaceAll is ES2021, but
        // tsconfig.json's `lib` is pinned to ES2020 (see frontend/tsconfig.json).
        (acc, [k, v]) => acc.split(`{{${k}}}`).join(String(v)),
        text
      );
    },
  }),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", () => ({
  useNavigate: () => mockNavigate,
}));

vi.mock("../../context/WorkspaceContext", () => ({
  useWorkspace: () => ({
    activeWorkspace: { id: "ws-001", name: "Test Workspace", preset: "extended" },
  }),
}));

vi.mock("../../api/audit");
vi.mock("../../api/artifacts");
vi.mock("../../api/traceability");

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const PROJECT_REPORT: AuditReport = {
  tier: "extended",
  scope: "project",
  scope_artifact_id: null,
  counts: { total: 2, blockers: 1, warnings: 1 },
  truncated: false,
  total_findings_available: 2,
  total_blockers_available: 1,
  total_warnings_available: 1,
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

const REQ_ARTIFACT_ID = "11111111-1111-1111-1111-111111111111";
const ARCH_ARTIFACT_ID = "33333333-3333-3333-3333-333333333333";
const REQ_ENTITY_ID = "aaaaaaaa-1111-1111-1111-111111111111";
const ARCH_ENTITY_ID = "cccccccc-3333-3333-3333-333333333333";

/** A finding whose only artifact has no backing domain row (`resolved: false`). */
const DANGLING_ARTIFACT_ID = "99999999-9999-9999-9999-999999999999";

const DANGLING_REPORT: AuditReport = {
  tier: "extended",
  scope: "project",
  scope_artifact_id: null,
  counts: { total: 1, blockers: 1, warnings: 0 },
  truncated: false,
  total_findings_available: 1,
  total_blockers_available: 1,
  total_warnings_available: 0,
  findings: [
    {
      rule_id: "TRACE-P7",
      severity: "blocker",
      message: "Trace link crosses the scope boundary.",
      artifact_ids: [DANGLING_ARTIFACT_ID],
      scope: "project",
      scope_artifact_id: null,
      index: 0,
      remediation: {
        rule_id: "TRACE-P7",
        automatic: false,
        reason: "No automatic remediation is available for TRACE-P7.",
        finding_artifact_ids: [DANGLING_ARTIFACT_ID],
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
  truncated: false,
  total_findings_available: 0,
  total_blockers_available: 0,
  total_warnings_available: 0,
  findings: [],
};

// BUG-15: the backend caps the returned findings when a run produces more
// than AuditService.MAX_REPORT_FINDINGS — reuse PROJECT_REPORT's 2 findings
// as the "shown" subset of a much larger run. Mirrors the audit's 300-req
// stress scenario: 4,440 real findings, all severity blocker.
const TRUNCATED_REPORT: AuditReport = {
  ...PROJECT_REPORT,
  truncated: true,
  total_findings_available: 4440,
  total_blockers_available: 4440,
  total_warnings_available: 0,
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

  // #451: the Modify action needs the Artifact id -> entity id mapping from
  // GET /traceability/resolve/ to build an editor route. Unknown ids answer
  // `resolved: false`, which is a normal response, not an error.
  vi.mocked(traceabilityApi.resolve).mockImplementation((ids) =>
    Promise.resolve(
      ids.map((artifactId) => {
        if (artifactId === REQ_ARTIFACT_ID) {
          return {
            artifact_id: artifactId,
            resolved: true,
            entity_type: "Requirement",
            entity_id: REQ_ENTITY_ID,
          };
        }
        if (artifactId === ARCH_ARTIFACT_ID) {
          return {
            artifact_id: artifactId,
            resolved: true,
            entity_type: "ArchitectureElement",
            entity_id: ARCH_ENTITY_ID,
          };
        }
        return {
          artifact_id: artifactId,
          resolved: false,
          entity_type: null,
          entity_id: null,
        };
      })
    )
  );
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

  it("shows an Adopt button for automatic findings and an enabled Modify button otherwise", async () => {
    render(<AuditDashboard />);

    expect(await screen.findByTestId("audit-adopt-0")).toBeInTheDocument();
    const modifyBtn = await screen.findByTestId("audit-modify-1");
    expect(modifyBtn).toBeInTheDocument();
    // GitHub #451: the whole point — this used to be permanently disabled,
    // leaving every finding without an automatic proposal unfixable via the UI.
    expect(modifyBtn).not.toBeDisabled();
  });

  // GitHub #451: Modify must actually go somewhere. Findings are derived from
  // the trace graph and never persisted, so the only way to clear one is to
  // correct the artifact it points at — the button navigates to that editor,
  // resolving the finding's *Artifact* id to the *entity* id the route takes.
  it("navigates to the affected artifact's editor when Modify is clicked", async () => {
    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-modify-1"));

    expect(mockNavigate).toHaveBeenCalledWith(`/architecture/${ARCH_ENTITY_ID}`);
  });

  it("resolves the finding's artifact ids through the batch resolve endpoint", async () => {
    render(<AuditDashboard />);

    await screen.findByTestId("audit-modify-1");
    expect(traceabilityApi.resolve).toHaveBeenCalledWith(
      expect.arrayContaining([REQ_ARTIFACT_ID, ARCH_ARTIFACT_ID])
    );
  });

  // GitHub #451: the reason must also be visible as text, not only as a hover
  // `title` — every finding without a registered automatic remediation lands
  // here (the common case, not an edge case), and a hover-only tooltip is not
  // discoverable via keyboard/touch/screen reader.
  it("shows the not-auto-fixable reason as visible text next to the Modify button", async () => {
    render(<AuditDashboard />);

    const reason = await screen.findByTestId("audit-modify-reason-1");
    expect(reason.textContent).toContain(
      "A dangling parent cannot be invented automatically."
    );
  });

  // GitHub #451: a control that cannot do anything is worse than no control —
  // when the subject artifact has no editor route, render no button at all
  // instead of a permanently disabled one.
  it("renders no Modify button when the finding's artifact cannot be resolved", async () => {
    vi.mocked(auditApi.run).mockResolvedValue(DANGLING_REPORT);

    render(<AuditDashboard />);

    const reason = await screen.findByTestId("audit-modify-reason-0");
    expect(reason.textContent).toContain(
      "This finding references no artifact that can be opened"
    );
    expect(screen.queryByTestId("audit-modify-0")).not.toBeInTheDocument();
  });

  // GitHub #451: "Adopt" (TRACE-P5 et al.) vs "Modify" is the automatic/manual
  // split of the backend's remediation analysis, not a per-rule inconsistency.
  it("explains the Adopt/Modify distinction in a legend", async () => {
    render(<AuditDashboard />);

    const legend = await screen.findByTestId("audit-action-legend");
    expect(legend.textContent).toContain("Adopt applies the correction");
    expect(legend.textContent).toContain("Modify opens the affected artifact");
  });

  // GitHub #450: the scope selector must stay interactive (mirrors the
  // severity selector on the same page, and ListToolbar's list pages), not
  // gated on the in-flight audit run.
  it("never disables the scope select, even while a request is in flight", async () => {
    render(<AuditDashboard />);

    const scopeSelect = await screen.findByTestId("audit-scope-select");
    expect(scopeSelect).not.toBeDisabled();

    fireEvent.click(screen.getByTestId("audit-refresh-btn"));
    expect(scopeSelect).not.toBeDisabled();

    await waitFor(() =>
      expect(screen.getByTestId("audit-refresh-btn")).not.toBeDisabled()
    );
    expect(scopeSelect).not.toBeDisabled();
  });

  // ---- BUG-15: truncated result set ----

  it("shows a truncation banner with shown/total counts when the backend caps the result", async () => {
    vi.mocked(auditApi.run).mockResolvedValue(TRUNCATED_REPORT);

    render(<AuditDashboard />);

    const banner = await screen.findByTestId("audit-truncated-banner");
    expect(banner.textContent).toContain("2");
    expect(banner.textContent).toContain("4440");
  });

  it("renders no truncation banner when the result set is not capped", async () => {
    render(<AuditDashboard />);

    await screen.findByTestId("audit-finding-0");
    expect(screen.queryByTestId("audit-truncated-banner")).not.toBeInTheDocument();
  });

  // Code review M3: the count badges must show the backend's true pre-cap
  // totals when truncated, not the length of the (capped) findings array —
  // otherwise a workspace with 4,440 real blockers shows "500" (or here, the
  // 2-item fixture's "1") with no indication the number is partial.
  it("shows the true pre-cap totals in the count badges when truncated, not the capped array length", async () => {
    vi.mocked(auditApi.run).mockResolvedValue(TRUNCATED_REPORT);

    render(<AuditDashboard />);

    await screen.findByTestId("audit-truncated-banner");
    expect(screen.getByTestId("audit-count-total").textContent).toContain("4440");
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("4440");
    expect(screen.getByTestId("audit-count-warnings").textContent).toContain("0");
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
    // #451: the fallback is a usable manual action, not a dead disabled button.
    expect(modifyBtn).not.toBeDisabled();
    expect(screen.getByTestId("audit-modify-reason-0").textContent).toContain(
      "Candidate became ambiguous; pick manually."
    );
    expect(screen.getByTestId("audit-finding-error-0").textContent).toBe(
      "Candidate became ambiguous; pick manually."
    );
    // The finding is still present (not removed) — only its action state changed.
    expect(screen.getByTestId("audit-finding-0")).toBeInTheDocument();

    fireEvent.click(modifyBtn);
    expect(mockNavigate).toHaveBeenCalledWith(`/requirements/${REQ_ENTITY_ID}`);
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
