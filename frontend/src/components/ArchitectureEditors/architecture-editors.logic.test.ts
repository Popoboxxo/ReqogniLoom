/**
 * architecture-editors.logic.test.ts
 *
 * Behaviour characterisation for the pure view helpers extracted from
 * `ArchitectureEditors.tsx` (S3.2 WP-5). The bodies were moved verbatim, so
 * these assertions describe the pre-extraction list filter, tree mapping,
 * summary, id translation, version anchor and AI-action set.
 */

import { describe, it, expect, vi } from "vitest";
import type { TFunction } from "i18next";
import type { ArchitectureElement } from "../../types";
import {
  ARCH_LIFECYCLE_STATUSES,
  buildAiActions,
  buildArchSummary,
  buildArtifactIdMap,
  buildCurrentVersion,
  buildElementIdByArtifactId,
  buildTreeNodes,
  filterElements,
  resolveArtifactId,
} from "./architecture-editors.logic";

const t = ((key: string, opts?: Record<string, unknown>) =>
  opts?.defaultValue !== undefined
    ? String(opts.defaultValue).replace("{{count}}", String(opts.count))
    : key) as unknown as TFunction;

function element(overrides: Partial<ArchitectureElement> = {}): ArchitectureElement {
  return {
    id: "el-1",
    artifact_id: "art-1",
    workspace_id: "ws-1",
    title: "Subsystem A",
    description: "",
    element_type: "subsystem",
    parent_id: null,
    level: 1,
    version: 3,
    uid: "SYS-001",
    lifecycle_status: "active",
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-02-01T00:00:00Z",
    ...overrides,
  } as ArchitectureElement;
}

describe("ARCH_LIFECYCLE_STATUSES", () => {
  it("offers active/outdated/deprecated but never deleted", () => {
    expect(ARCH_LIFECYCLE_STATUSES).toEqual(['active', 'outdated', 'deprecated']);
  });
});

describe("filterElements", () => {
  const rows = [
    element({ id: "a", title: "Alpha", uid: "SYS-001", lifecycle_status: "active" }),
    element({ id: "b", title: "Beta", uid: "SYS-002", lifecycle_status: "outdated" }),
    element({ id: "c", title: "Gamma", uid: null, lifecycle_status: undefined }),
  ];

  it("returns all rows when no filter is active", () => {
    expect(filterElements(rows, "", "")).toEqual(rows);
  });

  it("treats a missing lifecycle status as active", () => {
    expect(filterElements(rows, "", "active").map((e) => e.id)).toEqual(["a", "c"]);
    expect(filterElements(rows, "", "outdated").map((e) => e.id)).toEqual(["b"]);
  });

  it("searches title and uid case-insensitively", () => {
    expect(filterElements(rows, "  ALPHA ", "").map((e) => e.id)).toEqual(["a"]);
    expect(filterElements(rows, "sys-002", "").map((e) => e.id)).toEqual(["b"]);
    expect(filterElements(rows, "missing", "")).toEqual([]);
  });

  it("applies status and search together", () => {
    expect(filterElements(rows, "sys-", "active").map((e) => e.id)).toEqual(["a"]);
  });
});

describe("buildTreeNodes", () => {
  it("maps domain rows to tree nodes and marks workflow-locked rows", () => {
    const nodes = buildTreeNodes(
      [
        element({ id: "a", title: "", uid: "SYS-001", level: 2, lifecycle_status: "outdated" }),
        element({ id: "b", title: "Unlocked", parent_id: "a", level: undefined, uid: null }),
      ],
      { a: "frozen" },
      t,
    );
    expect(nodes[0]).toMatchObject({
      id: "a",
      name: "editor.untitled",
      identifier: "SYS-001",
      parentId: null,
      level: "L2",
      outdated: true,
      locked: { state: "frozen" },
    });
    expect(nodes[1]).toMatchObject({
      parentId: "a",
      level: "L0",
      outdated: false,
      locked: null,
    });
  });
});

describe("buildArchSummary", () => {
  it("counts absent lifecycle status as active", () => {
    const summary = buildArchSummary(
      [
        element({ lifecycle_status: "active" }),
        element({ lifecycle_status: undefined }),
        element({ lifecycle_status: "deprecated" }),
      ],
      t,
    );
    expect(summary).toBe("3 · 2 active");
  });
});

describe("id maps", () => {
  it("maps element ids to artifact ids with an identity fallback", () => {
    const map = buildArtifactIdMap([
      element({ id: "a", artifact_id: "art-1" }),
      element({ id: "b", artifact_id: undefined }),
    ]);
    expect(map.get("a")).toBe("art-1");
    expect(map.get("b")).toBe("b");
  });

  it("maps artifact ids and element ids to the element id", () => {
    const map = buildElementIdByArtifactId([
      element({ id: "a", artifact_id: "art-1" }),
    ]);
    expect(map.get("art-1")).toBe("a");
    expect(map.get("a")).toBe("a");
  });

  it("keeps null parent as null and falls back for unmapped nodes", () => {
    const map = new Map([["a", "art-1"]]);
    expect(resolveArtifactId(map, null)).toBeNull();
    expect(resolveArtifactId(map, "a")).toBe("art-1");
    expect(resolveArtifactId(map, "unknown")).toBe("unknown");
  });
});

describe("buildCurrentVersion", () => {
  it("uses updated_at with created_at fallback and returns nothing without an element", () => {
    expect(buildCurrentVersion(undefined)).toBeUndefined();
    expect(
      buildCurrentVersion(element({ version: 7, updated_at: undefined })),
    ).toEqual({
      version: 7,
      label: "v7",
      createdAt: "2026-01-01T00:00:00Z",
      baselineIds: [],
    });
  });
});

describe("buildAiActions", () => {
  it("is empty without a selected element", () => {
    expect(buildAiActions(null, t, vi.fn(), vi.fn(), false)).toEqual([]);
  });

  it("exposes decompose and risk actions with stable test ids", () => {
    const decompose = vi.fn();
    const risk = vi.fn();
    const actions = buildAiActions(element(), t, decompose, risk, true);
    expect(actions.map((a) => a.testId)).toEqual([
      "arch-decompose-btn",
      "arch-derive-risks-btn",
    ]);
    expect(actions[1].disabled).toBe(true);
    actions[0].onClick();
    actions[1].onClick();
    expect(decompose).toHaveBeenCalledOnce();
    expect(risk).toHaveBeenCalledOnce();
  });
});
