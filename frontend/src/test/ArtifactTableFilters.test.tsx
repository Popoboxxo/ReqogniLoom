/**
 * Task 4.4 — type-aware filters and chips
 * (plan 2026-11-04-tabellenansicht-s4).
 */
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../i18n/index";

import { ActiveFilterChips } from "../components/shared/ArtifactTable/ActiveFilterChips";
import { ColumnFilterPopover } from "../components/shared/ArtifactTable/ColumnFilterPopover";
import type { TableColumn } from "../components/shared/ArtifactTable/columnModel";
import type { FilterConstraint } from "../api/table-views";
import {
  constraintsFor,
  withConstraints,
} from "../components/shared/ArtifactTable/filters";

function column(overrides: Partial<TableColumn>): TableColumn {
  return {
    name: "title",
    type: "text",
    kind: "core",
    label: "Title",
    editable: true,
    filterable: true,
    sortable: true,
    inlineEditable: true,
    ...overrides,
  };
}


function Harness({
  column,
  onChange,
}: {
  column: TableColumn;
  onChange: (next: FilterConstraint[]) => void;
}): JSX.Element {
  const [constraints, setConstraints] = useState<FilterConstraint[]>([]);
  return (
    <ColumnFilterPopover
      column={column}
      constraints={constraints}
      onChange={(next) => {
        setConstraints(next);
        onChange(next);
      }}
      onClose={vi.fn()}
    />
  );
}

const ENUM = column({
  name: "status",
  label: "Status",
  type: "enum",
  options: [
    { value: "draft", label_de: "Entwurf", label_en: "Draft" },
    { value: "approved", label_de: "Freigegeben", label_en: "Approved" },
  ],
});

describe("ColumnFilterPopover", () => {
  it("emits in with the selected enum values", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ColumnFilterPopover
        column={ENUM}
        constraints={[]}
        onChange={onChange}
        onClose={vi.fn()}
      />
    );
    await user.click(screen.getByTestId("filter-option-status-draft"));
    expect(onChange).toHaveBeenLastCalledWith([{ op: "in", value: ["draft"] }]);
  });

  it("emits contains for a text column", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness column={column({ name: "title" })} onChange={onChange} />);
    await user.type(screen.getByTestId("filter-title-contains"), "abc");
    expect(onChange).toHaveBeenLastCalledWith([{ op: "contains", value: "abc" }]);
  });

  it("emits gte and lte as a list for a date range", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness column={column({ name: "due", type: "date" })} onChange={onChange} />);
    await user.type(screen.getByTestId("filter-due-gte"), "2026-01-01");
    await user.type(screen.getByTestId("filter-due-lte"), "2026-12-31");
    expect(onChange).toHaveBeenLastCalledWith([
      { op: "gte", value: "2026-01-01" },
      { op: "lte", value: "2026-12-31" },
    ]);
  });

  it("emits a two-element list for a number range", async () => {
    const onChange = vi.fn();
    render(
      <ColumnFilterPopover
        column={column({ name: "score", type: "number" })}
        constraints={[
          { op: "gte", value: 1 },
          { op: "lte", value: 5 },
        ]}
        onChange={onChange}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByTestId("filter-score-gte")).toHaveValue(1);
    expect(screen.getByTestId("filter-score-lte")).toHaveValue(5);
  });

  it("removes the constraint on the boolean 'all' choice", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ColumnFilterPopover
        column={column({ name: "active", type: "boolean" })}
        constraints={[{ op: "eq", value: true }]}
        onChange={onChange}
        onClose={vi.fn()}
      />
    );
    await user.selectOptions(screen.getByTestId("filter-active-boolean"), "all");
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it("emits in for an actor column", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(<Harness column={column({ name: "owner", type: "actor" })} onChange={onChange} />);
    await user.type(screen.getByTestId("filter-owner-in"), "u1,u2");
    expect(onChange).toHaveBeenLastCalledWith([{ op: "in", value: ["u1", "u2"] }]);
  });

  it("renders nothing for a non-filterable column", () => {
    const { container } = render(
      <ColumnFilterPopover
        column={column({ name: "custom", kind: "extended", filterable: false })}
        constraints={[]}
        onChange={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("closes on Escape", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    render(
      <ColumnFilterPopover
        column={column({ name: "title" })}
        constraints={[]}
        onChange={vi.fn()}
        onClose={onClose}
      />
    );
    screen.getByTestId("filter-title-contains").focus();
    await user.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });
});

describe("ActiveFilterChips", () => {
  it("shows one chip per constraint and removes individually", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    render(
      <ActiveFilterChips
        columns={[column({ name: "score", type: "number" })]}
        filters={{ score: [{ op: "gte", value: 1 }, { op: "lte", value: 5 }] }}
        onChange={onChange}
      />
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    await user.click(screen.getByTestId("filter-chip-remove-score-0"));
    expect(onChange).toHaveBeenCalledWith({ score: { op: "lte", value: 5 } });
  });
});

describe("filters helpers", () => {
  it("removes the key when the constraint list is empty", () => {
    expect(withConstraints({ title: { op: "contains", value: "x" } }, "title", [])).toEqual(
      {}
    );
    expect(constraintsFor({ title: { op: "contains", value: "x" } }, "title")).toEqual([
      { op: "contains", value: "x" },
    ]);
  });
});
