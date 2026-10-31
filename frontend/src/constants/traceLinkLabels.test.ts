/**
 * Unit tests for the trace-link Tri-Label constants (Task 23).
 *
 * Verifies:
 *   - `FALLBACK_TRI_LABELS` covers the built-in link types
 *   - Every fallback entry has non-empty DE + EN downstream/upstream/neutral labels
 *   - `getTriLabel`: catalog label wins, static fallback second, raw key last
 *   - `ALL_LINK_TYPES` is no longer exported (catalog-driven now, Task 22)
 *   - `getLinkTypeLabel` / `LINK_TYPE_LABELS` stay backward-compatible for the
 *     out-of-scope consumers that were not migrated to `useLinkTypes()` in
 *     this task, including their raw-key fallback for a non-built-in type
 */
import { describe, it, expect } from "vitest";
import {
  FALLBACK_TRI_LABELS,
  LINK_TYPE_LABELS,
  getLinkTypeLabel,
  getTriLabel,
} from "./traceLinkLabels";

const EXPECTED_TYPES = [
  "allocated-to",
  "blocks",
  "decides",
  "decomposes",
  "derives-from",
  "diagram-ref",
  "mitigates",
  "performs",
  "realizes",
  "references",
  "refines",
  "resolves",
  "satisfies",
  "threatens",
  "validates",
  "verifies",
];

describe("FALLBACK_TRI_LABELS", () => {
  it("covers the built-in link types", () => {
    // Membership, not a pinned size: the backend catalog gains types per plan
    // (Plan F and later), and this table is only its pre-load fallback.
    for (const lt of EXPECTED_TYPES) {
      expect(FALLBACK_TRI_LABELS[lt]).toBeDefined();
    }
  });

  it.each(EXPECTED_TYPES)("has non-empty DE+EN downstream/upstream/neutral labels for '%s'", (lt) => {
    const entry = FALLBACK_TRI_LABELS[lt];
    expect(entry.de.downstream).toBeTruthy();
    expect(entry.de.upstream).toBeTruthy();
    expect(entry.de.neutral).toBeTruthy();
    expect(entry.en.downstream).toBeTruthy();
    expect(entry.en.upstream).toBeTruthy();
    expect(entry.en.neutral).toBeTruthy();
  });

  it("mirrors the pinned Issue/Risk vocabulary labels (Plan F F1.1-T2)", () => {
    expect(FALLBACK_TRI_LABELS.blocks).toEqual({
      de: { downstream: "blockiert", upstream: "wird blockiert durch", neutral: "Blockade" },
      en: { downstream: "blocks", upstream: "is blocked by", neutral: "Blocker" },
    });
    expect(FALLBACK_TRI_LABELS.resolves).toEqual({
      de: { downstream: "löst", upstream: "wird gelöst durch", neutral: "Lösung" },
      en: { downstream: "resolves", upstream: "is resolved by", neutral: "Resolution" },
    });
    expect(FALLBACK_TRI_LABELS.threatens).toEqual({
      de: { downstream: "bedroht", upstream: "wird bedroht durch", neutral: "Bedrohung" },
      en: { downstream: "threatens", upstream: "is threatened by", neutral: "Threat" },
    });
  });
});

describe("getTriLabel", () => {
  it("prefers a catalog label over the static fallback", () => {
    expect(
      getTriLabel("verifies", "de", "neutral", {
        downstream: "prüft",
        upstream: "wird geprüft von",
        neutral: "Prüfung",
      }),
    ).toBe("Prüfung");
  });

  it("falls back to the static table for a built-in key", () => {
    expect(getTriLabel("verifies", "de", "neutral")).toBe("Verifikation");
    expect(getTriLabel("verifies", "de", "downstream")).toBe("verifiziert");
    expect(getTriLabel("verifies", "de", "upstream")).toBe("wird verifiziert von");
    expect(getTriLabel("verifies", "en", "neutral")).toBe("Verification");
  });

  it("falls back to the raw key for a tenant-invented type", () => {
    expect(getTriLabel("conflicts-with", "de", "neutral")).toBe("conflicts-with");
  });

  it("no longer exports a hardcoded complete list", async () => {
    const module = await import("./traceLinkLabels");
    expect("ALL_LINK_TYPES" in module).toBe(false);
  });

  it("lists every built-in type exactly once", () => {
    const keys = Object.keys(FALLBACK_TRI_LABELS);
    expect(new Set(keys).size).toBe(keys.length);
    for (const lt of EXPECTED_TYPES) {
      expect(keys).toContain(lt);
    }
  });
});

describe("backward-compatible flat label lookup", () => {
  it("getLinkTypeLabel resolves every built-in type without a raw-key fallback", () => {
    for (const lt of Object.keys(FALLBACK_TRI_LABELS)) {
      const label = getLinkTypeLabel(lt);
      expect(label).toBeTruthy();
      expect(label).not.toBe(lt); // never falls back to the raw key for a known built-in
    }
  });

  it("LINK_TYPE_LABELS is derived from the fallback table's EN-neutral form", () => {
    expect(LINK_TYPE_LABELS["allocated-to"]).toBe("Allocation");
    expect(LINK_TYPE_LABELS.decomposes).toBe("Decomposition");
  });

  it("getLinkTypeLabel falls back to the raw key for a tenant-invented type (Finding 1)", () => {
    expect(getLinkTypeLabel("conflicts-with")).toBe("conflicts-with");
    expect(LINK_TYPE_LABELS["conflicts-with"]).toBeUndefined();
  });
});
