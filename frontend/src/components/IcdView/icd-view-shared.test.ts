/**
 * Unit tests for the IcdView shared helpers (REQ-050 extraction).
 * Covers the pure similarity/list/id helpers lifted out of the former
 * monolithic IcdView (REQ-006 similar-interface detection).
 */

import { describe, it, expect } from "vitest";
import type { Icd } from "../../api/icds";
import {
  extractErrorMessage,
  findSimilarICDs,
  joinListField,
  parseListField,
  shortId,
} from "./icd-view-shared";

function makeIcd(id: string, name: string): Icd {
  return {
    id,
    name,
    workspace_id: "ws-1",
    source_element_id: "s",
    target_element_id: "t",
    current_version: null,
    created_at: null,
  };
}

describe("icd-view-shared", () => {
  it("shortId truncates to 8 chars with an ellipsis", () => {
    expect(shortId("0123456789abcdef")).toBe("01234567…");
  });

  it("parseListField splits, trims and drops blank lines", () => {
    expect(parseListField("a\n  b  \n\n c\n")).toEqual(["a", "b", "c"]);
  });

  it("joinListField round-trips an array and tolerates undefined", () => {
    expect(joinListField(["a", "b"])).toBe("a\nb");
    expect(joinListField(undefined)).toBe("");
  });

  it("extractErrorMessage prefers the API message shape", () => {
    expect(extractErrorMessage({ error: { message: "boom" } }, "fb")).toBe(
      "boom",
    );
    expect(extractErrorMessage(null, "fallback")).toBe("fallback");
  });

  it("findSimilarICDs excludes self and ranks by descending score", () => {
    const current = makeIcd("1", "User Auth Service Interface");
    const others = [
      makeIcd("2", "User Auth Service Gateway"), // high overlap
      makeIcd("3", "Payment Billing Endpoint"), // no overlap
      makeIcd("4", "Auth Service Interface Legacy"), // partial overlap
    ];
    const result = findSimilarICDs(current, [current, ...others], 0.2);
    // Self is never returned.
    expect(result.every((r) => r.icd.id !== "1")).toBe(true);
    // The unrelated ICD is filtered out by the threshold.
    expect(result.find((r) => r.icd.id === "3")).toBeUndefined();
    // Scores are sorted descending.
    const scores = result.map((r) => r.score);
    expect([...scores].sort((a, b) => b - a)).toEqual(scores);
  });
});
