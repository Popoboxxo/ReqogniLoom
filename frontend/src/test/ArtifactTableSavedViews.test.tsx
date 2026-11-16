/**
 * Task 4.6 — saved view bar (plan 2026-11-04-tabellenansicht-s4).
 */
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import "../i18n/index";
import { i18n } from "../i18n/index";

const list = vi.fn();
const create = vi.fn();
const update = vi.fn();
const remove = vi.fn();
const apply = vi.fn();

vi.mock("../api/table-views", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/table-views")>();
  return {
    ...actual,
    savedViewsApi: {
      list: (...a: unknown[]) => list(...a),
      create: (...a: unknown[]) => create(...a),
      update: (...a: unknown[]) => update(...a),
      remove: (...a: unknown[]) => remove(...a),
      apply: (...a: unknown[]) => apply(...a),
    },
  };
});

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "me", username: "me", email: "", first_name: "", last_name: "", is_active: true, tenant_id: null, roles: ["editor"] },
    isTenantAdmin: false,
  }),
}));

import { SavedViewBar } from "../components/shared/ArtifactTable/SavedViewBar";

const STATE = { columns: [{ field: "title", order: 0 }], filters: {}, sort: [] };

function view(overrides: Record<string, unknown> = {}) {
  return {
    id: "v1",
    workspace_id: "ws",
    item_type: "Requirement",
    owner_id: "me",
    name: "My view",
    visibility: "private",
    version: 1,
    columns: [],
    filters: {},
    sort: [],
    ...overrides,
  };
}

function renderBar(onApply = vi.fn()) {
  render(
    <SavedViewBar workspaceId="ws" itemType="Requirement" current={STATE} onApply={onApply} />
  );
  return onApply;
}

beforeAll(async () => {
  await i18n.changeLanguage("en");
});

describe("SavedViewBar", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    list.mockResolvedValue([
      view(),
      view({ id: "v2", name: "Shared", owner_id: "other", visibility: "workspace" }),
    ]);
    apply.mockResolvedValue({ count: 0, results: [], next: null, previous: null, warnings: [] });
  });

  it("lists private and workspace views", async () => {
    renderBar();
    await waitFor(() => expect(screen.getByText("My view")).toBeInTheDocument());
    expect(screen.getByText(/Shared/)).toBeInTheDocument();
  });

  it("saves the current state from the dialog", async () => {
    const user = userEvent.setup();
    create.mockResolvedValue(view({ id: "v3", name: "New" }));
    renderBar();
    await waitFor(() => expect(list).toHaveBeenCalled());
    await user.click(screen.getByTestId("saved-view-save"));
    await user.type(screen.getByTestId("saved-view-name"), "New");
    await user.click(screen.getByTestId("saved-view-submit"));
    expect(create).toHaveBeenCalledWith("ws", "Requirement", {
      name: "New",
      visibility: "private",
      columns: STATE.columns,
      filters: {},
      sort: [],
    });
  });

  it("shows a name conflict inside the dialog", async () => {
    const user = userEvent.setup();
    create.mockRejectedValue({ error: { code: "VALIDATION_ERROR", message: "Name exists" } });
    renderBar();
    await waitFor(() => expect(list).toHaveBeenCalled());
    await user.click(screen.getByTestId("saved-view-save"));
    await user.type(screen.getByTestId("saved-view-name"), "Dup");
    await user.click(screen.getByTestId("saved-view-submit"));
    await waitFor(() =>
      expect(screen.getByTestId("saved-view-dialog-error")).toHaveTextContent("Name exists")
    );
  });

  it("hides edit and delete for a non-owner view", async () => {
    const user = userEvent.setup();
    renderBar();
    await waitFor(() => expect(screen.getByText(/Shared/)).toBeInTheDocument());
    await user.selectOptions(screen.getByTestId("saved-view-select"), "v2");
    expect(screen.queryByTestId("saved-view-update")).not.toBeInTheDocument();
    expect(screen.queryByTestId("saved-view-delete")).not.toBeInTheDocument();
  });

  it("asks for confirmation before deleting", async () => {
    const user = userEvent.setup();
    remove.mockResolvedValue(undefined);
    renderBar();
    await waitFor(() => expect(screen.getByText("My view")).toBeInTheDocument());
    await user.selectOptions(screen.getByTestId("saved-view-select"), "v1");
    await user.click(screen.getByTestId("saved-view-delete"));
    expect(screen.getByTestId("saved-view-delete-confirm")).toBeInTheDocument();
    expect(remove).not.toHaveBeenCalled();
    await user.click(screen.getByTestId("saved-view-delete-confirm-confirm"));
    await waitFor(() => expect(remove).toHaveBeenCalledWith("v1"));
  });

  it("calls onApply and shows the server's stale-view warnings", async () => {
    const user = userEvent.setup();
    apply.mockResolvedValue({
      count: 0,
      results: [],
      next: null,
      previous: null,
      warnings: ["custom_field"],
    });
    const onApply = renderBar();
    await waitFor(() => expect(screen.getByText("My view")).toBeInTheDocument());
    await user.selectOptions(screen.getByTestId("saved-view-select"), "v1");
    await waitFor(() => expect(onApply).toHaveBeenCalled());
    expect(onApply.mock.calls[0][0].id).toBe("v1");
    expect(screen.getByTestId("saved-view-warnings")).toHaveTextContent("custom_field");
  });

  it("closes the dialog on Escape", async () => {
    const user = userEvent.setup();
    renderBar();
    await waitFor(() => expect(list).toHaveBeenCalled());
    await user.click(screen.getByTestId("saved-view-save"));
    expect(screen.getByTestId("saved-view-dialog")).toBeInTheDocument();
    await user.keyboard("{Escape}");
    await waitFor(() =>
      expect(screen.queryByTestId("saved-view-dialog")).not.toBeInTheDocument()
    );
  });
});
