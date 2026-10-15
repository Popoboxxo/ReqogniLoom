/**
 * Sparse ordering helpers of the attribute editor (feature #1260).
 *
 * These mirror `backend/attribute_definitions/ordering.py` one-to-one: the
 * editor applies a move optimistically and the server re-applies the same rules,
 * so a mismatch here would leave the page "dirty" after a persisted drop or —
 * worse — show a different order than the one the server stored.
 */

import { describe, it, expect } from "vitest";

import type { AttributeSpec } from "../../api/attribute-definitions";
import {
  ORDER_STEP,
  anchorBefore,
  indexAfterAnchor,
  moveAnchor,
  moveAttribute,
} from "./attribute-edits";

function attr(overrides: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "alpha",
    kind: "extended",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "general",
    order: ORDER_STEP,
    label: { de: "", en: "" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
    ...overrides,
  };
}

function orders(attributes: AttributeSpec[]): Record<string, number> {
  return Object.fromEntries(attributes.map((a) => [a.name, a.order]));
}

function names(attributes: AttributeSpec[]): string[] {
  return attributes.map((a) => a.name);
}

const GAPPY = [
  attr({ name: "alpha", order: ORDER_STEP }),
  attr({ name: "beta", order: 2 * ORDER_STEP }),
  attr({ name: "gamma", section: "other", order: ORDER_STEP }),
];

describe("moveAttribute (sparse keys)", () => {
  it("takes a free slot between the two neighbours and rewrites one entry", () => {
    const result = moveAttribute(GAPPY, "gamma", "general", 1);

    expect(orders(result)).toEqual({
      alpha: ORDER_STEP,
      gamma: ORDER_STEP + ORDER_STEP / 2,
      beta: 2 * ORDER_STEP,
    });
    expect(names(result)).toEqual(["alpha", "gamma", "beta"]);
  });

  it("moves to the front with the free slot below the first entry", () => {
    const result = moveAttribute(GAPPY, "beta", "general", 0);

    expect(orders(result).beta).toBe(0);
    expect(names(result)).toEqual(["beta", "alpha", "gamma"]);
  });

  it("appends one step beyond the last entry of the target section", () => {
    const result = moveAttribute(GAPPY, "gamma", "general", Number.MAX_SAFE_INTEGER);

    expect(orders(result).gamma).toBe(3 * ORDER_STEP);
    expect(names(result)).toEqual(["alpha", "beta", "gamma"]);
  });

  it("re-spaces a section whose neighbours hold adjacent keys", () => {
    const dense = [attr({ name: "alpha", order: 0 }), attr({ name: "beta", order: 1 })];

    const result = moveAttribute(dense, "beta", "general", 0);

    expect(orders(result)).toEqual({ beta: ORDER_STEP, alpha: 2 * ORDER_STEP });
    expect(names(result)).toEqual(["beta", "alpha"]);
  });

  it("leaves other sections alone", () => {
    const result = moveAttribute(GAPPY, "alpha", "general", 1);

    expect(orders(result).gamma).toBe(ORDER_STEP);
  });

  it("is a no-op for an unknown attribute", () => {
    expect(moveAttribute(GAPPY, "nope", "general", 0)).toBe(GAPPY);
  });

  it("never mutates its input", () => {
    moveAttribute(GAPPY, "beta", "general", 0);

    expect(names(GAPPY)).toEqual(["alpha", "beta", "gamma"]);
    expect(orders(GAPPY)).toEqual({
      alpha: ORDER_STEP,
      beta: 2 * ORDER_STEP,
      gamma: ORDER_STEP,
    });
  });
});

describe("moveAnchor", () => {
  it("names the neighbour the row must follow", () => {
    expect(moveAnchor(GAPPY, "gamma", "general", 1)).toBe("alpha");
  });

  it("is null for the front of a section", () => {
    expect(moveAnchor(GAPPY, "gamma", "general", 0)).toBeNull();
  });

  it("is the last neighbour when the row lands at the end", () => {
    expect(moveAnchor(GAPPY, "gamma", "general", Number.MAX_SAFE_INTEGER)).toBe("beta");
  });

  it("ignores the moved attribute itself", () => {
    expect(moveAnchor(GAPPY, "alpha", "general", 1)).toBe("beta");
  });

  it("agrees with the position moveAttribute actually produces", () => {
    for (const index of [0, 1, 2, Number.MAX_SAFE_INTEGER]) {
      const anchor = moveAnchor(GAPPY, "gamma", "general", index);
      const inSection = moveAttribute(GAPPY, "gamma", "general", index).filter(
        (a) => a.section === "general"
      );
      const position = inSection.findIndex((a) => a.name === "gamma");
      const anchorPosition =
        anchor === null ? 0 : inSection.findIndex((a) => a.name === anchor) + 1;
      expect(position).toBe(anchorPosition);
    }
  });
});

describe("anchorBefore / indexAfterAnchor", () => {
  it("names the sibling the attribute currently follows", () => {
    expect(anchorBefore(GAPPY, "beta")).toBe("alpha");
    expect(anchorBefore(GAPPY, "alpha")).toBeNull();
  });

  it("is null for an attribute of another section that is first there", () => {
    expect(anchorBefore(GAPPY, "gamma")).toBeNull();
  });

  it("round-trips an anchor back into an index", () => {
    expect(indexAfterAnchor(GAPPY, "gamma", "general", "alpha")).toBe(1);
    expect(indexAfterAnchor(GAPPY, "gamma", "general", "beta")).toBe(2);
    expect(indexAfterAnchor(GAPPY, "gamma", "general", null)).toBe(0);
  });

  it("appends when the anchor is gone", () => {
    expect(indexAfterAnchor(GAPPY, "gamma", "general", "vanished")).toBe(2);
  });
});
