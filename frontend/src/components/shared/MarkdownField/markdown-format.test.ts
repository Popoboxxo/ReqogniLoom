/**
 * #1287 — pure formatting contract of the markdown toolbar.
 *
 * `applyMarkdownFormat` is the only place that decides where a marker lands and
 * where the caret/selection must end up afterwards, so it is pinned here without
 * a DOM: the component layer only forwards `selectionStart`/`selectionEnd` and
 * re-applies the returned offsets.
 */

import { describe, expect, it } from "vitest";

import { applyMarkdownFormat } from "./markdown-format";

describe("applyMarkdownFormat – inline markers", () => {
  it("wraps a selection in bold and keeps the text selected", () => {
    expect(applyMarkdownFormat("hello", 0, 5, "bold")).toEqual({
      value: "**hello**",
      selStart: 2,
      selEnd: 7,
    });
  });

  it("puts the caret inside the markers for an empty selection", () => {
    expect(applyMarkdownFormat("ab", 1, 1, "bold")).toEqual({
      value: "a****b",
      selStart: 3,
      selEnd: 3,
    });
  });

  it("wraps in italic and code with their own marker", () => {
    expect(applyMarkdownFormat("x", 0, 1, "italic").value).toBe("*x*");
    expect(applyMarkdownFormat("x", 0, 1, "code").value).toBe("`x`");
  });

  it("wraps only the selected span, not the whole value", () => {
    expect(applyMarkdownFormat("a b c", 2, 3, "bold")).toEqual({
      value: "a **b** c",
      selStart: 4,
      selEnd: 5,
    });
  });
});

describe("applyMarkdownFormat – link template", () => {
  it("turns the selection into [text](url) and selects the url placeholder", () => {
    expect(applyMarkdownFormat("text", 0, 4, "link")).toEqual({
      value: "[text](url)",
      selStart: 7,
      selEnd: 10,
    });
  });

  it("leaves the caret inside the brackets for an empty selection", () => {
    expect(applyMarkdownFormat("abc", 1, 1, "link")).toEqual({
      value: "a[](url)bc",
      selStart: 2,
      selEnd: 2,
    });
  });
});

describe("applyMarkdownFormat – heading", () => {
  it("prefixes the caret's line with ## and moves the caret after the marker", () => {
    expect(applyMarkdownFormat("abc", 1, 1, "heading")).toEqual({
      value: "## abc",
      selStart: 4,
      selEnd: 4,
    });
  });

  it("inserts at the start of the line, not at the caret column", () => {
    expect(applyMarkdownFormat("a\nb", 2, 2, "heading")).toEqual({
      value: "a\n## b",
      selStart: 5,
      selEnd: 5,
    });
  });

  it("removes an existing ## on the line (toggle)", () => {
    expect(applyMarkdownFormat("## abc", 4, 4, "heading")).toEqual({
      value: "abc",
      selStart: 1,
      selEnd: 1,
    });
  });
});

describe("applyMarkdownFormat – list prefixes", () => {
  it("prefixes every selected line with '- '", () => {
    expect(applyMarkdownFormat("one\ntwo", 0, 7, "bulletList")).toEqual({
      value: "- one\n- two",
      selStart: 2,
      selEnd: 11,
    });
  });

  it("prefixes a single caret line and keeps the caret after the marker", () => {
    expect(applyMarkdownFormat("only", 0, 0, "numberedList")).toEqual({
      value: "1. only",
      selStart: 3,
      selEnd: 3,
    });
  });

  it("only touches the selected block, leaving neighbouring lines alone", () => {
    expect(applyMarkdownFormat("top\nmid\nbottom", 4, 10, "bulletList")).toEqual({
      value: "top\n- mid\n- bottom",
      selStart: 6,
      selEnd: 14,
    });
  });

  it("strips the prefix again when every selected line already has it (toggle)", () => {
    expect(applyMarkdownFormat("- one\n- two", 0, 11, "bulletList")).toEqual({
      value: "one\ntwo",
      selStart: 0,
      selEnd: 7,
    });
  });
});
