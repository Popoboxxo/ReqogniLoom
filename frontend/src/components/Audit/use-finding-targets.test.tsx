/**
 * use-finding-targets.test.tsx
 *
 * Unit tests for the SE-Auditor "Modify" target resolution (GitHub #451).
 *
 * Covers the three contract details of GET /traceability/resolve/ the hook
 * exists to absorb:
 *   - batches larger than RESOLVE_BATCH_LIMIT are chunked (the endpoint answers
 *     400 above the cap, and `traceabilityApi.resolve` silently truncates)
 *   - `resolved: false` is a normal answer -> no editor target, no retry
 *   - a failed request degrades to "no target" instead of looping
 * plus the caching guarantee (adopting one finding must not re-resolve the rest)
 * and `primaryTarget`'s "first resolvable id wins" rule.
 */

import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { primaryTarget, useFindingTargets } from "./use-finding-targets";
import { traceabilityApi } from "../../api/traceability";
import { RESOLVE_BATCH_LIMIT } from "../../api/tracelinks";
import type { AuditFinding } from "../../api/audit";
import type { ResolvedArtifact } from "../../api/tracelinks";

vi.mock("../../api/traceability");

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeFinding(index: number, artifactIds: string[]): AuditFinding {
  return {
    rule_id: "TRACE-P1",
    severity: "blocker",
    message: `finding ${index}`,
    artifact_ids: artifactIds,
    scope: "project",
    scope_artifact_id: null,
    index,
    remediation: {
      rule_id: "TRACE-P1",
      automatic: false,
      reason: "manual",
      finding_artifact_ids: artifactIds,
      action_kind: null,
      params: {},
    },
  };
}

/** Resolve every id to a Requirement whose entity id is `<id>-entity`. */
function resolveAll(ids: string[]): Promise<ResolvedArtifact[]> {
  return Promise.resolve(
    ids.map((id) => ({
      artifact_id: id,
      resolved: true,
      entity_type: "Requirement",
      entity_id: `${id}-entity`,
    }))
  );
}

describe("useFindingTargets (GitHub #451)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("maps a resolvable artifact id onto its editor route", async () => {
    vi.mocked(traceabilityApi.resolve).mockImplementation((ids) => resolveAll(ids));

    const findings = [makeFinding(0, ["req-1"])];
    const { result } = renderHook(() => useFindingTargets(findings));

    await waitFor(() => expect(result.current["req-1"]).toBeTruthy());
    expect(result.current["req-1"]).toEqual({
      artifactId: "req-1",
      entityType: "Requirement",
      route: "/requirements/req-1-entity",
    });
  });

  it("chunks the id set so no request exceeds the endpoint's batch cap", async () => {
    vi.mocked(traceabilityApi.resolve).mockImplementation((ids) => resolveAll(ids));

    const ids = Array.from({ length: RESOLVE_BATCH_LIMIT + 5 }, (_, i) => `req-${i}`);
    const findings = ids.map((id, i) => makeFinding(i, [id]));
    const { result } = renderHook(() => useFindingTargets(findings));

    await waitFor(() =>
      expect(Object.keys(result.current)).toHaveLength(ids.length)
    );
    expect(traceabilityApi.resolve).toHaveBeenCalledTimes(2);
    for (const call of vi.mocked(traceabilityApi.resolve).mock.calls) {
      expect(call[0].length).toBeLessThanOrEqual(RESOLVE_BATCH_LIMIT);
    }
  });

  it("caches results: a re-render with fewer findings issues no new request", async () => {
    vi.mocked(traceabilityApi.resolve).mockImplementation((ids) => resolveAll(ids));

    const findings = [makeFinding(0, ["req-1"]), makeFinding(1, ["req-2"])];
    const { result, rerender } = renderHook(
      ({ list }: { list: AuditFinding[] }) => useFindingTargets(list),
      { initialProps: { list: findings } }
    );

    await waitFor(() => expect(result.current["req-2"]).toBeTruthy());
    expect(traceabilityApi.resolve).toHaveBeenCalledTimes(1);

    // Mirrors a successful Adopt: the array identity changes, the id set shrinks.
    rerender({ list: [findings[1]] });
    expect(traceabilityApi.resolve).toHaveBeenCalledTimes(1);
  });

  it("treats resolved:false as 'no editor target' without retrying", async () => {
    vi.mocked(traceabilityApi.resolve).mockImplementation((ids) =>
      Promise.resolve(
        ids.map((id) => ({
          artifact_id: id,
          resolved: false,
          entity_type: null,
          entity_id: null,
        }))
      )
    );

    const findings = [makeFinding(0, ["dangling"])];
    const { result, rerender } = renderHook(
      ({ list }: { list: AuditFinding[] }) => useFindingTargets(list),
      { initialProps: { list: findings } }
    );

    await waitFor(() => expect("dangling" in result.current).toBe(true));
    expect(result.current["dangling"]).toBeNull();

    rerender({ list: [makeFinding(0, ["dangling"])] });
    expect(traceabilityApi.resolve).toHaveBeenCalledTimes(1);
  });

  it("degrades to 'no target' when the resolve request fails", async () => {
    vi.mocked(traceabilityApi.resolve).mockRejectedValue(new Error("boom"));

    const findings = [makeFinding(0, ["req-1"])];
    const { result } = renderHook(() => useFindingTargets(findings));

    await waitFor(() => expect("req-1" in result.current).toBe(true));
    expect(result.current["req-1"]).toBeNull();
  });
});

describe("primaryTarget", () => {
  it("returns the first resolvable artifact id of the finding", () => {
    // ARCH-003 reports (requirement, child element, parent element) — the
    // subject is the first id, so it wins whenever it resolves.
    const finding = makeFinding(0, ["subject", "child", "parent"]);
    const targets = {
      subject: { artifactId: "subject", entityType: "Requirement", route: "/requirements/s" },
      child: { artifactId: "child", entityType: "ArchitectureElement", route: "/architecture/c" },
    };

    expect(primaryTarget(finding, targets)?.artifactId).toBe("subject");
  });

  it("falls back to a later id when the subject does not resolve", () => {
    const finding = makeFinding(0, ["subject", "child"]);
    const targets = {
      subject: null,
      child: { artifactId: "child", entityType: "ArchitectureElement", route: "/architecture/c" },
    };

    expect(primaryTarget(finding, targets)?.artifactId).toBe("child");
  });

  it("returns null when nothing resolves", () => {
    expect(primaryTarget(makeFinding(0, ["a"]), { a: null })).toBeNull();
    expect(primaryTarget(makeFinding(0, []), {})).toBeNull();
  });
});
