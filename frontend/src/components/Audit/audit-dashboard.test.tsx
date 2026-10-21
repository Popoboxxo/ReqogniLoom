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

import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { AuditDashboard } from "./audit-dashboard";
import { auditApi } from "../../api/audit";
import { artifactsApi } from "../../api/artifacts";
import { traceabilityApi } from "../../api/traceability";
import { ForbiddenError, UnprocessableEntityError } from "../../api/errors";
import type { AuditFinding, AuditReport, SuppressionView } from "../../api/audit";
import type { Artifact, PaginatedResponse } from "../../types";
import { resolveLocaleKey } from "../../test/i18n-test-helpers";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    // Mimics i18next's `{{placeholder}}` interpolation for the banners (the
    // only call sites in this component that pass options).
    //
    // Two call shapes exist in the component: `t(key, "default", options)` and
    // — for keys that are fully translated (#1383) — `t(key, options)`. In the
    // second shape the options object is the *second* argument, exactly like
    // real i18next; the template then comes from the locale file instead of an
    // inline default, so this mock resolves it from de.json. `t(key)` alone
    // resolves from de.json too, like i18next (a raw key would hide a missing
    // translation behind the key itself).
    t: (
      key: string,
      fallback?: string | Record<string, unknown>,
      options?: Record<string, unknown>
    ) => {
      const optionsOnly = typeof fallback === "object" && fallback !== null;
      const template = optionsOnly
        ? (resolveLocaleKey(key) ?? key)
        : (fallback ?? resolveLocaleKey(key) ?? key);
      const vars = optionsOnly ? fallback : options;
      if (!vars) return template;
      return Object.entries(vars).reduce(
        // split/join instead of replaceAll: replaceAll is ES2021, but
        // tsconfig.json's `lib` is pinned to ES2020 (see frontend/tsconfig.json).
        (acc, [k, v]) => acc.split(`{{${k}}}`).join(String(v)),
        template
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
  useOptionalWorkspace: () => ({
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
  // #1382/#1383: full-run ground truth. Here the run *is* the mounted window.
  counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
  page_counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
  truncated: false,
  total_findings_available: 2,
  total_blockers_available: 1,
  total_effective_blockers: 1,
  total_warnings_available: 1,
  total_suppressed_available: 0,
  total_suppressed_blockers_available: 0,
  suppressed_filtered: 0,
  offset: 0,
  next_offset: null,
  findings: [
    {
      rule_id: "TRACE-P1",
      severity: "blocker",
      message: "Requirement REQ-1 has no derives-from link.",
      artifact_ids: ["11111111-1111-1111-1111-111111111111"],
      scope: "project",
      scope_artifact_id: null,
      index: 0,
      finding_key: "TRACE-P1\x1f11111111-1111-1111-1111-111111111111",
      suppressed: false,
      suppressed_until: null,
      suppression_reason: null,
      suppression_id: null,
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
      finding_key: "TRACE-P4\x1f33333333-3333-3333-3333-333333333333",
      suppressed: false,
      suppressed_until: null,
      suppression_reason: null,
      suppression_id: null,
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
  counts: { total: 1, blockers: 1, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
  page_counts: { total: 1, blockers: 1, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
  truncated: false,
  total_findings_available: 1,
  total_blockers_available: 1,
  total_effective_blockers: 1,
  total_warnings_available: 0,
  total_suppressed_available: 0,
  total_suppressed_blockers_available: 0,
  suppressed_filtered: 0,
  offset: 0,
  next_offset: null,
  findings: [
    {
      rule_id: "TRACE-P7",
      severity: "blocker",
      message: "Trace link crosses the scope boundary.",
      artifact_ids: [DANGLING_ARTIFACT_ID],
      scope: "project",
      scope_artifact_id: null,
      index: 0,
      finding_key: `TRACE-P7\x1f${DANGLING_ARTIFACT_ID}`,
      suppressed: false,
      suppressed_until: null,
      suppression_reason: null,
      suppression_id: null,
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
  counts: { total: 0, blockers: 0, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
  page_counts: { total: 0, blockers: 0, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
  truncated: false,
  total_findings_available: 0,
  total_blockers_available: 0,
  total_effective_blockers: 0,
  total_warnings_available: 0,
  total_suppressed_available: 0,
  total_suppressed_blockers_available: 0,
  suppressed_filtered: 0,
  offset: 0,
  next_offset: null,
  findings: [],
};

// BUG-15: reuse PROJECT_REPORT's 2 findings as the "shown" subset of a much
// larger run. Mirrors the audit's 300-req stress scenario: 4,440 real
// findings, all severity blocker.
//
// #1382/#1383: `counts` is the FULL-run ground truth (4,440) while the two
// mounted findings are only the window the response returned — the regression
// this fixture guards is that the badges used to show "2" (or "1" blocker)
// when a partial window was mounted.
const TRUNCATED_REPORT: AuditReport = {
  ...PROJECT_REPORT,
  counts: { total: 4440, blockers: 4440, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
  page_counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
  truncated: true,
  total_findings_available: 4440,
  total_blockers_available: 4440,
  total_effective_blockers: 4440,
  total_warnings_available: 0,
  next_offset: 2,
};

// #569: one persisted suppression (the POST .../audit/waivers/ response body).
const WAIVER_VIEW: SuppressionView = {
  waiver_id: "waiver-001",
  finding_key: "TRACE-P1\x1f11111111-1111-1111-1111-111111111111",
  identity_key: "TRACE-P1\x1f11111111-1111-1111-1111-111111111111\x1fproject",
  rule_id: "TRACE-P1",
  artifact_ids: ["11111111-1111-1111-1111-111111111111"],
  scope: "project",
  scope_artifact_id: "",
  reason: "Accepted deviation — documented in the safety case.",
  granted_by: "user-1",
  created_at: "2026-09-22T10:00:00Z",
  expires_at: null,
  state: "active",
};

const WAIVE_REASON = "Accepted deviation — documented in the safety case.";

// ---------------------------------------------------------------------------
// #596: paged findings (one bounded window per request, `?limit=&offset=`)
// ---------------------------------------------------------------------------

/** A single finding at the given position of a (logical) 250-finding run. */
function findingAt(index: number): AuditFinding {
  return {
    rule_id: `TRACE-P${index % 3}`,
    severity: index < 200 ? "blocker" : "warning",
    message: `finding ${index}`,
    artifact_ids: [],
    scope: "project",
    scope_artifact_id: null,
    index,
    // #569/#1383: the run-independent identity. Unique per finding — an empty
    // artifact list would otherwise collapse every finding of a rule onto one
    // key, which is exactly what the append dedupe must not do.
    finding_key: `TRACE-P${index % 3}\x1fartifact-${index}`,
    suppressed: false,
    suppressed_until: null,
    suppression_reason: null,
    suppression_id: null,
    remediation: {
      rule_id: `TRACE-P${index % 3}`,
      automatic: false,
      reason: "Manual correction required.",
      finding_artifact_ids: [],
      action_kind: null,
      params: {},
    },
  };
}

/**
 * `findingAt` with an automatic remediation, so its row renders an Adopt
 * button (NF-A: the adopt-then-paginate cursor shift).
 */
function adoptableFindingAt(index: number): AuditFinding {
  const base = findingAt(index);
  return {
    ...base,
    remediation: { ...base.remediation, automatic: true, action_kind: "create_trace_link" },
  };
}

/** A window of `length` findings starting at `offset`, of a 250-finding run. */
function windowReport(offset: number, length: number): AuditReport {
  const total = 250;
  const findings = Array.from({ length }, (_unused, i) => findingAt(offset + i));
  const end = offset + findings.length;
  return {
    tier: "extended",
    scope: "project",
    scope_artifact_id: null,
    // #1382/#1383: `counts` is the whole run (identical for every window);
    // `page_counts` is this window only.
    counts: { total, blockers: 200, warnings: 50, suppressed: 0, suppressed_blockers: 0 },
    page_counts: {
      total: findings.length,
      blockers: findings.filter((f) => f.severity === "blocker").length,
      warnings: findings.filter((f) => f.severity === "warning").length,
      suppressed: 0,
      suppressed_blockers: 0,
    },
    // #622: with a `limit` this flag means "more findings exist past this
    // window", not "the backend capped the result set".
    truncated: end < total,
    total_findings_available: total,
    total_blockers_available: 200,
    total_effective_blockers: 200,
    total_warnings_available: 50,
    total_suppressed_available: 0,
    total_suppressed_blockers_available: 0,
    suppressed_filtered: 0,
    offset,
    // #1383: the server cursor. `null` once the last window has been returned.
    next_offset: end < total ? end : null,
    findings,
  };
}

/**
 * A faithful post-adopt window (NFA-3).
 *
 * `identities` names the findings by their *pre-adopt* position — that is what
 * their message and `finding_key` carry. `index` is the position in the
 * **current** run, derived from `offset`, exactly like the server reports it.
 * Because the run shrank, such a position can equal the stale index of a row
 * that is already mounted — which is the NFA-2 case, not a fixture artefact.
 * `adoptable` marks the identities whose remediation is automatic.
 */
function shiftedWindow({
  offset,
  identities,
  nextOffset,
  total,
  blockers,
  warnings,
  adoptable = [],
}: {
  offset: number;
  identities: number[];
  nextOffset: number | null;
  total: number;
  blockers: number;
  warnings: number;
  adoptable?: number[];
}): AuditReport {
  const findings = identities.map((identity, i) => ({
    ...(adoptable.includes(identity) ? adoptableFindingAt(identity) : findingAt(identity)),
    index: offset + i,
  }));
  return {
    tier: "extended",
    scope: "project",
    scope_artifact_id: null,
    counts: { total, blockers, warnings, suppressed: 0, suppressed_blockers: 0 },
    page_counts: {
      total: findings.length,
      blockers: findings.filter((f) => f.severity === "blocker").length,
      warnings: findings.filter((f) => f.severity === "warning").length,
      suppressed: 0,
      suppressed_blockers: 0,
    },
    truncated: nextOffset !== null,
    total_findings_available: total,
    total_blockers_available: blockers,
    total_effective_blockers: blockers,
    total_warnings_available: warnings,
    total_suppressed_available: 0,
    total_suppressed_blockers_available: 0,
    suppressed_filtered: 0,
    offset,
    next_offset: nextOffset,
    findings,
  };
}

/**
 * Messages of every mounted finding row, sorted (NFA-3).
 *
 * `audit-finding-<index>` is the E2E contract and stays index-based, so once a
 * shifted window reuses the stale index of a mounted row two rows carry the
 * same `data-testid`. Identity-based assertions therefore read the finding's
 * message instead of resolving a single testid.
 */
function mountedFindingMessages(): string[] {
  return screen
    .queryAllByTestId(/^audit-finding-\d+$/)
    .map((row) => within(row).getByText(/^finding \d+$/).textContent ?? "")
    .sort();
}

/** The `<li>` row of the finding whose message is exactly `finding <n>`. */
function findingRow(message: string): HTMLElement {
  const row = screen.getByText(message).closest("li");
  if (!row) throw new Error(`no finding row for "${message}"`);
  return row;
}

function setupDefaultMocks(): void {
  vi.mocked(auditApi.run).mockImplementation((_wsId, options) => {
    if (options?.scope === "document") return Promise.resolve(DOCUMENT_REPORT);
    return Promise.resolve(PROJECT_REPORT);
  });
  // #569: the dashboard also loads the suppression list (both lifecycles) so
  // an *expired* suppression stays visible and distinguishable. Default: none.
  vi.mocked(auditApi.waivers).mockResolvedValue({
    waivers: [],
    counts: { active: 0, expired: 0 },
  });
  // Default successful waive — tests that exercise the failure paths override
  // this with `mockRejectedValue`.
  vi.mocked(auditApi.waive).mockResolvedValue(WAIVER_VIEW);
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

  // Strengthened (#1382/#1383): the run totals and the mounted window
  // deliberately differ here, so this cannot pass by comparing a number with
  // itself (the old fixture had `counts === page_counts === findings.length`).
  it("shows total/blocker/warning count badges from the run, not the window", async () => {
    vi.mocked(auditApi.run).mockResolvedValue({
      ...PROJECT_REPORT,
      counts: { total: 9, blockers: 5, warnings: 4, suppressed: 0, suppressed_blockers: 0 },
      page_counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
      total_findings_available: 9,
      total_blockers_available: 5,
      total_warnings_available: 4,
    });

    render(<AuditDashboard />);

    await screen.findByTestId("audit-finding-0");
    expect(screen.getByTestId("audit-count-total").textContent).toContain("9");
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("5");
    expect(screen.getByTestId("audit-count-warnings").textContent).toContain("4");
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

  // #1382 regression: the badges are the report's `counts` (ground truth over
  // the FULL run), not a recount of the mounted window. Before the fix a
  // 2-row window of a 7-finding run rendered "Findings: 2".
  it("renders the full-run counts while only a smaller window is mounted (#1382)", async () => {
    vi.mocked(auditApi.run).mockResolvedValue({
      ...PROJECT_REPORT,
      counts: { total: 7, blockers: 4, warnings: 3, suppressed: 0, suppressed_blockers: 0 },
      page_counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
      truncated: true,
      total_findings_available: 7,
      total_blockers_available: 4,
      total_effective_blockers: 4,
      total_warnings_available: 3,
      next_offset: 2,
    });

    render(<AuditDashboard />);

    await screen.findByTestId("audit-truncated-banner");
    expect(screen.getByTestId("audit-count-total").textContent).toContain("7");
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("4");
    expect(screen.getByTestId("audit-count-warnings").textContent).toContain("3");
  });

  // #1383: "X of Y" names the *window* (page_counts.total) against the *run*
  // (counts.total) — the mounted row count is a third, separate number.
  it("renders the window size from page_counts against counts.total (#1383)", async () => {
    vi.mocked(auditApi.run).mockResolvedValue({
      ...PROJECT_REPORT,
      counts: { total: 7, blockers: 4, warnings: 3, suppressed: 0, suppressed_blockers: 0 },
      page_counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
      truncated: true,
      total_findings_available: 7,
      total_blockers_available: 4,
      total_effective_blockers: 4,
      total_warnings_available: 3,
      next_offset: 2,
    });

    render(<AuditDashboard />);

    const banner = await screen.findByTestId("audit-truncated-banner");
    // 2 = page_counts.total (this response's window), 7 = counts.total (run).
    expect(banner.textContent).toMatch(/2 of 7/);
  });

  // #1382 (rolling deploy, both blocks present): `page_counts` is additive, so
  // a backend can send it while `counts` still describes the returned window.
  // When `counts.total` disagrees with `total_findings_available` the invariant
  // `counts.total === total_findings_available` is broken, so the additive
  // full-run fields win — otherwise a window becomes the run total again.
  it("prefers total_findings_available when counts and page_counts disagree (#1382)", async () => {
    vi.mocked(auditApi.run).mockResolvedValue({
      ...PROJECT_REPORT,
      // Pre-#1383 window-scoped `counts` next to an already-upgraded
      // `page_counts` block — the shape a future backend could emit.
      counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
      page_counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
      total_findings_available: 4440,
      total_blockers_available: 4440,
      total_warnings_available: 0,
      total_suppressed_available: 0,
      total_suppressed_blockers_available: 0,
    });

    render(<AuditDashboard />);

    await screen.findByTestId("audit-finding-0");
    expect(screen.getByTestId("audit-count-total").textContent).toContain("4440");
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("4440");
    expect(screen.getByTestId("audit-count-warnings").textContent).toContain("0");
  });

  // #1382: "the trace graph is consistent" is a statement about the RUN, so it
  // may only be rendered when the run is empty. Deriving it from the mounted,
  // filtered rows made a filter that hides everything read as a clean graph
  // while the ground-truth badges still reported findings.
  it("renders a neutral message when a filter hides every mounted finding (#1382)", async () => {
    vi.mocked(auditApi.run).mockResolvedValue({
      ...PROJECT_REPORT,
      counts: { total: 7, blockers: 0, warnings: 7, suppressed: 0, suppressed_blockers: 0 },
      page_counts: { total: 1, blockers: 0, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
      total_findings_available: 7,
      total_blockers_available: 0,
      total_warnings_available: 7,
      // Only warning rows are mounted, so the severity filter hides all of them.
      findings: [PROJECT_REPORT.findings[1]],
    });

    render(<AuditDashboard />);
    await screen.findByTestId("audit-finding-1");

    fireEvent.change(screen.getByTestId("audit-severity-filter"), {
      target: { value: "blocker" },
    });

    const neutral = await screen.findByTestId("audit-no-filter-match");
    expect(neutral.textContent).toBe(resolveLocaleKey("audit.noFilterMatch"));
    expect(screen.queryByTestId("audit-empty")).not.toBeInTheDocument();
    expect(screen.getByTestId("audit-count-total").textContent).toContain("7");
  });

  // ---- Failed run must never look like a clean run (GitHub #952) ----

  // Defensive hardening for the reported UI false-negative (the API reported
  // 24 blockers while the page showed "Findings: 0 · consistent"): the page
  // must not decide "run succeeded" from the truthiness of an error *message*.
  // An error carrying an empty message is reachable (the backend contract
  // never validates it, and a transport failure can surface with none), and
  // before this fix it fell straight through to the green empty state — a
  // failed audit rendered as a successful, consistent trace graph.
  it("renders the error banner instead of the empty state when a failed run has an empty message", async () => {
    vi.mocked(auditApi.run).mockRejectedValue(new Error(""));

    render(<AuditDashboard />);

    const banner = await screen.findByTestId("audit-load-error");
    // Non-empty fallback: the banner must still say something.
    expect(banner.textContent?.trim()).toBe("Could not load audit findings.");
    expect(screen.queryByTestId("audit-empty")).not.toBeInTheDocument();
    expect(
      screen.queryByText("No findings — the trace graph is consistent for this scope.")
    ).not.toBeInTheDocument();
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

    // UI-57: Adopt now interposes a confirmation before firing the mutation.
    const confirmBtn = await screen.findByTestId("audit-adopt-confirm-confirm");
    fireEvent.click(confirmBtn);

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

    // UI-57: Adopt now interposes a confirmation before firing the mutation.
    const confirmBtn = await screen.findByTestId("audit-adopt-confirm-confirm");
    fireEvent.click(confirmBtn);

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

// ---------------------------------------------------------------------------
// #596 — the findings list is mounted in bounded windows and can page past the
// first one, instead of rendering the whole (480 KB at 500 findings) run.
// ---------------------------------------------------------------------------

describe("AuditDashboard — paged findings (#596)", () => {
  /** Mocks `run` as a real #622-style windowed endpoint over a 250-finding run. */
  function setupWindowedEndpoint(): void {
    vi.mocked(auditApi.run).mockImplementation((_wsId, options) => {
      const offset = options?.offset ?? 0;
      const limit = options?.limit ?? 250;
      return Promise.resolve(
        windowReport(offset, Math.max(0, Math.min(limit, 250 - offset)))
      );
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
    setupWindowedEndpoint();
  });

  it("requests only the first window on load instead of the whole run", async () => {
    render(<AuditDashboard />);

    await screen.findByTestId("audit-finding-0");

    expect(auditApi.run).toHaveBeenCalledWith(
      "ws-001",
      expect.objectContaining({ limit: 100, offset: 0 })
    );
    // The DOM holds one window: findings 0..99, not all 250.
    expect(screen.getByTestId("audit-finding-99")).toBeInTheDocument();
    expect(screen.queryByTestId("audit-finding-100")).not.toBeInTheDocument();
  });

  it("shows the banner and the load-more control while more findings exist", async () => {
    render(<AuditDashboard />);

    const banner = await screen.findByTestId("audit-truncated-banner");
    expect(banner.textContent).toContain("100");
    expect(banner.textContent).toContain("250");
    expect(screen.getByTestId("audit-load-more-btn")).toBeInTheDocument();
  });

  it("appends the next window and drops the control once every finding is mounted", async () => {
    render(<AuditDashboard />);

    await screen.findByTestId("audit-load-more-btn");
    fireEvent.click(screen.getByTestId("audit-load-more-btn"));

    // Second window: 100..199, appended (the first window stays mounted).
    expect(await screen.findByTestId("audit-finding-100")).toBeInTheDocument();
    expect(screen.getByTestId("audit-finding-0")).toBeInTheDocument();
    expect(auditApi.run).toHaveBeenLastCalledWith(
      "ws-001",
      expect.objectContaining({ limit: 100, offset: 100 })
    );

    fireEvent.click(screen.getByTestId("audit-load-more-btn"));

    // Third and last window: 200..249 — `truncated` is false now, so the
    // banner and the button disappear again.
    await waitFor(() => {
      expect(screen.getByTestId("audit-finding-249")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("audit-load-more-btn")).not.toBeInTheDocument();
    expect(screen.queryByTestId("audit-truncated-banner")).not.toBeInTheDocument();
  });

  it("keeps the true totals in the count badges until every window is loaded", async () => {
    render(<AuditDashboard />);

    await screen.findByTestId("audit-load-more-btn");
    // Only 100 of 250 findings are mounted, but the badges must not understate
    // the run: they show the full-run `counts` (#1382/#1383).
    expect(screen.getByTestId("audit-count-total").textContent).toContain("250");
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("200");
  });

  // #1383: a second call must continue from the server's `next_offset`, never
  // from `offset + findings.length` — the two differ as soon as the server
  // skips a finding, and the old recomputation then re-requests a wrong window.
  it("uses the response's next_offset as the Load-more cursor (#1383)", async () => {
    vi.mocked(auditApi.run)
      .mockResolvedValueOnce({
        ...PROJECT_REPORT,
        counts: { total: 250, blockers: 200, warnings: 50, suppressed: 0, suppressed_blockers: 0 },
        page_counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
        truncated: true,
        offset: 0,
        // Deliberately not `offset + findings.length` (2).
        next_offset: 60,
      })
      .mockResolvedValueOnce(windowReport(60, 100));

    render(<AuditDashboard />);

    await screen.findByTestId("audit-load-more-btn");
    fireEvent.click(screen.getByTestId("audit-load-more-btn"));

    await waitFor(() =>
      expect(auditApi.run).toHaveBeenLastCalledWith(
        "ws-001",
        expect.objectContaining({ limit: 100, offset: 60 })
      )
    );
  });

  // #1382: `truncated` without an advancing cursor must stop paging and say
  // so. Fabricating `offset + findings.length` re-requested the same window
  // forever (or silently hid the rest of the run) and masked the broken
  // backend. `0` and `null` are both terminal on a modern backend, which is
  // recognisable by the presence of `page_counts`.
  it.each([
    ["0", 0],
    ["null", null],
  ])(
    "stops paging when truncated is true and next_offset is %s (#1383)",
    async (_label, nextOffset) => {
      vi.mocked(auditApi.run).mockResolvedValue({
        ...windowReport(0, 100),
        next_offset: nextOffset,
      });

      render(<AuditDashboard />);

      const error = await screen.findByTestId("audit-load-error");
      expect(error.textContent).toBe(resolveLocaleKey("audit.pagingStalled"));
      expect(screen.queryByTestId("audit-load-more-btn")).not.toBeInTheDocument();
      // No second request: the loop is stopped at the resolver, not by luck.
      expect(auditApi.run).toHaveBeenCalledTimes(1);
    }
  );

  // #1382: the local deltas mean "since the last snapshot". "Load more" adopts
  // a fresh run snapshot, which already excludes the adopted finding, so the
  // delta has to be dropped — otherwise the badge subtracts it twice
  // (250 -> 249 locally, then 249 - 1 = 248 against the fresh snapshot).
  it("applies a local adopt exactly once when Load more adopts a new snapshot (#1382)", async () => {
    vi.mocked(auditApi.run)
      .mockResolvedValueOnce({
        ...PROJECT_REPORT,
        counts: { total: 250, blockers: 250, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
        page_counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
        truncated: true,
        total_findings_available: 250,
        total_blockers_available: 250,
        total_effective_blockers: 250,
        total_warnings_available: 0,
        next_offset: 2,
      })
      // The next run: the Adopt removed one finding, so the snapshot is 249.
      .mockResolvedValueOnce({
        ...windowReport(2, 2),
        counts: { total: 249, blockers: 249, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
        total_findings_available: 249,
        total_blockers_available: 249,
        total_effective_blockers: 249,
        total_warnings_available: 0,
        truncated: false,
        next_offset: null,
      });
    vi.mocked(auditApi.remediate).mockResolvedValue({
      applied: true,
      finding_resolved: true,
      created_link_id: "link-001",
      proposal: PROJECT_REPORT.findings[0].remediation,
    });

    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-adopt-0"));
    fireEvent.click(await screen.findByTestId("audit-adopt-confirm-confirm"));
    await waitFor(() =>
      expect(screen.getByTestId("audit-count-total").textContent).toContain("249")
    );

    fireEvent.click(screen.getByTestId("audit-load-more-btn"));
    // The banner disappearing proves the fresh snapshot was committed.
    await waitFor(() =>
      expect(screen.queryByTestId("audit-truncated-banner")).not.toBeInTheDocument()
    );
    expect(screen.getByTestId("audit-count-total").textContent).toContain("249");
    expect(screen.getByTestId("audit-count-total").textContent).not.toContain("248");
  });

  // NF-A (BLOCKING): a local Adopt removes a row, so every finding behind it
  // shifts one position down — the server cursor is only valid for the run
  // that produced it. Adopting old index 0 of a 250-run must move the cursor
  // from 2 to 1; paging from 2 would return old 3 and 4 and silently never
  // mount old index 2 (which is new index 1) until Refresh.
  it("shifts the Load-more cursor after an Adopt so no finding is skipped (NF-A)", async () => {
    vi.mocked(auditApi.run).mockImplementation((_wsId, options) => {
      const offset = options?.offset ?? 0;
      if (offset === 0) {
        return Promise.resolve({
          ...windowReport(0, 2),
          counts: { total: 250, blockers: 200, warnings: 50, suppressed: 0, suppressed_blockers: 0 },
          page_counts: { total: 2, blockers: 2, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
          truncated: true,
          total_findings_available: 250,
          total_blockers_available: 200,
          total_effective_blockers: 200,
          total_warnings_available: 50,
          next_offset: 2,
          findings: [adoptableFindingAt(0), findingAt(1)],
        });
      }
      // Post-adopt snapshot: 249 findings. Old index `i` now lives at new
      // index `i - 1`, so this window starts at old index `offset + 1` — and
      // labels those findings with their *current-run* position `offset`,
      // `offset + 1` (NFA-3). Old index 1 is still mounted under its stale
      // index 1, so the two rows share `data-testid="audit-finding-1"`; the
      // assertions below therefore compare mounted identities, not testids.
      return Promise.resolve(
        shiftedWindow({
          offset,
          identities: [offset + 1, offset + 2],
          nextOffset: null,
          total: 249,
          blockers: 199,
          warnings: 50,
        })
      );
    });
    vi.mocked(auditApi.remediate).mockResolvedValue({
      applied: true,
      finding_resolved: true,
      created_link_id: "link-001",
      proposal: adoptableFindingAt(0).remediation,
    });

    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-adopt-0"));
    fireEvent.click(await screen.findByTestId("audit-adopt-confirm-confirm"));
    await waitFor(() =>
      expect(screen.queryByTestId("audit-finding-0")).not.toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("audit-load-more-btn"));

    // The cursor followed the locally removed row: 2 -> 1, not the stale 2.
    await waitFor(() =>
      expect(auditApi.run).toHaveBeenLastCalledWith(
        "ws-001",
        expect.objectContaining({ offset: 1 })
      )
    );
    // ...so the shifted window still mounts old index 2 (the row the stale
    // cursor would have skipped) next to old index 3. Nothing else was lost:
    // old 0 was adopted, old 1..3 are mounted — asserted by identity because
    // old 1 and old 2 now share the index 1 testid.
    await waitFor(() =>
      expect(mountedFindingMessages()).toEqual(["finding 1", "finding 2", "finding 3"])
    );
  });

  // NFA-1 (BLOCKING): the old guard compared a *stale snapshot* index against
  // an already-decremented cursor, so a second adopt on the same page did not
  // decrement at all (2 -> 1, then index 1 < 1 is false). "Load more" then
  // paged from 1 instead of 0 and the finding that moved into the second
  // adopted slot was skipped permanently. The adopted row is always mounted
  // and covered by the cursor, so every adopt decrements by exactly one.
  it("decrements the cursor on every Adopt of the same page (NFA-1)", async () => {
    let firstPageServed = false;
    vi.mocked(auditApi.run).mockImplementation((_wsId, options) => {
      const offset = options?.offset ?? 0;
      if (offset === 0 && !firstPageServed) {
        firstPageServed = true;
        // A 6-finding run; the first page mounts two adoptable findings.
        return Promise.resolve(
          shiftedWindow({
            offset: 0,
            identities: [0, 1],
            nextOffset: 2,
            total: 6,
            blockers: 6,
            warnings: 0,
            adoptable: [0, 1],
          })
        );
      }
      // Post-adopt run: old 2..5 now sit at positions 0..3.
      if (offset === 0) {
        return Promise.resolve(
          shiftedWindow({
            offset: 0,
            identities: [2, 3],
            nextOffset: 2,
            total: 4,
            blockers: 4,
            warnings: 0,
          })
        );
      }
      return Promise.resolve(
        shiftedWindow({
          offset,
          identities: [4, 5],
          nextOffset: null,
          total: 4,
          blockers: 4,
          warnings: 0,
        })
      );
    });
    vi.mocked(auditApi.remediate).mockResolvedValue({
      applied: true,
      finding_resolved: true,
      created_link_id: "link-001",
      proposal: adoptableFindingAt(0).remediation,
    });

    render(<AuditDashboard />);

    // Two adopts on the first page: cursor 2 -> 1 -> 0.
    fireEvent.click(await screen.findByTestId("audit-adopt-0"));
    fireEvent.click(await screen.findByTestId("audit-adopt-confirm-confirm"));
    await waitFor(() => expect(mountedFindingMessages()).toEqual(["finding 1"]));

    fireEvent.click(screen.getByTestId("audit-adopt-1"));
    fireEvent.click(await screen.findByTestId("audit-adopt-confirm-confirm"));
    await waitFor(() => expect(mountedFindingMessages()).toEqual([]));

    // Paging therefore starts at 0 — the stale 1 would skip old index 2.
    fireEvent.click(screen.getByTestId("audit-load-more-btn"));
    await waitFor(() =>
      expect(auditApi.run).toHaveBeenLastCalledWith(
        "ws-001",
        expect.objectContaining({ offset: 0 })
      )
    );
    await waitFor(() =>
      expect(mountedFindingMessages()).toEqual(["finding 2", "finding 3"])
    );

    fireEvent.click(screen.getByTestId("audit-load-more-btn"));
    await waitFor(() =>
      expect(auditApi.run).toHaveBeenLastCalledWith(
        "ws-001",
        expect.objectContaining({ offset: 2 })
      )
    );
    // Complete mounted set: the two adopted rows are gone, old 2..5 are
    // mounted exactly once each — nothing was skipped.
    await waitFor(() =>
      expect(mountedFindingMessages()).toEqual([
        "finding 2",
        "finding 3",
        "finding 4",
        "finding 5",
      ])
    );
  });

  // NFA-2 (MEDIUM): a shifted window can hand a mounted row's stale `index` to
  // a *different* finding. Removal by index would then drop both rows; the
  // adopted row must be matched by its identity (`finding_key` + scope).
  it("removes only the adopted row when a shifted window reuses its index (NFA-2)", async () => {
    vi.mocked(auditApi.run).mockImplementation((_wsId, options) => {
      const offset = options?.offset ?? 0;
      if (offset === 0) {
        return Promise.resolve({
          ...windowReport(0, 2),
          findings: [adoptableFindingAt(0), findingAt(1)],
        });
      }
      // After adopting old index 0 the run shrank: the window at cursor 1
      // labels old 2 and old 3 with their current-run positions 1 and 2, so
      // old 2 collides with the still-mounted old 1.
      return Promise.resolve(
        shiftedWindow({
          offset,
          identities: [offset + 1, offset + 2],
          nextOffset: null,
          total: 249,
          blockers: 199,
          warnings: 50,
          adoptable: [offset + 1],
        })
      );
    });
    vi.mocked(auditApi.remediate).mockResolvedValue({
      applied: true,
      finding_resolved: true,
      created_link_id: "link-001",
      proposal: adoptableFindingAt(0).remediation,
    });

    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-adopt-0"));
    fireEvent.click(await screen.findByTestId("audit-adopt-confirm-confirm"));
    await waitFor(() => expect(mountedFindingMessages()).toEqual(["finding 1"]));

    fireEvent.click(screen.getByTestId("audit-load-more-btn"));
    await waitFor(() =>
      expect(mountedFindingMessages()).toEqual(["finding 1", "finding 2", "finding 3"])
    );

    // Both "finding 1" and "finding 2" carry `audit-adopt-1` now; address the
    // new window's row through its identity.
    fireEvent.click(within(findingRow("finding 2")).getByTestId("audit-adopt-1"));
    fireEvent.click(await screen.findByTestId("audit-adopt-confirm-confirm"));

    // Only old 2 was resolved — old 1, which shares the old numeric index, is
    // still mounted.
    await waitFor(() =>
      expect(mountedFindingMessages()).toEqual(["finding 1", "finding 3"])
    );
  });

  // NFA-2 (MEDIUM, waive half): the in-place suppression map was keyed on
  // `index` too, so waiving one of two index-colliding rows marked both.
  it("suppresses only the waived row when a shifted window reuses its index (NFA-2)", async () => {
    vi.mocked(auditApi.run).mockImplementation((_wsId, options) => {
      const offset = options?.offset ?? 0;
      if (offset === 0) {
        return Promise.resolve({
          ...windowReport(0, 2),
          findings: [adoptableFindingAt(0), findingAt(1)],
        });
      }
      return Promise.resolve(
        shiftedWindow({
          offset,
          identities: [offset + 1, offset + 2],
          nextOffset: null,
          total: 249,
          blockers: 199,
          warnings: 50,
        })
      );
    });
    vi.mocked(auditApi.remediate).mockResolvedValue({
      applied: true,
      finding_resolved: true,
      created_link_id: "link-001",
      proposal: adoptableFindingAt(0).remediation,
    });

    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-adopt-0"));
    fireEvent.click(await screen.findByTestId("audit-adopt-confirm-confirm"));
    await waitFor(() => expect(mountedFindingMessages()).toEqual(["finding 1"]));

    fireEvent.click(screen.getByTestId("audit-load-more-btn"));
    await waitFor(() =>
      expect(mountedFindingMessages()).toEqual(["finding 1", "finding 2", "finding 3"])
    );

    fireEvent.click(within(findingRow("finding 2")).getByTestId("audit-waive-1"));
    fireEvent.change(screen.getByTestId("audit-waive-reason"), {
      target: { value: WAIVE_REASON },
    });
    fireEvent.click(screen.getByTestId("audit-waive-confirm"));

    await waitFor(() =>
      expect(within(findingRow("finding 2")).getByTestId("audit-suppressed-badge-1"))
        .toBeInTheDocument()
    );
    // The other row that happened to carry index 1 stays untouched, and only
    // one suppression is visible in total.
    expect(
      within(findingRow("finding 1")).queryByTestId("audit-suppressed-badge-1")
    ).not.toBeInTheDocument();
    expect(screen.getAllByTestId("audit-suppressed-badge-1")).toHaveLength(1);
  });

  // NF-A (waive half): a waive removes nothing, so it must NOT shift the
  // cursor — but "Load more" adopts a fresh snapshot that already counts the
  // suppression. The badges must therefore show the snapshot's suppressed
  // numbers, never snapshot + delta (which would double-count it).
  it("does not double-count a waive when Load more adopts a new snapshot (NF-A)", async () => {
    vi.mocked(auditApi.run)
      .mockResolvedValueOnce({
        ...windowReport(0, 2),
        counts: { total: 250, blockers: 200, warnings: 50, suppressed: 0, suppressed_blockers: 0 },
        page_counts: { total: 2, blockers: 2, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
        truncated: true,
        total_findings_available: 250,
        total_blockers_available: 200,
        total_effective_blockers: 200,
        total_warnings_available: 50,
        next_offset: 2,
        findings: [findingAt(0), findingAt(1)],
      })
      // Fresh snapshot: the same 250 raw findings, one blocker now suppressed
      // (a waiver never changes `total` — nothing is hidden).
      .mockResolvedValueOnce({
        ...windowReport(2, 2),
        counts: { total: 250, blockers: 199, warnings: 50, suppressed: 1, suppressed_blockers: 1 },
        page_counts: { total: 2, blockers: 2, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
        truncated: false,
        total_findings_available: 250,
        total_blockers_available: 199,
        total_effective_blockers: 199,
        total_warnings_available: 50,
        total_suppressed_available: 1,
        total_suppressed_blockers_available: 1,
        next_offset: null,
        findings: [findingAt(2), findingAt(3)],
      });

    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-waive-0"));
    fireEvent.change(screen.getByTestId("audit-waive-reason"), {
      target: { value: WAIVE_REASON },
    });
    fireEvent.click(screen.getByTestId("audit-waive-confirm"));
    await screen.findByTestId("audit-suppressed-badge-0");

    // Local delta on top of the snapshot: 200 -> 199, 0 -> 1 suppressed.
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("199");
    expect(screen.getByTestId("audit-count-suppressed").textContent).toContain("1");
    expect(screen.getByTestId("audit-count-suppressed-blockers").textContent).toContain("1");

    // No row was removed, so the cursor stays on the server's 2.
    fireEvent.click(screen.getByTestId("audit-load-more-btn"));
    await waitFor(() =>
      expect(auditApi.run).toHaveBeenLastCalledWith(
        "ws-001",
        expect.objectContaining({ offset: 2 })
      )
    );
    await waitFor(() =>
      expect(screen.queryByTestId("audit-truncated-banner")).not.toBeInTheDocument()
    );

    // Exactly the snapshot: the delta was reset, not applied a second time.
    expect(screen.getByTestId("audit-count-total").textContent).toContain("250");
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("199");
    expect(screen.getByTestId("audit-count-blockers").textContent).not.toContain("198");
    expect(screen.getByTestId("audit-count-suppressed").textContent).not.toContain("2");
    expect(screen.getByTestId("audit-count-suppressed-blockers").textContent).not.toContain("2");
  });

  // #569/#1383: the append dedupe is keyed on `finding_key` + scope — every
  // window is a fresh run, so `index` shifts once a finding was resolved. A
  // re-reported finding must not be mounted twice under its new position, and
  // a genuinely new finding whose index collides with an old one must survive.
  it("dedupes an appended window by finding_key, not by positional index (#1383)", async () => {
    const [first, second] = PROJECT_REPORT.findings;
    vi.mocked(auditApi.run)
      .mockResolvedValueOnce({
        ...PROJECT_REPORT,
        counts: { total: 3, blockers: 1, warnings: 2, suppressed: 0, suppressed_blockers: 0 },
        page_counts: { total: 2, blockers: 1, warnings: 1, suppressed: 0, suppressed_blockers: 0 },
        truncated: true,
        total_findings_available: 3,
        total_blockers_available: 1,
        total_warnings_available: 2,
        next_offset: 2,
        findings: [first, second],
      })
      .mockResolvedValueOnce({
        ...PROJECT_REPORT,
        counts: { total: 3, blockers: 1, warnings: 2, suppressed: 0, suppressed_blockers: 0 },
        page_counts: { total: 2, blockers: 2, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
        truncated: false,
        total_findings_available: 3,
        total_blockers_available: 1,
        total_warnings_available: 2,
        next_offset: null,
        findings: [
          // Already mounted — same finding, shifted position after the re-run.
          { ...second, index: 7 },
          // Genuinely new, distinct finding.
          { ...first, index: 8, finding_key: "TRACE-P9\x1fartifact-8" },
        ],
      });

    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-load-more-btn"));

    expect(await screen.findByTestId("audit-finding-8")).toBeInTheDocument();
    expect(screen.queryByTestId("audit-finding-7")).not.toBeInTheDocument();
    expect(screen.getAllByText(second.message)).toHaveLength(1);
  });

  // #1383: rolling deploy — a backend that predates `page_counts`/`next_offset`
  // still reports the full run through `total_*_available` and keeps the old
  // (window-scoped) `counts` semantics. That shape must be normalised, not
  // rendered as the run total.
  it("normalises a legacy response without page_counts or next_offset", async () => {
    const { page_counts: _pageCounts, next_offset: _nextOffset, ...legacy } = windowReport(0, 100);
    vi.mocked(auditApi.run).mockResolvedValue({
      ...legacy,
      counts: { total: 100, blockers: 100, warnings: 0, suppressed: 0, suppressed_blockers: 0 },
    });

    render(<AuditDashboard />);

    await screen.findByTestId("audit-load-more-btn");
    expect(screen.getByTestId("audit-count-total").textContent).toContain("250");
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("200");

    fireEvent.click(screen.getByTestId("audit-load-more-btn"));
    await waitFor(() =>
      expect(auditApi.run).toHaveBeenLastCalledWith(
        "ws-001",
        expect.objectContaining({ offset: 100 })
      )
    );
  });

  // #1383: once more than one window is mounted, "window" and "rows on screen"
  // are different numbers; the banner must name all three (window / mounted /
  // run) instead of presenting the mounted rows as the window.
  it("names the window, the run total and the mounted rows once several windows are loaded", async () => {
    render(<AuditDashboard />);

    await screen.findByTestId("audit-load-more-btn");
    fireEvent.click(screen.getByTestId("audit-load-more-btn"));
    await screen.findByTestId("audit-finding-100");

    const banner = screen.getByTestId("audit-truncated-banner");
    expect(banner.textContent).toContain("100"); // page_counts.total — last window
    expect(banner.textContent).toContain("250"); // counts.total — full run
    expect(banner.textContent).toContain("200"); // findings.length — rows mounted
  });

  it("keeps the loaded findings readable when loading the next window fails", async () => {
    render(<AuditDashboard />);

    await screen.findByTestId("audit-load-more-btn");
    vi.mocked(auditApi.run).mockRejectedValueOnce(new Error("network down"));
    fireEvent.click(screen.getByTestId("audit-load-more-btn"));

    const banner = await screen.findByTestId("audit-load-error");
    expect(banner.textContent).toContain("network down");
    // The page the user was working through is still there — a failed
    // "Load more" must not discard it.
    expect(screen.getByTestId("audit-finding-0")).toBeInTheDocument();
    // ...and the failed window stays retryable (a Refresh would jump back to
    // page 1 and throw the loaded pages away).
    expect(screen.getByTestId("audit-load-more-btn")).toBeEnabled();

    fireEvent.click(screen.getByTestId("audit-load-more-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("audit-finding-100")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("audit-load-error")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// #569 — finding suppression (waivers): the third action, the "show suppressed"
// filter, the suppressed badge, and the *critical* invariant that a waive
// failure never falls through into the Adopt -> Modify flip (422 belongs to
// `remediate` alone; the waive endpoints never emit it).
// ---------------------------------------------------------------------------

describe("AuditDashboard — waivers (#569)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  it("suppresses a finding via the waive dialog", async () => {
    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-waive-0"));
    const confirm = await screen.findByTestId("audit-waive-confirm");

    // "No silent suppression": a justification is mandatory in the UI — the
    // confirm button stays disabled until one is typed.
    expect(confirm).toBeDisabled();
    fireEvent.change(screen.getByTestId("audit-waive-reason"), {
      target: { value: WAIVE_REASON },
    });
    expect(confirm).not.toBeDisabled();
    fireEvent.click(confirm);

    // The finding is marked in-place (never removed) with its justification.
    const badge = await screen.findByTestId("audit-suppressed-badge-0");
    expect(badge.textContent).toContain(WAIVE_REASON);
    expect(screen.getByTestId("audit-suppression-reason-0").textContent).toContain(
      WAIVE_REASON
    );
    expect(screen.getByTestId("audit-count-suppressed").textContent).toContain("1");
    expect(screen.getByTestId("audit-toast")).toBeInTheDocument();

    // The Waive action is gone once the finding carries a suppression.
    expect(screen.queryByTestId("audit-waive-0")).not.toBeInTheDocument();

    // C1: the finding's own scope travels with the request so the server's
    // existence check runs over the same scope the finding was reported in.
    expect(auditApi.waive).toHaveBeenCalledWith("ws-001", {
      rule_id: "TRACE-P1",
      artifact_ids: ["11111111-1111-1111-1111-111111111111"],
      reason: WAIVE_REASON,
      scope: "project",
    });
  });

  // #1150/#1382: the server's `counts.blockers` is effective (waiver-aware), so
  // a local waive must shrink the blocker badge — not only the additive
  // "suppressed" counters. Before the fix the badge kept claiming the waived
  // blocker still blocked a baseline.
  it("shrinks the blocker badge when a blocker is waived (#1150/#1382)", async () => {
    render(<AuditDashboard />);

    await screen.findByTestId("audit-finding-0");
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("1");

    fireEvent.click(screen.getByTestId("audit-waive-0"));
    fireEvent.change(screen.getByTestId("audit-waive-reason"), {
      target: { value: WAIVE_REASON },
    });
    fireEvent.click(screen.getByTestId("audit-waive-confirm"));

    await screen.findByTestId("audit-suppressed-badge-0");
    expect(screen.getByTestId("audit-count-blockers").textContent).toContain("0");
    // Still counted additively, so the decision stays visible.
    expect(screen.getByTestId("audit-count-suppressed").textContent).toContain("1");
    expect(screen.getByTestId("audit-count-suppressed-blockers").textContent).toContain("1");
  });

  it("hides suppressed findings when the filter is off and restores them when on", async () => {
    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-waive-0"));
    fireEvent.change(screen.getByTestId("audit-waive-reason"), {
      target: { value: WAIVE_REASON },
    });
    fireEvent.click(screen.getByTestId("audit-waive-confirm"));
    await screen.findByTestId("audit-suppressed-badge-0");

    const filter = screen.getByTestId("audit-show-suppressed") as HTMLInputElement;
    // Default ON — nothing is hidden by default (O3).
    expect(filter.checked).toBe(true);

    fireEvent.click(filter);
    await waitFor(() =>
      expect(screen.queryByTestId("audit-finding-0")).not.toBeInTheDocument()
    );
    // Only the suppressed row disappears; the other finding is untouched.
    expect(screen.getByTestId("audit-finding-1")).toBeInTheDocument();

    fireEvent.click(filter);
    expect(await screen.findByTestId("audit-finding-0")).toBeInTheDocument();
  });

  // THE critical behavioural requirement of #569: a rejected justification
  // (400 WAIVER_REASON_REJECTED) must surface as a reason-specific message and
  // MUST NOT be routed into the Modify flip. That flip is triggered by a 422,
  // which is reserved for POST .../audit/remediate/ — the waive paths never
  // emit it (spec E18). If a future refactor routed waive failures through the
  // same `instanceof UnprocessableEntityError` branch as Adopt, this test goes
  // red: `audit-modify-0` would appear and `audit-adopt-0` would vanish.
  it("shows a reason-specific error and never flips the finding into Modify when a waive is rejected", async () => {
    vi.mocked(auditApi.waive).mockRejectedValue({
      error: {
        code: "WAIVER_REASON_REJECTED",
        message: "Justification is a placeholder.",
        details: [],
      },
    });

    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-waive-0"));
    fireEvent.change(screen.getByTestId("audit-waive-reason"), {
      target: { value: "because" },
    });
    fireEvent.click(screen.getByTestId("audit-waive-confirm"));

    const error = await screen.findByTestId("audit-waive-error");
    expect(error.textContent).toContain(
      "The justification does not satisfy the policy."
    );

    // The finding keeps its Adopt action and never gains a Modify action.
    expect(screen.getByTestId("audit-adopt-0")).toBeInTheDocument();
    expect(screen.queryByTestId("audit-modify-0")).not.toBeInTheDocument();
    // No suppression was recorded, and the generic per-finding error channel
    // used by the Adopt flip stays empty (the message lives in the dialog).
    expect(screen.queryByTestId("audit-suppressed-badge-0")).not.toBeInTheDocument();
    expect(screen.queryByTestId("audit-finding-error-0")).not.toBeInTheDocument();
  });

  it("shows the dedicated SUPPRESSION_EXPIRED message instead of a generic error", async () => {
    vi.mocked(auditApi.waive).mockRejectedValue({
      error: { code: "SUPPRESSION_EXPIRED", message: "expired", details: [] },
    });

    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-waive-0"));
    fireEvent.change(screen.getByTestId("audit-waive-reason"), {
      target: { value: WAIVE_REASON },
    });
    fireEvent.click(screen.getByTestId("audit-waive-confirm"));

    const error = await screen.findByTestId("audit-waive-error");
    expect(error.textContent).toContain("An expired suppression already exists");
    // Still no Modify flip.
    expect(screen.queryByTestId("audit-modify-0")).not.toBeInTheDocument();
  });

  it("shows the dedicated WAIVER_FINDING_NOT_BLOCKING message", async () => {
    vi.mocked(auditApi.waive).mockRejectedValue({
      error: { code: "WAIVER_FINDING_NOT_BLOCKING", message: "warning", details: [] },
    });

    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-waive-0"));
    fireEvent.change(screen.getByTestId("audit-waive-reason"), {
      target: { value: WAIVE_REASON },
    });
    fireEvent.click(screen.getByTestId("audit-waive-confirm"));

    const error = await screen.findByTestId("audit-waive-error");
    expect(error.textContent).toContain("not a blocker right now");
  });

  it("lists suppressions with a visually distinct badge for expired vs active", async () => {
    vi.mocked(auditApi.waivers).mockResolvedValue({
      waivers: [
        { ...WAIVER_VIEW, waiver_id: "w-active", state: "active" },
        {
          ...WAIVER_VIEW,
          waiver_id: "w-expired",
          state: "expired",
          expires_at: "2026-01-01T00:00:00Z",
        },
      ],
      counts: { active: 1, expired: 1 },
    });

    render(<AuditDashboard />);

    expect(await screen.findByTestId("audit-waivers")).toBeInTheDocument();
    expect(screen.getByTestId("audit-waiver-state-w-active").textContent).toMatch(
      /active/i
    );
    expect(screen.getByTestId("audit-waiver-state-w-expired").textContent).toMatch(
      /expired/i
    );
    // Visually distinguishable: the two lifecycle states do not share the same
    // badge styling (active = neutral, expired = warning).
    expect(screen.getByTestId("audit-waiver-state-w-active").getAttribute("style")).not.toBe(
      screen.getByTestId("audit-waiver-state-w-expired").getAttribute("style")
    );
  });
});

// ---------------------------------------------------------------------------
// #569 UI review — the three minor findings fixed on the branch.
// ---------------------------------------------------------------------------

describe("AuditDashboard — waiver UI review fixes (#569)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    setupDefaultMocks();
  });

  // UI-569-01: `apiFetch` intercepts 403 and throws `ForbiddenError`, a plain
  // Error subclass with no `.error` — so a real 403 (no Admin/Approver role, or
  // an AUTHOR-tier API key) used to resolve to code `null` and the dedicated
  // forbidden message was unreachable. Deriving the code from the typed error
  // must render `audit.waiveForbidden`, not the generic fallback.
  it("renders the dedicated forbidden message when the waive is rejected with 403", async () => {
    vi.mocked(auditApi.waive).mockRejectedValue(new ForbiddenError("Forbidden."));

    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-waive-0"));
    fireEvent.change(screen.getByTestId("audit-waive-reason"), {
      target: { value: WAIVE_REASON },
    });
    fireEvent.click(screen.getByTestId("audit-waive-confirm"));

    const error = await screen.findByTestId("audit-waive-error");
    expect(error.textContent).toContain("You are not allowed to suppress findings");
    // Not the generic/raw transport message...
    expect(error.textContent).not.toContain("Forbidden.");
    // ...and still never the Modify flip (422 belongs to `remediate` alone).
    expect(screen.getByTestId("audit-adopt-0")).toBeInTheDocument();
    expect(screen.queryByTestId("audit-modify-0")).not.toBeInTheDocument();
  });

  // UI-569-02: the suppression panel is an independent request. Zero rows must
  // render the already-defined empty key, not nothing at all.
  it("renders the suppression panel's empty state instead of hiding the panel", async () => {
    render(<AuditDashboard />);

    const empty = await screen.findByTestId("audit-waivers-empty");
    expect(empty.textContent).toContain("No suppressions on file.");
    expect(screen.queryByTestId("audit-waivers-error")).not.toBeInTheDocument();
    expect(screen.queryByTestId("audit-waivers-loading")).not.toBeInTheDocument();
  });

  // UI-569-02: a failed/forbidden read must be distinguishable from "no
  // suppressions on file".
  it("renders a distinct error state when the suppression list request fails", async () => {
    vi.mocked(auditApi.waivers).mockRejectedValue(new Error("waivers unavailable"));

    render(<AuditDashboard />);

    const error = await screen.findByTestId("audit-waivers-error");
    expect(error.textContent).toContain("waivers unavailable");
    expect(screen.queryByTestId("audit-waivers-empty")).not.toBeInTheDocument();
  });

  it("renders a loading state while the suppression list request is in flight", async () => {
    vi.mocked(auditApi.waivers).mockReturnValue(new Promise<never>(() => {}));

    render(<AuditDashboard />);

    expect(await screen.findByTestId("audit-waivers-loading")).toBeInTheDocument();
    expect(screen.queryByTestId("audit-waivers-empty")).not.toBeInTheDocument();
  });

  // UI-569-03: a successful waive unmounts the Waive trigger, so the dialog's
  // focus trap (which only restores to a connected element) cannot return
  // focus to it. Focus must land on the still-mounted finding row instead of
  // falling to `<body>`.
  it("moves focus onto the finding row after a successful waive", async () => {
    render(<AuditDashboard />);

    fireEvent.click(await screen.findByTestId("audit-waive-0"));
    fireEvent.change(screen.getByTestId("audit-waive-reason"), {
      target: { value: WAIVE_REASON },
    });
    fireEvent.click(screen.getByTestId("audit-waive-confirm"));

    await screen.findByTestId("audit-suppressed-badge-0");
    await waitFor(() => {
      expect(document.activeElement).toBe(screen.getByTestId("audit-finding-0"));
    });
  });
});
