/**
 * Task 4.7 — bulk action bar (plan 2026-11-04-tabellenansicht-s4).
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
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

const WS = "11111111-1111-1111-1111-111111111111";

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
    bulkUpdate.mockResolvedValue({ committed: true, updated: [], failed: [] });
    getTransitions.mockResolvedValue({
      current_state: "draft",
      states: ["draft", "approved"],
      allowed_transitions: [{ target_state: "approved", requires_change_reason: true, signature_gate: false }],
    });
  });

  it("offers only inline-editable columns in the edit dialog", async () => {
    const user = userEvent.setup();
    render(<BulkActionBar workspaceId={WS} selectedRows={[row(1)]} columns={COLUMNS} onDone={vi.fn()} />);
    await user.click(screen.getByTestId("bulk-edit-fields"));
    expect(screen.getByTestId("bulk-field-title")).toBeInTheDocument();
    expect(screen.queryByTestId("bulk-field-status")).not.toBeInTheDocument();
    expect(screen.queryByTestId("bulk-field-owner")).not.toBeInTheDocument();
  });

  it("sends one entry per row with its own expected_version and the change reason", async () => {
    const user = userEvent.setup();
    render(
      <BulkActionBar
        workspaceId={WS}
        selectedRows={[row(1), row(2)]}
        columns={COLUMNS}
        onDone={vi.fn()}
      />
    );
    await user.click(screen.getByTestId("bulk-edit-fields"));
    await user.type(screen.getByTestId("bulk-field-title"), "New");
    await user.type(screen.getByTestId("bulk-change-reason"), "because");
    await user.click(screen.getByTestId("bulk-submit"));
    expect(bulkUpdate).toHaveBeenCalledWith({
      workspace_id: WS,
      entries: [
        {
          artifact_id: "artifact-1",
          expected_version: 4,
          fields: { title: "New", change_reason: "because" },
        },
        {
          artifact_id: "artifact-2",
          expected_version: 5,
          fields: { title: "New", change_reason: "because" },
        },
      ],
    });
  });

  it("lists every failing artifact on an all-or-nothing refusal and reports no success", async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    bulkUpdate.mockResolvedValue({
      committed: false,
      updated: [],
      failed: [
        { index: 0, artifact_id: "artifact-1", code: "VALIDATION_ERROR", message: "title" },
        { index: 1, artifact_id: "artifact-2", code: "CONFLICT", message: "version" },
      ],
    });
    render(
      <BulkActionBar workspaceId={WS} selectedRows={[row(1), row(2)]} columns={COLUMNS} onDone={onDone} />
    );
    await user.click(screen.getByTestId("bulk-edit-fields"));
    await user.type(screen.getByTestId("bulk-field-title"), "New");
    await user.click(screen.getByTestId("bulk-submit"));
    const failures = await screen.findByTestId("bulk-failures");
    expect(failures).toHaveTextContent("artifact-1");
    expect(failures).toHaveTextContent("artifact-2");
    expect(failures).toHaveTextContent("version");
    expect(screen.queryByTestId("bulk-result-message")).not.toBeInTheDocument();
    expect(screen.getByTestId("bulk-edit-dialog")).toBeInTheDocument();
    expect(onDone).not.toHaveBeenCalled();
  });

  it("commits, closes the dialog and refreshes on a 200 without errors", async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    bulkUpdate.mockResolvedValue({
      committed: true,
      updated: [
        { artifact_id: "artifact-1", version: 5 },
        { artifact_id: "artifact-2", version: 6 },
      ],
      failed: [],
    });
    render(
      <BulkActionBar workspaceId={WS} selectedRows={[row(1), row(2)]} columns={COLUMNS} onDone={onDone} />
    );
    await user.click(screen.getByTestId("bulk-edit-fields"));
    await user.type(screen.getByTestId("bulk-field-title"), "New");
    await user.click(screen.getByTestId("bulk-submit"));
    await waitFor(() => expect(onDone).toHaveBeenCalled());
    expect(screen.queryByTestId("bulk-edit-dialog")).not.toBeInTheDocument();
  });

  it("offers a reload on an all-conflict failure", async () => {
    const user = userEvent.setup();
    bulkUpdate.mockResolvedValue({
      committed: false,
      updated: [],
      failed: [{ index: 0, artifact_id: "artifact-1", code: "CONFLICT", message: "version" }],
    });
    render(
      <BulkActionBar workspaceId={WS} selectedRows={[row(1)]} columns={COLUMNS} onDone={vi.fn()} />
    );
    await user.click(screen.getByTestId("bulk-edit-fields"));
    await user.type(screen.getByTestId("bulk-field-title"), "New");
    await user.click(screen.getByTestId("bulk-submit"));
    expect(await screen.findByTestId("bulk-reload")).toBeInTheDocument();
  });

  it("disables submit above 100 selected rows with a hint", async () => {
    const user = userEvent.setup();
    const rows = Array.from({ length: BULK_MAX_ITEMS + 1 }, (_, i) => row(i));
    render(
      <BulkActionBar workspaceId={WS} selectedRows={rows} columns={COLUMNS} onDone={vi.fn()} />
    );
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
    render(<BulkActionBar workspaceId={WS} selectedRows={[row(1), row(2)]} columns={COLUMNS} onDone={vi.fn()} />);
    await user.click(screen.getByTestId("bulk-change-status"));
    await waitFor(() =>
      expect(screen.getByTestId("bulk-target-state")).toHaveTextContent("review")
    );
    expect(screen.getByTestId("bulk-target-state")).not.toHaveTextContent("approved");
  });

  it("requires a change reason for a status change", async () => {
    const user = userEvent.setup();
    render(<BulkActionBar workspaceId={WS} selectedRows={[row(1)]} columns={COLUMNS} onDone={vi.fn()} />);
    await user.click(screen.getByTestId("bulk-change-status"));
    await waitFor(() => expect(screen.getByTestId("bulk-target-state")).not.toBeDisabled());
    await user.selectOptions(screen.getByTestId("bulk-target-state"), "approved");
    expect(screen.getByTestId("bulk-transition-submit")).toBeDisabled();
    await user.type(screen.getByTestId("bulk-status-change-reason"), "because");
    expect(screen.getByTestId("bulk-transition-submit")).not.toBeDisabled();
  });

  it("posts the transition body the backend declares (no workspace_id)", async () => {
    const user = userEvent.setup();
    const onDone = vi.fn();
    bulkTransition.mockResolvedValue({
      transitioned: [
        { artifact_id: "artifact-1", state: "approved" },
        { artifact_id: "artifact-2", state: "approved" },
      ],
      failed: [],
    });
    render(
      <BulkActionBar workspaceId={WS} selectedRows={[row(1), row(2)]} columns={COLUMNS} onDone={onDone} />
    );
    await user.click(screen.getByTestId("bulk-change-status"));
    await waitFor(() => expect(screen.getByTestId("bulk-target-state")).not.toBeDisabled());
    await user.selectOptions(screen.getByTestId("bulk-target-state"), "approved");
    await user.type(screen.getByTestId("bulk-status-change-reason"), "because");
    await user.click(screen.getByTestId("bulk-transition-submit"));

    await waitFor(() => expect(bulkTransition).toHaveBeenCalled());
    const body = bulkTransition.mock.calls[0][0];
    expect(body).toEqual({
      item_type: "Requirement",
      ids: ["artifact-1", "artifact-2"],
      to_state: "approved",
      change_reason: "because",
    });
    expect(body).not.toHaveProperty("workspace_id");
    expect(onDone).toHaveBeenCalled();
  });

  it("keeps failed transition rows visible with their message", async () => {
    const user = userEvent.setup();
    bulkTransition.mockResolvedValue({
      transitioned: [{ artifact_id: "artifact-1", state: "approved" }],
      failed: [
        { index: 1, artifact_id: "artifact-2", code: "FORBIDDEN", message: "no edge" },
      ],
    });
    render(
      <BulkActionBar workspaceId={WS} selectedRows={[row(1), row(2)]} columns={COLUMNS} onDone={vi.fn()} />
    );
    await user.click(screen.getByTestId("bulk-change-status"));
    await waitFor(() => expect(screen.getByTestId("bulk-target-state")).not.toBeDisabled());
    await user.selectOptions(screen.getByTestId("bulk-target-state"), "approved");
    await user.type(screen.getByTestId("bulk-status-change-reason"), "because");
    await user.click(screen.getByTestId("bulk-transition-submit"));
    const failures = await screen.findByTestId("bulk-failures");
    expect(failures).toHaveTextContent("artifact-2");
    expect(failures).toHaveTextContent("no edge");
  });

  // Regression guard for the e2e "bulk transition of two rows" flow: the parent
  // rebuilds `selectedRows` on every render, so a re-render used to reset the
  // chosen target state, refetch the transitions and leave the submit button
  // disabled — the POST the guardrail waits for never happened.
  it("keeps the chosen target state across a parent re-render", async () => {
    const user = userEvent.setup();
    bulkTransition.mockResolvedValue({
      transitioned: [
        { artifact_id: "artifact-1", state: "approved" },
        { artifact_id: "artifact-2", state: "approved" },
      ],
      failed: [],
    });

    function Harness(): JSX.Element {
      const [tick, setTick] = useState(0);
      // New array identity every render, identical content.
      const selected = [row(1), row(2)];
      return (
        <div data-tick={tick}>
          <button type="button" data-testid="parent-rerender" onClick={() => setTick((n) => n + 1)}>
            rerender
          </button>
          <BulkActionBar
            workspaceId={WS}
            selectedRows={selected}
            columns={COLUMNS}
            onDone={vi.fn()}
          />
        </div>
      );
    }

    render(<Harness />);
    await user.click(screen.getByTestId("bulk-change-status"));
    await waitFor(() =>
      expect(screen.getByTestId("bulk-target-state")).not.toBeDisabled()
    );
    await user.selectOptions(screen.getByTestId("bulk-target-state"), "approved");
    await user.type(screen.getByTestId("bulk-status-change-reason"), "because");

    await user.click(screen.getByTestId("parent-rerender"));

    expect(screen.getByTestId("bulk-target-state")).toHaveValue("approved");
    expect(screen.getByTestId("bulk-status-change-reason")).toHaveValue("because");
    expect(screen.getByTestId("bulk-transition-submit")).not.toBeDisabled();

    await user.click(screen.getByTestId("bulk-transition-submit"));
    await waitFor(() => expect(bulkTransition).toHaveBeenCalledTimes(1));
    expect(bulkTransition.mock.calls[0][0]).toEqual({
      item_type: "Requirement",
      ids: ["artifact-1", "artifact-2"],
      to_state: "approved",
      change_reason: "because",
    });
  });
});
