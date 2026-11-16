/**
 * Task 4.7 — bulk action bar (plan 2026-11-04-tabellenansicht-s4).
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../i18n/index";
import { i18n } from "../i18n/index";

const bulkUpdate = vi.fn();
const bulkTransition = vi.fn();
const getTransitions = vi.fn();

vi.mock("../api/table-views", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/table-views")>();
  return {
    ...actual,
    tableApi: {
      query: vi.fn(),
      bulkUpdate: (...a: unknown[]) => bulkUpdate(...a),
      bulkTransition: (...a: unknown[]) => bulkTransition(...a),
    },
  };
});

vi.mock("../api/workflow-transitions", () => ({
  workflowTransitionsApi: {
    getTransitions: (...a: unknown[]) => getTransitions(...a),
  },
}));

import { BulkActionBar, BULK_MAX_ITEMS } from "../components/shared/ArtifactTable/BulkActionBar";
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

function row(i: number): TableRow {
  return {
    id: `row-${i}`,
    artifact_id: `artifact-${i}`,
    item_type: "Requirement",
    version: 3 + i,
    values: { title: `T${i}`, status: "draft" },
    locked: null,
  };
}

const COLUMNS = [
  column({ name: "title" }),
  column({ name: "status", type: "enum", editable: "workflow", inlineEditable: false }),
  column({ name: "owner", type: "user", editable: false, inlineEditable: false }),
];

beforeAll(async () => {
  await i18n.changeLanguage("en");
});

describe("BulkActionBar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    bulkUpdate.mockResolvedValue({ committed: true, mode: "atomic", updated: [], failed: [] });
    getTransitions.mockResolvedValue({
      current_state: "draft",
      states: ["draft", "approved"],
      allowed_transitions: [{ target_state: "approved", requires_change_reason: true, signature_gate: false }],
    });
  });

  it("offers only inline-editable columns in the edit dialog", async () => {
    const user = userEvent.setup();
    render(<BulkActionBar selectedRows={[row(1)]} columns={COLUMNS} onDone={vi.fn()} />);
    await user.click(screen.getByTestId("bulk-edit-fields"));
    expect(screen.getByTestId("bulk-field-title")).toBeInTheDocument();
    expect(screen.queryByTestId("bulk-field-status")).not.toBeInTheDocument();
    expect(screen.queryByTestId("bulk-field-owner")).not.toBeInTheDocument();
  });

  it("sends each row's expected version and mode atomic by default", async () => {
    const user = userEvent.setup();
    render(
      <BulkActionBar selectedRows={[row(1), row(2)]} columns={COLUMNS} onDone={vi.fn()} />
    );
    await user.click(screen.getByTestId("bulk-edit-fields"));
    await user.type(screen.getByTestId("bulk-field-title"), "New");
    await user.click(screen.getByTestId("bulk-submit"));
    expect(bulkUpdate).toHaveBeenCalledWith({
      mode: "atomic",
      items: [
        { artifact_id: "artifact-1", expected_version: 4, fields: { title: "New" } },
        { artifact_id: "artifact-2", expected_version: 5, fields: { title: "New" } },
      ],
    });
  });

  it("lists every failing artifact on an atomic failure and reports no success", async () => {
    const user = userEvent.setup();
    bulkUpdate.mockResolvedValue({
      committed: false,
      mode: "atomic",
      updated: [],
      failed: [
        { index: 0, artifact_id: "artifact-1", code: "VALIDATION_ERROR", reason: "title" },
        { index: 1, artifact_id: "artifact-2", code: "CONFLICT", reason: "version" },
      ],
    });
    render(<BulkActionBar selectedRows={[row(1), row(2)]} columns={COLUMNS} onDone={vi.fn()} />);
    await user.click(screen.getByTestId("bulk-edit-fields"));
    await user.type(screen.getByTestId("bulk-field-title"), "New");
    await user.click(screen.getByTestId("bulk-submit"));
    const failures = await screen.findByTestId("bulk-failures");
    expect(failures).toHaveTextContent("artifact-1");
    expect(failures).toHaveTextContent("artifact-2");
    expect(screen.queryByTestId("bulk-result-message")).not.toBeInTheDocument();
  });

  it("reports counts and failures for a partial result", async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    bulkUpdate.mockResolvedValue({
      committed: true,
      mode: "partial",
      updated: [{ artifact_id: "artifact-1", id: "1", item_type: "Requirement", version: 5 }],
      failed: [
        { index: 1, artifact_id: "artifact-2", code: "CONFLICT", reason: "version" },
      ],
    });
    render(<BulkActionBar selectedRows={[row(1), row(2)]} columns={COLUMNS} onDone={onDone} />);
    await user.click(screen.getByTestId("bulk-edit-fields"));
    await user.type(screen.getByTestId("bulk-field-title"), "New");
    await user.click(screen.getByTestId("bulk-submit"));
    expect(await screen.findByTestId("bulk-result-message")).toBeInTheDocument();
    expect(onDone).toHaveBeenCalled();
  });

  it("offers a reload on an all-conflict failure", async () => {
    const user = userEvent.setup();
    bulkUpdate.mockResolvedValue({
      committed: false,
      mode: "atomic",
      updated: [],
      failed: [{ index: 0, artifact_id: "artifact-1", code: "CONFLICT", reason: "version" }],
    });
    render(<BulkActionBar selectedRows={[row(1)]} columns={COLUMNS} onDone={vi.fn()} />);
    await user.click(screen.getByTestId("bulk-edit-fields"));
    await user.type(screen.getByTestId("bulk-field-title"), "New");
    await user.click(screen.getByTestId("bulk-submit"));
    expect(await screen.findByTestId("bulk-reload")).toBeInTheDocument();
  });

  it("disables submit above 100 selected rows with a hint", async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: BULK_MAX_ITEMS + 1 }, (_, i) => row(i));
    render(<BulkActionBar selectedRows={rows} columns={COLUMNS} onDone={vi.fn()} />);
    await user.click(screen.getByTestId("bulk-edit-fields"));
    await user.type(screen.getByTestId("bulk-field-title"), "New");
    expect(screen.getByTestId("bulk-too-many")).toBeInTheDocument();
    expect(screen.getByTestId("bulk-submit")).toBeDisabled();
  });

  it("lists only states reachable from every selected row", async () => {
    const user = userEvent.setup();
    getTransitions
      .mockResolvedValueOnce({
        current_state: "draft",
        states: ["draft", "review", "approved"],
        allowed_transitions: [
          { target_state: "review", requires_change_reason: false, signature_gate: false },
          { target_state: "approved", requires_change_reason: false, signature_gate: false },
        ],
      })
      .mockResolvedValueOnce({
        current_state: "draft",
        states: ["draft", "review", "approved"],
        allowed_transitions: [
          { target_state: "review", requires_change_reason: false, signature_gate: false },
        ],
      });
    render(<BulkActionBar selectedRows={[row(1), row(2)]} columns={COLUMNS} onDone={vi.fn()} />);
    await user.click(screen.getByTestId("bulk-change-status"));
    await waitFor(() =>
      expect(screen.getByTestId("bulk-target-state")).toHaveTextContent("review")
    );
    expect(screen.getByTestId("bulk-target-state")).not.toHaveTextContent("approved");
  });

  it("requires a change reason for a status change", async () => {
    const user = userEvent.setup();
    render(<BulkActionBar selectedRows={[row(1)]} columns={COLUMNS} onDone={vi.fn()} />);
    await user.click(screen.getByTestId("bulk-change-status"));
    await waitFor(() => expect(screen.getByTestId("bulk-target-state")).not.toBeDisabled());
    await user.selectOptions(screen.getByTestId("bulk-target-state"), "approved");
    expect(screen.getByTestId("bulk-transition-submit")).toBeDisabled();
    await user.type(screen.getByTestId("bulk-status-change-reason"), "because");
    expect(screen.getByTestId("bulk-transition-submit")).not.toBeDisabled();
  });
});
