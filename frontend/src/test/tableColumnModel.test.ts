/**
 * Task 4.2 — column model (plan 2026-11-04-tabellenansicht-s4).
 */
import { describe, expect, it } from "vitest";

import type { AttributeSpec, AttributeType } from "../api/attribute-definitions";
import {
  buildColumns,
  columnLabel,
  isWorkflowOwned,
  normaliseSort,
  operatorsForColumn,
} from "../components/shared/ArtifactTable/columnModel";

function attr(
  name: string,
  type: AttributeType,
  overrides: Partial<AttributeSpec> = {}
): AttributeSpec {
  return {
    name,
    kind: "core",
    type,
    widget_key: null,
    fields: [],
    options: [],
    required: false,
    visible: true,
    locked: false,
    editable: true,
    section: "basics",
    order: 0,
    label: { de: name, en: name },
    help_text: { de: "", en: "" },
    default: null,
    validation: {},
    ai_elicit: false,
    export: true,
    audience: "basic",
    ...overrides,
  };
}

describe("operatorsForColumn", () => {
  it("maps every type to the backend operator table", () => {
    expect(operatorsForColumn({ type: "text", kind: "core" })).toEqual(["contains"]);
    expect(operatorsForColumn({ type: "textarea", kind: "core" })).toEqual(["contains"]);
    expect(operatorsForColumn({ type: "number", kind: "core" })).toEqual([
      "eq",
      "gte",
      "lte",
    ]);
    expect(operatorsForColumn({ type: "boolean", kind: "core" })).toEqual(["eq"]);
    expect(operatorsForColumn({ type: "enum", kind: "core" })).toEqual(["in"]);
    expect(operatorsForColumn({ type: "multi-enum", kind: "core" })).toEqual(["in"]);
    expect(operatorsForColumn({ type: "date", kind: "core" })).toEqual(["gte", "lte"]);
    expect(operatorsForColumn({ type: "reference", kind: "core" })).toEqual(["in"]);
    expect(operatorsForColumn({ type: "user", kind: "core" })).toEqual(["in"]);
    expect(operatorsForColumn({ type: "actor", kind: "core" })).toEqual(["in"]);
    expect(operatorsForColumn({ type: "criteria-list", kind: "core" })).toEqual([]);
    expect(operatorsForColumn({ type: "widget", kind: "core" })).toEqual([]);
  });
});

describe("buildColumns", () => {
  it("is filterable by 'in' for status but never inline-editable", () => {
    const [status] = buildColumns(
      [attr("status", "enum", { editable: "workflow" })],
      { columns: [] },
      "en"
    );
    expect(status.filterable).toBe(true);
    expect(status.inlineEditable).toBe(false);
    expect(isWorkflowOwned(attr("status", "enum", { editable: "workflow" }))).toBe(true);
  });

  it("treats editable:false as read-only but not workflow-owned", () => {
    const readOnly = attr("uid", "text", { editable: false });
    expect(isWorkflowOwned(readOnly)).toBe(false);
    expect(buildColumns([readOnly], { columns: [] }, "en")[0].inlineEditable).toBe(false);
  });

  it("never makes extended columns filterable or sortable", () => {
    const [extended] = buildColumns(
      [attr("custom_note", "text", { kind: "extended" })],
      { columns: [] },
      "en"
    );
    expect(extended.filterable).toBe(false);
    expect(extended.sortable).toBe(false);
    expect(extended.inlineEditable).toBe(false);
  });

  it("only marks editable:true non-widget core columns inline-editable", () => {
    const columns = buildColumns(
      [
        attr("title", "text"),
        attr("description", "textarea"),
        attr("widget", "widget"),
        attr("locked_field", "text", { editable: false }),
        attr("owner", "text", { editable: "system" }),
      ],
      { columns: [] },
      "en"
    );
    const byName = Object.fromEntries(columns.map((c) => [c.name, c]));
    expect(byName.title.inlineEditable).toBe(true);
    expect(byName.description.inlineEditable).toBe(true);
    expect(byName.widget.inlineEditable).toBe(false);
    expect(byName.locked_field.inlineEditable).toBe(false);
    expect(byName.owner.inlineEditable).toBe(false);
  });

  it("keeps state order first, then definition order", () => {
    const attributes = [
      attr("a", "text", { order: 0 }),
      attr("b", "text", { order: 1 }),
      attr("c", "text", { order: 2 }),
    ];
    const columns = buildColumns(
      attributes,
      { columns: [{ field: "c", order: 0 }, { field: "a", order: 1 }] },
      "en"
    );
    expect(columns.map((c) => c.name)).toEqual(["c", "a", "b"]);
  });

  it("excludes hidden attributes", () => {
    const columns = buildColumns(
      [attr("shown", "text"), attr("hidden", "text", { visible: false })],
      { columns: [] },
      "en"
    );
    expect(columns.map((c) => c.name)).toEqual(["shown"]);
  });

  it("falls back to the field name when no label exists", () => {
    expect(
      columnLabel(attr("bare", "text", { label: { de: "", en: "" } }), "de")
    ).toBe("bare");
    expect(columnLabel(attr("x", "text", { label: { de: "Titel", en: "Title" } }), "de")).toBe(
      "Titel"
    );
  });

  it("drops sort terms for non-sortable/unknown fields", () => {
    const columns = buildColumns(
      [attr("title", "text"), attr("custom", "text", { kind: "extended" })],
      { columns: [] },
      "en"
    );
    expect(
      normaliseSort(
        [
          { field: "title", dir: "asc" },
          { field: "custom", dir: "desc" },
          { field: "gone", dir: "asc" },
        ],
        columns
      )
    ).toEqual([{ field: "title", dir: "asc" }]);
  });
});
