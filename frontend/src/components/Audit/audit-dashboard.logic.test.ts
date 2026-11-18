/**
 * audit-dashboard.logic.test.ts
 *
 * Behaviour characterisation for the pure selectors extracted from
 * `audit-dashboard.tsx` (S3.2 WP-5). These are the rules the component's
 * badges, filters and rule groups already relied on — the bodies were moved
 * verbatim, so the assertions describe the pre-extraction behaviour.
 */

import { describe, it, expect } from "vitest";
import { ForbiddenError } from "../../api/errors";
import type { AuditCounts, AuditFinding } from "../../api/audit";
import type { Artifact } from "../../types";
import {
  ARTIFACT_TYPE_OPTIONS,
  EMPTY_COUNTS,
  SCOPES,
  artifactLabel,
  buildRuleOptions,
  computeCounts,
  decrement,
  filterFindings,
  formatExpiry,
  groupFindingsByRule,
  waiverErrorCode,
} from "./audit-dashboard.logic";

function finding(overrides: Partial<AuditFinding> = {}): AuditFinding {
  return {
    rule_id: "TRACE-P1",
    severity: "blocker",
    message: "finding",
    artifact_ids: ["11111111-1111"],
    scope: "project",
    scope_artifact_id: null,
    index: 0,
    finding_key: "TRACE-P1\x1f11111111-1111",
    suppressed: false,
    suppressed_until: null,
    suppression_reason: null,
    suppression_id: null,
    remediation: {
      rule_id: "TRACE-P1",
      automatic: true,
      reason: "auto",
      finding_artifact_ids: ["11111111-1111"],
      action_kind: "create_trace_link",
      params: {},
    },
    ...overrides,
  };
}

function counts(overrides: Partial<AuditCounts> = {}): AuditCounts {
  return {
    total: 10,
    blockers: 6,
    warnings: 4,
    suppressed: 2,
    suppressed_blockers: 1,
    ...overrides,
  };
}

describe("audit dashboard constants", () => {
  it("keeps the scope order project → document → global", () => {
    expect(SCOPES).toEqual(["project", "document", "global"]);
  });

  it("offers only artifact types that can carry findings", () => {
    expect(ARTIFACT_TYPE_OPTIONS).toEqual([
      "Requirement",
      "ArchitectureElement",
      "Icd",
      "TestCase",
      "StakeholderNeed",
      "Goal",
    ]);
  });

  it("has an all-zero pre-run snapshot", () => {
    expect(EMPTY_COUNTS).toEqual({
      total: 0,
      blockers: 0,
      warnings: 0,
      suppressed: 0,
      suppressed_blockers: 0,
    });
  });
});

describe("display helpers", () => {
  it("prefers title, then name, then a truncated id for artifact labels", () => {
    const base = { id: "1234567890abcdef", artifact_type: "Requirement" } as Artifact;
    expect(artifactLabel({ ...base, title: "Sys req" } as Artifact)).toBe(
      "Requirement — Sys req"
    );
    expect(artifactLabel({ ...base, name: "Fallback" } as Artifact)).toBe(
      "Requirement — Fallback"
    );
    expect(artifactLabel(base)).toBe("Requirement — 12345678…");
  });

  it("maps ForbiddenError and API error bodies onto the same stable code", () => {
    expect(waiverErrorCode(new ForbiddenError("no"))).toBe("PERMISSION_DENIED");
    expect(waiverErrorCode({ error: { code: "WAIVER_REASON_REJECTED" } })).toBe(
      "WAIVER_REASON_REJECTED"
    );
    expect(waiverErrorCode(null)).toBeNull();
    expect(waiverErrorCode(new Error("plain"))).toBeNull();
  });

  it("formats an ISO expiry and degrades to the raw string on invalid input", () => {
    expect(formatExpiry("2026-05-04T00:00:00.000Z")).toBe(
      new Date("2026-05-04T00:00:00.000Z").toLocaleDateString()
    );
    expect(formatExpiry("not-a-date")).toBe("not-a-date");
  });

  it("never lets a local correction drive counts below zero", () => {
    expect(decrement(3, 5)).toBe(0);
    expect(decrement(3, 1)).toBe(2);
  });
});

describe("filterFindings", () => {
  const rows = [
    finding({ rule_id: "B", severity: "blocker", index: 0 }),
    finding({ rule_id: "A", severity: "warning", index: 1 }),
    finding({ rule_id: "B", severity: "blocker", suppressed: true, index: 2 }),
  ];

  it("returns the mounted rows unchanged for the default filters", () => {
    expect(filterFindings(rows, "all", "all", true)).toBe(rows);
  });

  it("narrows by severity, then rule, then suppression", () => {
    expect(filterFindings(rows, "blocker", "all", true).map((f) => f.index)).toEqual([0, 2]);
    expect(filterFindings(rows, "all", "B", true).map((f) => f.index)).toEqual([0, 2]);
    expect(filterFindings(rows, "all", "all", false).map((f) => f.index)).toEqual([0, 1]);
    expect(filterFindings(rows, "blocker", "B", false).map((f) => f.index)).toEqual([0]);
  });
});

describe("buildRuleOptions", () => {
  it("counts mounted rows per rule and orders by rule id", () => {
    const options = buildRuleOptions([
      finding({ rule_id: "Z" }),
      finding({ rule_id: "A" }),
      finding({ rule_id: "Z" }),
    ]);
    expect(options).toEqual([
      ["A", 1],
      ["Z", 2],
    ]);
  });
});

describe("computeCounts", () => {
  it("returns the zero snapshot before a report arrives", () => {
    expect(computeCounts(null, [], [])).toBe(EMPTY_COUNTS);
  });

  it("leaves the server snapshot untouched with no local actions", () => {
    expect(computeCounts(counts(), [], [])).toEqual(counts());
  });

  it("shrinks total/blockers/warnings for an adopted finding", () => {
    const adopted = finding({ severity: "blocker" });
    expect(
      computeCounts(counts(), [adopted], [])
    ).toEqual(counts({ total: 9, blockers: 5, warnings: 4 }));
  });

  it("shrinks warnings for an adopted non-blocker", () => {
    const adopted = finding({ severity: "warning" });
    expect(
      computeCounts(counts(), [adopted], [])
    ).toEqual(counts({ total: 9, blockers: 6, warnings: 3 }));
  });

  it("excludes a waived blocker from the effective count but adds it to suppressions", () => {
    const waived = finding({ severity: "blocker" });
    expect(computeCounts(counts(), [], [waived])).toEqual(
      counts({ blockers: 5, suppressed: 3, suppressed_blockers: 2 })
    );
  });

  it("clamps suppression counters at zero when a local action outruns the snapshot", () => {
    const adoptedSuppressedBlocker = finding({
      severity: "blocker",
      suppressed: true,
    });
    expect(
      computeCounts(counts({ suppressed: 0, suppressed_blockers: 0 }), [], [])
    ).toEqual(counts({ suppressed: 0, suppressed_blockers: 0 }));
    expect(
      computeCounts(
        counts({ suppressed: 0, suppressed_blockers: 0 }),
        [adoptedSuppressedBlocker],
        []
      )
    ).toEqual(
      counts({ total: 9, blockers: 5, suppressed: 0, suppressed_blockers: 0 })
    );
  });
});

describe("groupFindingsByRule", () => {
  it("groups rows by rule id and orders groups by rule id", () => {
    const rows = [
      finding({ rule_id: "Z", index: 0 }),
      finding({ rule_id: "A", index: 1 }),
      finding({ rule_id: "Z", index: 2 }),
    ];
    const grouped = groupFindingsByRule(rows);
    expect(grouped.map(([rule]) => rule)).toEqual(["A", "Z"]);
    expect(grouped.find(([rule]) => rule === "Z")?.[1].map((f) => f.index)).toEqual([0, 2]);
  });

  it("returns no groups for an empty view", () => {
    expect(groupFindingsByRule([])).toEqual([]);
  });
});
