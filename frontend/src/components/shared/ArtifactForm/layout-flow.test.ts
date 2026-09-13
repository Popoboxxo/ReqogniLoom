/**
 * layout-flow.test.ts — 12-column layout derivation (WS4 #938, spec section 7).
 *
 * Pure-function coverage of the client mirror of the backend's
 * `materialize_*`/`effective_*` helpers, so the renderer and the editor are
 * proven to keep a definition WITHOUT a flow rendering exactly as before.
 */

import { describe, expect, it } from "vitest";

import type { AttributeSpec, SectionSpec } from "../../../api/attribute-definitions";
import {
  attributeSpanColumns,
  deleteSectionToken,
  effectiveAttributeFlowTokens,
  materializeAttributeFlow,
  materializeSectionFlow,
  moveToken,
  orderedSectionTokens,
  pruneAttributeFlows,
  pruneSectionFlow,
  removeToken,
  replaceToken,
  renameSectionToken,
  resolveAttributeFlow,
  sectionLayoutColumns,
  spacerColumns,
  spanClassSuffix,
} from "./layout-flow";

function attr(name: string, section = "general", order = 0): AttributeSpec {
  return {
    name,
    kind: "core",
    type: "text",
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section,
    order,
    label: { de: "", en: "" },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: false,
    audience: "basic",
  };
}

function section(over: Partial<SectionSpec>): SectionSpec {
  return { name: "general", order: 0, visible: true, layout: "full", ...over };
}

describe("layout column vocabulary", () => {
  it("maps span/section/spacer tokens to columns", () => {
    expect(attributeSpanColumns("full")).toBe(12);
    expect(attributeSpanColumns("half")).toBe(6);
    expect(attributeSpanColumns("quarter")).toBe(3);
    expect(attributeSpanColumns(undefined)).toBe(12);
    expect(sectionLayoutColumns("half")).toBe(6);
    expect(sectionLayoutColumns(undefined)).toBe(12);
    expect(spacerColumns("sm")).toBe(1);
    expect(spacerColumns("md")).toBe(2);
    expect(spacerColumns("lg")).toBe(4);
  });

  it("clamps the CSS-module span suffix into the 12-column grid", () => {
    expect(spanClassSuffix(0)).toBe(1);
    expect(spanClassSuffix(6)).toBe(6);
    expect(spanClassSuffix(99)).toBe(12);
  });
});

describe("default derivation (no flow = old behaviour)", () => {
  it("materializes one section token per section, no spacers", () => {
    expect(materializeSectionFlow(["a", "b"])).toEqual([
      { kind: "section", name: "a" },
      { kind: "section", name: "b" },
    ]);
  });

  it("materializes one full-span attribute token per attribute", () => {
    expect(materializeAttributeFlow([attr("title"), attr("uid")])).toEqual([
      { kind: "attribute", name: "title", span: "full" },
      { kind: "attribute", name: "uid", span: "full" },
    ]);
  });

  it("orderedSectionTokens derives the section order when there is no flow", () => {
    expect(orderedSectionTokens(undefined, ["a", "b"])).toEqual([
      { kind: "section", name: "a" },
      { kind: "section", name: "b" },
    ]);
  });

  it("resolveAttributeFlow stacks every attribute at full width without a flow", () => {
    const entries = resolveAttributeFlow(undefined, [attr("a", "general", 0), attr("b", "general", 1)]);
    expect(entries).toEqual([
      { kind: "attribute", attribute: expect.objectContaining({ name: "a" }), span: "full", columns: 12 },
      { kind: "attribute", attribute: expect.objectContaining({ name: "b" }), span: "full", columns: 12 },
    ]);
  });
});

describe("supported flow lifecycle: default vs explicit empty (WS4 #938)", () => {
  it("only `undefined` derives the default; `[]` positions no token", () => {
    // `undefined` => default derivation.
    expect(orderedSectionTokens(undefined, ["a", "b"])).toEqual([
      { kind: "section", name: "a" },
      { kind: "section", name: "b" },
    ]);
    expect(effectiveAttributeFlowTokens(section({}), [attr("a"), attr("b")])).toEqual([
      { kind: "attribute", name: "a", span: "full" },
      { kind: "attribute", name: "b", span: "full" },
    ]);
    // explicitly stored `[]` => no tokens, no derivation.
    expect(orderedSectionTokens([], ["a", "b"])).toEqual([]);
    expect(
      effectiveAttributeFlowTokens(section({ attribute_flow: [] }), [attr("a"), attr("b")])
    ).toEqual([]);
    expect(resolveAttributeFlow(section({ attribute_flow: [] }), [attr("a")])).toEqual([]);
  });
});

describe("stored flow is respected, stale tokens are additive-safe", () => {
  it("keeps spacers and the stored section order, appending unpositioned sections", () => {
    expect(
      orderedSectionTokens(
        [
          { kind: "section", name: "b" },
          { kind: "spacer", size: "md" },
        ],
        ["a", "b"]
      )
    ).toEqual([
      { kind: "section", name: "b" },
      { kind: "spacer", size: "md" },
      { kind: "section", name: "a" },
    ]);
  });

  it("drops section tokens naming an unknown or duplicated section", () => {
    expect(
      orderedSectionTokens(
        [
          { kind: "section", name: "ghost" },
          { kind: "section", name: "a" },
          { kind: "section", name: "a" },
        ],
        ["a"]
      )
    ).toEqual([{ kind: "section", name: "a" }]);
  });

  it("respects attribute spans and spacers and appends unpositioned attributes", () => {
    const entries = resolveAttributeFlow(
      section({
        attribute_flow: [
          { kind: "attribute", name: "b", span: "half" },
          { kind: "spacer", size: "sm" },
          { kind: "attribute", name: "a", span: "quarter" },
        ],
      }),
      [attr("a", "general", 0), attr("b", "general", 1), attr("c", "general", 2)]
    );
    expect(entries.map((entry) => entry.kind)).toEqual([
      "attribute",
      "spacer",
      "attribute",
      "attribute",
    ]);
    expect(entries[0]).toMatchObject({ kind: "attribute", columns: 6 });
    expect(entries[1]).toMatchObject({ kind: "spacer", size: "sm", columns: 1 });
    expect(entries[2]).toMatchObject({ kind: "attribute", columns: 3 });
    expect(entries[3]).toMatchObject({ kind: "attribute", columns: 12 });
  });

  it("drops a stored attribute token whose attribute no longer exists", () => {
    const tokens = effectiveAttributeFlowTokens(
      section({ attribute_flow: [
        { kind: "attribute", name: "ghost", span: "half" },
        { kind: "attribute", name: "a", span: "quarter" },
      ] }),
      [attr("a")]
    );
    expect(tokens).toEqual([
      { kind: "attribute", name: "a", span: "quarter" },
    ]);
  });
});

describe("consistency maintenance", () => {
  it("renames a section token and merges onto an existing one", () => {
    expect(
      renameSectionToken([{ kind: "section", name: "a" }], "a", "b")
    ).toEqual([{ kind: "section", name: "b" }]);
    expect(
      renameSectionToken(
        [{ kind: "section", name: "a" }, { kind: "section", name: "b" }],
        "a",
        "b"
      )
    ).toEqual([{ kind: "section", name: "b" }]);
  });

  it("preserves an absent flow through rename/delete", () => {
    expect(renameSectionToken(undefined, "a", "b")).toBeUndefined();
    expect(deleteSectionToken(undefined, "a")).toBeUndefined();
  });

  it("deletes a section token but keeps spacers", () => {
    expect(
      deleteSectionToken(
        [
          { kind: "section", name: "a" },
          { kind: "spacer", size: "lg" },
          { kind: "section", name: "b" },
        ],
        "a"
      )
    ).toEqual([{ kind: "spacer", size: "lg" }, { kind: "section", name: "b" }]);
  });

  it("pruneSectionFlow removes dangling section tokens, keeps spacers and an empty-name no-op", () => {
    expect(
      pruneSectionFlow(
        [
          { kind: "section", name: "a" },
          { kind: "section", name: "ghost" },
          { kind: "spacer", size: "sm" },
        ],
        ["a"]
      )
    ).toEqual([{ kind: "section", name: "a" }, { kind: "spacer", size: "sm" }]);
    expect(pruneSectionFlow([{ kind: "section", name: "a" }], [])).toEqual([
      { kind: "section", name: "a" },
    ]);
  });

  it("pruneAttributeFlows drops dangling attribute tokens only", () => {
    const out = pruneAttributeFlows(
      [
        section({ attribute_flow: [
          { kind: "attribute", name: "ghost", span: "half" },
          { kind: "spacer", size: "md" },
        ] }),
        section({ name: "untouched" }),
      ],
      ["a"]
    );
    expect(out[0].attribute_flow).toEqual([{ kind: "spacer", size: "md" }]);
    expect(out[1].attribute_flow).toBeUndefined();
  });
});

describe("editor mutations", () => {
  const flow = [
    { kind: "attribute" as const, name: "a", span: "full" as const },
    { kind: "spacer" as const, size: "md" as const },
    { kind: "attribute" as const, name: "b", span: "half" as const },
  ];

  it("moves, removes and replaces tokens without mutating the input", () => {
    expect(moveToken(flow, 0, 2)).toEqual([flow[1], flow[2], flow[0]]);
    expect(removeToken(flow, 1)).toEqual([flow[0], flow[2]]);
    expect(replaceToken(flow, 1, { kind: "spacer", size: "lg" })).toEqual([
      flow[0],
      { kind: "spacer", size: "lg" },
      flow[2],
    ]);
    expect(flow).toHaveLength(3);
  });
});
