/**
 * AttributeTable.test.tsx (Task 4, spec section 4.2).
 */

import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import { AttributeTable } from "./AttributeTable";
import type { AttributeSpec } from "../../api/attribute-definitions";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

function attr(overrides: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "a",
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
    order: 0,
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

const ATTRIBUTES: AttributeSpec[] = [
  attr({ name: "beta", type: "number", section: "extra" }),
  attr({ name: "alpha", type: "text", section: "general" }),
];

describe("AttributeTable", () => {
  it("renders one row per attribute with the seven required columns", () => {
    render(
      <AttributeTable attributes={ATTRIBUTES} selected={null} onSelect={vi.fn()} />
    );
    expect(screen.getByTestId("attribute-table-row-alpha")).toBeTruthy();
    expect(screen.getByTestId("attribute-table-row-beta")).toBeTruthy();
    for (const column of [
      "name", "type", "section", "required", "visible", "audience", "origin",
    ]) {
      expect(screen.getByTestId(`attribute-table-sort-${column}`)).toBeTruthy();
    }
  });

  it("calls onSelect when a row is clicked", () => {
    const onSelect = vi.fn();
    render(
      <AttributeTable attributes={ATTRIBUTES} selected={null} onSelect={onSelect} />
    );
    fireEvent.click(screen.getByTestId("attribute-table-row-alpha"));
    expect(onSelect).toHaveBeenCalledWith("alpha");
  });

  it("sorts by name ascending by default (client-side, unpersisted)", () => {
    render(
      <AttributeTable attributes={ATTRIBUTES} selected={null} onSelect={vi.fn()} />
    );
    const rows = screen.getAllByTestId(/^attribute-table-row-[a-z]+$/);
    expect(rows.map((row) => row.getAttribute("data-testid"))).toEqual([
      "attribute-table-row-alpha",
      "attribute-table-row-beta",
    ]);
  });

  it("sorts by a clicked column header, toggling direction on a second click", () => {
    render(
      <AttributeTable attributes={ATTRIBUTES} selected={null} onSelect={vi.fn()} />
    );
    fireEvent.click(screen.getByTestId("attribute-table-sort-name"));
    let rows = screen.getAllByTestId(/^attribute-table-row-[a-z]+$/);
    expect(rows.map((row) => row.getAttribute("data-testid"))).toEqual([
      "attribute-table-row-beta",
      "attribute-table-row-alpha",
    ]);

    fireEvent.click(screen.getByTestId("attribute-table-sort-name"));
    rows = screen.getAllByTestId(/^attribute-table-row-[a-z]+$/);
    expect(rows.map((row) => row.getAttribute("data-testid"))).toEqual([
      "attribute-table-row-alpha",
      "attribute-table-row-beta",
    ]);
  });

  it("shows the origin from the origins map", () => {
    render(
      <AttributeTable
        attributes={ATTRIBUTES}
        origins={{ alpha: "workspace_only", beta: "global_customized" }}
        selected={null}
        onSelect={vi.fn()}
      />
    );
    expect(screen.getByTestId("attribute-table-row-alpha").textContent).toContain(
      "workspace_only"
    );
    expect(screen.getByTestId("attribute-table-row-beta").textContent).toContain(
      "global_customized"
    );
  });

  it("defaults to a global origin when no origins map is given (global scope)", () => {
    render(
      <AttributeTable attributes={ATTRIBUTES} selected={null} onSelect={vi.fn()} />
    );
    expect(screen.getByTestId("attribute-table-row-alpha").textContent).toContain(
      "global"
    );
  });

  it("renders a type icon for every row (Task 12)", () => {
    render(
      <AttributeTable attributes={ATTRIBUTES} selected={null} onSelect={vi.fn()} />
    );
    expect(screen.getByTestId("attribute-table-row-alpha-type-icon")).toBeTruthy();
    expect(screen.getByTestId("attribute-table-row-beta-type-icon")).toBeTruthy();
  });
});
