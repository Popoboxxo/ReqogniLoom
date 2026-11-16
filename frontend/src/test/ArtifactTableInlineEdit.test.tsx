/**
 * Task 4.8 — inline cell edit via the single-item path
 * (plan 2026-11-04-tabellenansicht-s4).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../i18n/index";

const updateRequirement = vi.fn();
const bulkUpdate = vi.fn();

vi.mock("../api/requirements", () => ({
  requirementsApi: { update: (...a: unknown[]) => updateRequirement(...a) },
}));
vi.mock("../api/table-views", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/table-views")>();
  return {
    ...actual,
    tableApi: {
      query: vi.fn(),
      bulkUpdate: (...a: unknown[]) => bulkUpdate(...a),
      bulkTransition: vi.fn(),
    },
  };
});

import {
  InlineCellEditor,
  updateCellValue,
} from "../components/shared/ArtifactTable/InlineCellEditor";
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

const ROW: TableRow = {
  id: "row-1",
  artifact_id: "artifact-1",
  item_type: "Requirement",
  version: 7,
  values: { title: "Old", status: "draft" },
  locked: null,
};

describe("InlineCellEditor", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateRequirement.mockResolvedValue({ id: "row-1", version: 8 });
  });

  it("never opens an editor for the status column", () => {
    const { container } = render(
      <InlineCellEditor
        column={column({ name: "status", type: "enum", inlineEditable: false })}
        row={ROW}
        onSave={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("saves a text cell on Enter via the single-item API, not bulk", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InlineCellEditor column={column({ name: "title" })} row={ROW} onSave={onSave} onCancel={vi.fn()} />
    );
    const input = screen.getByTestId("inline-input-title");
    await user.clear(input);
    await user.type(input, "New{Enter}");
    expect(onSave).toHaveBeenCalledWith("New");
    expect(bulkUpdate).not.toHaveBeenCalled();

    await updateCellValue(ROW, "title", "New");
    expect(updateRequirement).toHaveBeenCalledWith("row-1", { title: "New" }, 7);
    expect(bulkUpdate).not.toHaveBeenCalled();
  });

  it("cancels on Escape without a request", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    const onCancel = vi.fn();
    render(
      <InlineCellEditor column={column({ name: "title" })} row={ROW} onSave={onSave} onCancel={onCancel} />
    );
    await user.type(screen.getByTestId("inline-input-title"), "{Escape}");
    expect(onCancel).toHaveBeenCalled();
    expect(onSave).not.toHaveBeenCalled();
  });

  it("keeps the editor open with a server validation message", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue({
      error: { code: "VALIDATION_ERROR", message: "Validation failed", details: [{ field: "title", errors: ["too long"] }] },
    });
    render(
      <InlineCellEditor column={column({ name: "title" })} row={ROW} onSave={onSave} onCancel={vi.fn()} />
    );
    await user.type(screen.getByTestId("inline-input-title"), "X{Enter}");
    expect(await screen.findByTestId("inline-error")).toHaveTextContent("too long");
    expect(screen.getByTestId("inline-input-title")).toBeInTheDocument();
  });

  it("shows the reload hint on a conflict", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockRejectedValue({ error: { code: "CONFLICT", message: "stale" } });
    render(
      <InlineCellEditor column={column({ name: "title" })} row={ROW} onSave={onSave} onCancel={vi.fn()} />
    );
    await user.type(screen.getByTestId("inline-input-title"), "X{Enter}");
    await waitFor(() => expect(screen.getByTestId("inline-reload")).toBeInTheDocument());
  });

  it("cannot enter edit on a locked row", () => {
    const { container } = render(
      <InlineCellEditor
        column={column({ name: "title" })}
        row={{ ...ROW, locked: { state: "Freigegeben" } }}
        onSave={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("uses an enum select for an enum cell", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn().mockResolvedValue(undefined);
    render(
      <InlineCellEditor
        column={column({
          name: "category",
          type: "enum",
          options: [{ value: "func", label_de: "Funktional", label_en: "Functional" }],
        })}
        row={{ ...ROW, values: { category: "" } }}
        onSave={onSave}
        onCancel={vi.fn()}
      />
    );
    await user.selectOptions(screen.getByTestId("inline-input-category"), "func");
    expect(onSave).toHaveBeenCalledWith("func");
  });
});
