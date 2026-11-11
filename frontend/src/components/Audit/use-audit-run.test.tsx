/**
 * useAuditRun — stale-response guard (#598 S2).
 *
 * The dashboard starts a fresh run whenever the audit context changes (scope,
 * document root, artifact-type filter). Two requests can therefore be in flight
 * at once; only the newest may write its findings. This file pins that rule at
 * the hook boundary, because the rendered dashboard cannot deterministically
 * interleave the two responses.
 */

import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import type { TFunction } from "i18next";

import { useAuditRun } from "./use-audit-run";
import { auditApi } from "../../api/audit";
import type { AuditFinding, AuditReport } from "../../api/audit";

vi.mock("../../api/audit");

const t = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction;

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

describe("useAuditRun", () => {
  beforeEach(() => vi.clearAllMocks());

  it("ignores a superseded run that resolves after the newer one", async () => {
    let resolveFirst: (value: AuditReport) => void = () => {};
    const firstRun = new Promise<AuditReport>((resolve) => {
      resolveFirst = resolve;
    });

    vi.mocked(auditApi.run)
      .mockImplementationOnce(() => firstRun)
      .mockResolvedValueOnce(report([finding("TRACE-P9", "FRESH", 0)]));

    const { result, rerender } = renderHook(
      (props: { scope: "project" | "global" }) =>
        useAuditRun({
          workspaceId: "ws-1",
          scope: props.scope,
          scopeArtifactId: "",
          artifactTypeFilter: "all",
          t,
        }),
      { initialProps: { scope: "project" as "project" | "global" } }
    );

    // Context switch while the first request is still in flight.
    rerender({ scope: "global" });

    await waitFor(() => expect(result.current.findings[0]?.message).toBe("FRESH"));

    // The superseded response lands afterwards and must be discarded. Resolve
    // it inside `act` so any resulting state update is flushed before the
    // assertion (an unflushed update would let the test pass by accident).
    await act(async () => {
      resolveFirst(report([finding("TRACE-P1", "STALE", 0)]));
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(result.current.findings[0]?.message).toBe("FRESH");
    expect(result.current.findings).toHaveLength(1);
  });
});
