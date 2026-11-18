/**
 * requirement-editors.logic.test.ts
 *
 * Behaviour characterisation for the pure view helpers extracted from
 * `RequirementEditors.tsx` (S3.2 WP-5). Bodies were moved verbatim, so these
 * assertions describe the pre-extraction id translation, version anchor and
 * role-gated AI-action set.
 */

import { describe, it, expect, vi } from "vitest";
import type { TFunction } from "i18next";
import type { Requirement } from "../../types";
import {
  buildAiActions,
  buildArtifactIdMap,
  buildCurrentVersion,
  resolveArtifactId,
} from "./requirement-editors.logic";

const t = ((key: string, fallback?: string) => fallback ?? key) as unknown as TFunction;

function requirement(overrides: Partial<Requirement> = {}): Requirement {
  return {
    id: "req-1",
    artifact_id: "art-1",
    workspace_id: "ws-1",
    title: "The system shall …",
    description: "",
    category: "functional",
    status: "draft",
    version: 2,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-02-01T00:00:00Z",
    ...overrides,
  } as Requirement;
}

describe("buildArtifactIdMap / resolveArtifactId", () => {
  it("maps requirement ids to artifact ids with an identity fallback", () => {
    const map = buildArtifactIdMap([
      requirement({ id: "a", artifact_id: "art-a" }),
      requirement({ id: "b", artifact_id: undefined }),
    ]);
    expect(resolveArtifactId(map, "a")).toBe("art-a");
    expect(resolveArtifactId(map, "b")).toBe("b");
    expect(resolveArtifactId(map, "unknown")).toBe("unknown");
    expect(resolveArtifactId(map, null)).toBeNull();
  });
});

describe("buildCurrentVersion", () => {
  it("anchors the inspector on the latest timestamp and handles no selection", () => {
    expect(buildCurrentVersion(null)).toBeUndefined();
    expect(
      buildCurrentVersion(requirement({ version: 5, updated_at: "2026-03-01T00:00:00Z" })),
    ).toEqual({
      version: 5,
      label: "v5",
      createdAt: "2026-03-01T00:00:00Z",
      baselineIds: [],
    });
    expect(buildCurrentVersion(requirement({ updated_at: undefined }))?.createdAt).toBe(
      "2026-01-01T00:00:00Z",
    );
  });
});

describe("buildAiActions", () => {
  it("is empty for a viewer (role gate hides the triggers from the DOM)", () => {
    expect(buildAiActions(false, t, vi.fn(), false, vi.fn())).toEqual([]);
  });

  it("exposes both AI actions with stable test ids and derives/busy wiring", () => {
    const derive = vi.fn();
    const testcase = vi.fn();
    const actions = buildAiActions(true, t, derive, true, testcase);
    expect(actions.map((a) => a.testId)).toEqual([
      "req-ai-derive-btn",
      "req-derive-testcase-btn",
    ]);
    expect(actions[0].disabled).toBe(true);
    expect(actions[0].busyLabel).toBeDefined();
    actions[0].onClick();
    actions[1].onClick();
    expect(derive).toHaveBeenCalledOnce();
    expect(testcase).toHaveBeenCalledOnce();
  });
});
