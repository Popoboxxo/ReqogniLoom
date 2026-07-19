/**
 * Unit tests for the trace-link Tri-Label constants (UMSETZUNGSPLAN_SYSENG_2.0.md §1.3).
 *
 * Verifies:
 *   - All 14 backend LinkType values are covered (incl. `decomposes`)
 *   - Every entry has non-empty DE + EN downstream/upstream/neutral labels
 *   - getTriLabel is a pure lookup (no fallback branch)
 *   - getLinkTypeLabel / LINK_TYPE_LABELS stay backward-compatible for
 *     existing badge/dropdown consumers
 */
import { describe, it, expect } from "vitest";
import {
  ALL_LINK_TYPES,
  LINK_TYPE_LABELS,
  LINK_TYPE_TRI_LABELS,
  getLinkTypeLabel,
  getTriLabel,
} from "./traceLinkLabels";
import type { LinkType } from "../types";

const EXPECTED_TYPES: LinkType[] = [
  "parent-child",
  "derives-from",
  "satisfies",
  "verifies",
  "implements",
  "refines",
  "documents",
  "realizes",
  "traces",
  "copy-of",
  "allocated-to",
  "uses-term",
  "decides",
  "decomposes",
];

describe("LINK_TYPE_TRI_LABELS", () => {
  it("covers exactly the 14 backend LinkType values", () => {
    expect(ALL_LINK_TYPES.sort()).toEqual([...EXPECTED_TYPES].sort());
    expect(ALL_LINK_TYPES).toHaveLength(14);
  });

  it("includes the additive 'decomposes' type", () => {
    expect(ALL_LINK_TYPES).toContain("decomposes");
    expect(LINK_TYPE_TRI_LABELS.decomposes).toBeDefined();
  });

  it.each(EXPECTED_TYPES)("has non-empty DE+EN downstream/upstream/neutral labels for '%s'", (lt) => {
    const entry = LINK_TYPE_TRI_LABELS[lt];
    expect(entry.de.downstream).toBeTruthy();
    expect(entry.de.upstream).toBeTruthy();
    expect(entry.de.neutral).toBeTruthy();
    expect(entry.en.downstream).toBeTruthy();
    expect(entry.en.upstream).toBeTruthy();
    expect(entry.en.neutral).toBeTruthy();
  });

  it("getTriLabel is a pure lookup for all directions", () => {
    expect(getTriLabel("verifies", "de", "downstream")).toBe("verifiziert");
    expect(getTriLabel("verifies", "de", "upstream")).toBe("wird verifiziert von");
    expect(getTriLabel("verifies", "en", "neutral")).toBe("Verification");
  });
});

describe("backward-compatible flat label lookup", () => {
  it("getLinkTypeLabel resolves every one of the 14 types without a raw-enum fallback", () => {
    for (const lt of ALL_LINK_TYPES) {
      const label = getLinkTypeLabel(lt);
      expect(label).toBeTruthy();
      expect(label).not.toBe(lt); // never falls back to the raw enum string
    }
  });

  it("LINK_TYPE_LABELS is derived from the Tri-Label EN-neutral form", () => {
    expect(LINK_TYPE_LABELS["allocated-to"]).toBe("Allocation");
    expect(LINK_TYPE_LABELS.decomposes).toBe("Decomposition");
  });
});
