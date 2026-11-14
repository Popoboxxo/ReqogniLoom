/**
 * inspectorContract — the pure contract of the tabbed shell (#1762, M1-1).
 *
 * Pins the type matrix (spec §3) and the id/testid/storage inventory
 * (spec §7, §8.4) without mounting anything. If one of these fails, the shell,
 * its rail and its tests are no longer talking about the same names.
 */

import { describe, expect, it } from "vitest";

import {
  GOALS_TAB_STORAGE_KEY,
  HAS_LINKS_TAB,
  HAS_SPINE,
  INSPECTOR_TEST_IDS,
  INSPECTOR_TAB_ORDER,
  INSPECTOR_WIDTHS,
  LINKS_ROWS_ONLY,
  clampInspectorWidth,
  inspectorDefaultWidth,
  inspectorFormFor,
  inspectorPanelId,
  inspectorRegionFor,
  inspectorTabId,
  inspectorTabKeys,
  inspectorDefaultsOpen,
  inspectorTabStorageKey,
  isSpineLinkType,
  normalizeLinkTypeKey,
} from "./inspectorContract";
import type { ArtifactKind } from "./types";

describe("inspectorContract — type matrix (spec §3)", () => {
  it("has exactly the four documented tabs, in order", () => {
    expect(INSPECTOR_TAB_ORDER).toEqual(["version", "diff", "links", "comments"]);
  });

  it("never gives mainGoal a links tab", () => {
    expect(HAS_LINKS_TAB.has("mainGoal")).toBe(false);
    // …but every other kind has one.
    const kindsWithoutLinks = [...HAS_LINKS_TAB];
    expect(kindsWithoutLinks).not.toContain("mainGoal");
    expect(HAS_LINKS_TAB.size).toBe(11);
  });

  it("keeps the rows-only group exactly at glossary, icd and diagram", () => {
    expect([...LINKS_ROWS_ONLY].sort()).toEqual(["diagram", "glossary", "icd"]);
  });

  it("gives a spine to every kind except mainGoal, glossary, icd and diagram", () => {
    expect(HAS_SPINE.has("mainGoal")).toBe(false);
    expect(HAS_SPINE.has("glossary")).toBe(false);
    expect(HAS_SPINE.has("icd")).toBe(false);
    expect(HAS_SPINE.has("diagram")).toBe(false);
    expect(HAS_SPINE.has("requirement")).toBe(true);
    expect(HAS_SPINE.size).toBe(8);
  });
});

describe("inspectorContract — tabs per artifact", () => {
  it("renders all four tabs for a requirement with an Artifact UUID", () => {
    expect(inspectorTabKeys("requirement", "artifact-uuid")).toEqual([
      "version",
      "diff",
      "links",
      "comments",
    ]);
  });

  it("omits the comments tab when the Artifact UUID is not published", () => {
    expect(inspectorTabKeys("requirement", null)).toEqual(["version", "diff", "links"]);
    expect(inspectorTabKeys("adr", null)).toEqual(["version", "diff", "links"]);
  });

  it("renders three tabs for mainGoal (no links, comments with a UUID)", () => {
    expect(inspectorTabKeys("mainGoal", "artifact-uuid")).toEqual([
      "version",
      "diff",
      "comments",
    ]);
  });

  it("keeps the links tab for the spine-less kinds", () => {
    expect(inspectorTabKeys("glossary", null)).toEqual(["version", "diff", "links"]);
  });
});

describe("inspectorContract — id / testid inventory (spec §7, §8.4)", () => {
  it("derives tab and panel ids from the same key", () => {
    for (const key of INSPECTOR_TAB_ORDER) {
      expect(inspectorTabId(key)).toBe(`inspector-tab-${key}`);
      expect(inspectorPanelId(key)).toBe(`inspector-panel-${key}`);
    }
  });

  it("exposes every documented testid and no template without a key", () => {
    const fixed = [
      INSPECTOR_TEST_IDS.root,
      INSPECTOR_TEST_IDS.surface,
      INSPECTOR_TEST_IDS.tabs,
      INSPECTOR_TEST_IDS.rail,
      INSPECTOR_TEST_IDS.railOpen,
      INSPECTOR_TEST_IDS.close,
      INSPECTOR_TEST_IDS.splitter,
      INSPECTOR_TEST_IDS.live,
      INSPECTOR_TEST_IDS.alert,
      INSPECTOR_TEST_IDS.diffPair,
      INSPECTOR_TEST_IDS.baselineSelect,
    ];
    expect(new Set(fixed).size).toBe(fixed.length);
    for (const key of INSPECTOR_TAB_ORDER) {
      expect(INSPECTOR_TEST_IDS.tab(key)).toBe(`inspector-tab-${key}`);
      expect(INSPECTOR_TEST_IDS.panel(key)).toBe(`inspector-panel-${key}`);
      expect(INSPECTOR_TEST_IDS.railCount(key)).toBe(`inspector-rail-count-${key}`);
    }
  });

  it("uses the spec's data-testid literals for the two diff affordances", () => {
    expect(INSPECTOR_TEST_IDS.diffPair).toBe("inspector-diff-pair");
    expect(INSPECTOR_TEST_IDS.baselineSelect).toBe("inspector-baseline-select");
  });
});

describe("inspectorContract — persistence (spec §5.4)", () => {
  it("keys the tab per kind and artifact", () => {
    expect(inspectorTabStorageKey("requirement", "abc")).toBe(
      "reqflow_inspector_tab_requirement_abc",
    );
  });

  it("gives goal and mainGoal one shared slot (I-14)", () => {
    expect(inspectorTabStorageKey("goal", "1")).toBe(GOALS_TAB_STORAGE_KEY);
    expect(inspectorTabStorageKey("mainGoal", "2")).toBe(GOALS_TAB_STORAGE_KEY);
  });
});

describe("inspectorContract — width states (spec §4.2)", () => {
  const cases: Array<[number, "R1" | "R2" | "R3" | "R4" | "R5"]> = [
    [1920, "R1"],
    [1600, "R1"],
    [1599, "R2"],
    [1440, "R2"],
    [1439, "R3"],
    [1280, "R3"],
    [1279, "R3"],
    [1024, "R3"],
    [1023, "R4"],
    [768, "R4"],
    [767, "R5"],
    [320, "R5"],
  ];

  it.each(cases)("maps %i px to %s", (width, region) => {
    expect(inspectorRegionFor(width)).toBe(region);
  });

  it("opens R1/R2/R3 by default and keeps R4/R5 as rail", () => {
    expect(inspectorFormFor("R1", true)).toBe("panel");
    expect(inspectorFormFor("R2", true)).toBe("panel");
    expect(inspectorFormFor("R3", true)).toBe("sheet");
    expect(inspectorFormFor("R4", true)).toBe("sheet");
    expect(inspectorFormFor("R5", true)).toBe("fullscreen");
    expect(inspectorFormFor("R1", false)).toBe("rail");
    expect(inspectorFormFor("R3", false)).toBe("rail");
    expect(inspectorFormFor("R5", false)).toBe("rail");
  });

  it("opens the R3 sheet only from 1280 px upwards (spec §4.2)", () => {
    expect(inspectorDefaultsOpen("R1", 1600)).toBe(true);
    expect(inspectorDefaultsOpen("R2", 1440)).toBe(true);
    expect(inspectorDefaultsOpen("R3", 1440)).toBe(true);
    expect(inspectorDefaultsOpen("R3", 1280)).toBe(true);
    expect(inspectorDefaultsOpen("R3", 1279)).toBe(false);
    expect(inspectorDefaultsOpen("R3", 1024)).toBe(false);
    expect(inspectorDefaultsOpen("R4", 900)).toBe(false);
    expect(inspectorDefaultsOpen("R5", 320)).toBe(false);
  });

  it("defaults to 360 in R1 and 320 elsewhere", () => {
    expect(inspectorDefaultWidth("R1")).toBe(360);
    expect(inspectorDefaultWidth("R2")).toBe(320);
    expect(inspectorDefaultWidth("R4")).toBe(320);
  });

  it("clamps every width into the four-alias scale", () => {
    expect(clampInspectorWidth(10)).toBe(INSPECTOR_WIDTHS.min);
    expect(clampInspectorWidth(9999)).toBe(INSPECTOR_WIDTHS.max);
    expect(clampInspectorWidth(Number.NaN)).toBe(INSPECTOR_WIDTHS.default);
    expect(clampInspectorWidth(400)).toBe(400);
  });
});

describe("inspectorContract — spine link group (spec §2.3)", () => {
  it("normalises backend keys before the membership test", () => {
    expect(normalizeLinkTypeKey("derives_from")).toBe("derives-from");
    expect(isSpineLinkType("derives_from")).toBe(true);
    expect(isSpineLinkType("verifies")).toBe(true);
    expect(isSpineLinkType("mitigates")).toBe(false);
    expect(isSpineLinkType("references")).toBe(false);
    expect(isSpineLinkType("diagram-ref")).toBe(false);
  });
});

describe("inspectorContract — every ArtifactKind is classified", () => {
  const kinds: ArtifactKind[] = [
    "icd",
    "diagram",
    "adr",
    "risk",
    "issue",
    "glossary",
    "stakeholderNeed",
    "requirement",
    "architecture",
    "testCase",
    "goal",
    "mainGoal",
  ];

  it("never returns an empty tab list", () => {
    for (const kind of kinds) {
      expect(inspectorTabKeys(kind, null).length).toBeGreaterThanOrEqual(2);
    }
  });

  it("treats rows-only and links-tab membership consistently", () => {
    for (const kind of LINKS_ROWS_ONLY) {
      expect(HAS_LINKS_TAB.has(kind)).toBe(true);
      expect(HAS_SPINE.has(kind)).toBe(false);
    }
  });
});
