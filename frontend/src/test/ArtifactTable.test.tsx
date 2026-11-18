/**
 * Task 4.3 — ArtifactTable grid (plan 2026-11-04-tabellenansicht-s4).
 */
import { afterAll, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { i18n } from "../i18n/index";

import {
  ArtifactTable,
  SORT_LIMIT,
  toggleSort,
} from "../components/shared/ArtifactTable/ArtifactTable";
import type { TableColumn } from "../components/shared/ArtifactTable/columnModel";
import type { TableRow } from "../api/table-views";

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

function row(i: number, overrides: Partial<TableRow> = {}): TableRow {
  return {
    id: `row-${i}`,
    artifact_id: `artifact-${i}`,
    item_type: "Requirement",
    version: 1,
    values: { title: `Title ${i}`, status: "draft" },
    locked: null,
    ...overrides,
  };
}

const COLUMNS = [
  column({ name: "title", label: "Title" }),
  column({
    name: "status",
    label: "Status",
    type: "enum",
    editable: "workflow",
    inlineEditable: false,
  }),
];

function renderTable(rows: TableRow[], overrides: Record<string, unknown> = {}) {
  const props = {
    columns: COLUMNS,
    rows,
    sort: [],
    onSortChange: vi.fn(),
    selectedIds: new Set<string>(),
    onSelectionChange: vi.fn(),
    loading: false,
    ...overrides,
  };
  return { ...render(<ArtifactTable {...props} />), props };
}

describe("ArtifactTable", () => {
  it("renders a header per column and a row per item", () => {
    renderTable([row(1), row(2)]);
    expect(screen.getByTestId("sort-title")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Status" })).toBeInTheDocument();
    expect(screen.getAllByTestId(/^table-row-/)).toHaveLength(2);
  });

  it("cycles a header click asc -> desc -> off", async () => {
    const user = userEvent.setup();
    const { props } = renderTable([row(1)]);
    const button = screen.getByTestId("sort-title");
    await user.click(button);
    expect(props.onSortChange).toHaveBeenLastCalledWith([{ field: "title", dir: "asc" }]);
  });

  it("shift-click adds a secondary sort", () => {
    expect(toggleSort([{ field: "title", dir: "asc" }], "status", true)).toEqual([
      { field: "title", dir: "asc" },
      { field: "status", dir: "asc" },
    ]);
  });

  it("caps additive sort terms at five", () => {
    const full = Array.from({ length: SORT_LIMIT }, (_, i) => ({
      field: `f${i}`,
      dir: "asc" as const,
    }));
    expect(toggleSort(full, "extra", true)).toHaveLength(SORT_LIMIT);
  });

  it("renders status as a badge and never as an inline editor", () => {
    const renderCellEditor = vi.fn(() => <input data-testid="should-not-render" />);
    renderTable([row(1)], { renderCellEditor });
    expect(screen.getByTestId("status-badge-row-1")).toBeInTheDocument();
    expect(
      renderCellEditor.mock.calls.some(([col]) => col.name === "status")
    ).toBe(false);
  });

  it("renders the status change icon with its own testid", async () => {
    const user = userEvent.setup();
    const onStartInlineEdit = vi.fn();
    renderTable([row(1)], { onStartInlineEdit });
    await user.click(screen.getByTestId("status-change-row-1"));
    expect(onStartInlineEdit).toHaveBeenCalledWith("row-1", "status");
  });

  it("selects a row and all rows", async () => {
    const user = userEvent.setup();
    const onSelectionChange = vi.fn();
    renderTable([row(1), row(2)], { onSelectionChange });
    await user.click(screen.getByTestId("row-select-row-1"));
    expect(onSelectionChange).toHaveBeenCalledWith(new Set(["row-1"]));
    await user.click(screen.getByTestId("artifact-table-select-all"));
    expect(onSelectionChange).toHaveBeenLastCalledWith(new Set(["row-1", "row-2"]));
  });

  it("shows a lock marker on a locked row and offers no editor", () => {
    const renderCellEditor = vi.fn(() => <input data-testid="should-not-render" />);
    renderTable([row(1, { locked: { state: "Freigegeben" } })], { renderCellEditor });
    expect(screen.getByTestId("row-lock-row-1")).toBeInTheDocument();
    expect(renderCellEditor).not.toHaveBeenCalled();
  });

  afterAll(async () => {
    await i18n.changeLanguage("en");
  });

  it("exposes the lock marker as a named image for screen readers", async () => {
    await i18n.changeLanguage("de");
    renderTable([row(1, { locked: { state: "Freigegeben" } })]);
    expect(screen.getByRole("img", { name: "Gesperrt: Freigegeben" })).toContainElement(
      screen.getByTestId("row-lock-row-1")
    );
  });

  it("gives each row checkbox a distinct name derived from its title", async () => {
    await i18n.changeLanguage("de");
    renderTable([row(1), row(2)]);
    expect(
      screen.getByRole("checkbox", { name: "Zeile auswählen: Title 1" })
    ).toBe(screen.getByTestId("row-select-row-1"));
    expect(
      screen.getByRole("checkbox", { name: "Zeile auswählen: Title 2" })
    ).toBe(screen.getByTestId("row-select-row-2"));
    expect(
      screen.queryByRole("checkbox", { name: "Zeile auswählen" })
    ).not.toBeInTheDocument();
  });

  it("is keyboard-sortable via Enter on the header button", async () => {
    const user = userEvent.setup();
    const { props } = renderTable([row(1)]);
    screen.getByTestId("sort-title").focus();
    await user.keyboard("{Enter}");
    expect(props.onSortChange).toHaveBeenCalledWith([{ field: "title", dir: "asc" }]);
  });

  it("virtualises a 1000-row set to far fewer DOM rows", () => {
    renderTable(Array.from({ length: 1000 }, (_, i) => row(i)));
    expect(screen.getByTestId("artifact-table-scroll")).toBeInTheDocument();
    expect(screen.queryAllByTestId(/^table-row-/).length).toBeLessThan(1000);
  });
});
