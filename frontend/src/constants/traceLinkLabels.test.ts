/**
 * Unit tests for the trace-link Tri-Label constants (Task 23).
 *
 * Verifies:
 *   - `FALLBACK_TRI_LABELS` covers exactly the eight built-in link types
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
  "decides",
  "decomposes",
  "derives-from",
  "diagram-ref",
  "mitigates",
  "references",
  "verifies",
];

describe("FALLBACK_TRI_LABELS", () => {
  it("covers exactly the eight built-in link types", () => {
    expect(Object.keys(FALLBACK_TRI_LABELS).sort()).toEqual([...EXPECTED_TYPES].sort());
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

  it("the fallback table only covers the eight core types", () => {
    expect(Object.keys(FALLBACK_TRI_LABELS).sort()).toEqual([
      "allocated-to",
      "decides",
      "decomposes",
      "derives-from",
      "diagram-ref",
      "mitigates",
      "references",
      "verifies",
    ]);
  });
});

describe("backward-compatible flat label lookup", () => {
  it("getLinkTypeLabel resolves every one of the eight built-in types without a raw-key fallback", () => {
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
