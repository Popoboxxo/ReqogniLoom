/**
 * Task 4.9 — composition, Requirements-page toggle (plan
 * 2026-11-04-tabellenansicht-s4).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import "../i18n/index";

const query = vi.fn();
const listViews = vi.fn();
const applyView = vi.fn();
const getState = vi.fn();
const putState = vi.fn();
const bulkUpdate = vi.fn();
const getWorkspace = vi.fn();

vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({
    user: { id: "me", username: "me", email: "", first_name: "", last_name: "", is_active: true, tenant_id: null, roles: ["editor"] },
    isTenantAdmin: false,
  }),
}));

vi.mock("../hooks/useActiveWorkspace", () => ({
  useActiveWorkspace: () => ({ id: "ws" }),
}));

vi.mock("../api/attribute-definitions", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/attribute-definitions")>();
  return {
    ...actual,
    attributeDefinitionsApi: {
      ...actual.attributeDefinitionsApi,
      getWorkspace: (...a: unknown[]) => getWorkspace(...a),
    },
  };
});

vi.mock("../api/table-views", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/table-views")>();
  return {
    ...actual,
    tableApi: {
      query: (...a: unknown[]) => query(...a),
      bulkUpdate: (...a: unknown[]) => bulkUpdate(...a),
      bulkTransition: vi.fn(),
    },
    savedViewsApi: {
      list: (...a: unknown[]) => listViews(...a),
      apply: (...a: unknown[]) => applyView(...a),
      get: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      remove: vi.fn(),
    },
    tableViewStateApi: {
      get: (...a: unknown[]) => getState(...a),
      put: (...a: unknown[]) => putState(...a),
    },
  };
});

import { ArtifactTableView } from "../components/shared/ArtifactTable/ArtifactTableView";
import {
  REQUIREMENT_VIEW_MODE_KEY,
  RequirementViewToggle,
  readRequirementViewMode,
  writeRequirementViewMode,
  type RequirementViewMode,
} from "../components/RequirementEditors/RequirementViewToggle";

const DEFINITION = {
  item_type: "Requirement",
  preset: "standard",
  is_customized: false,
  version: 1,
  origins: {},
  sections: [],
  attributes: [
    {
      name: "title", kind: "core", type: "text", widget_key: null, fields: [], options: [],
      required: false, visible: true, locked: false, editable: true, section: "basics",
      order: 0, label: { de: "Titel", en: "Title" }, help_text: { de: "", en: "" },
      default: null, validation: {}, ai_elicit: false, export: true, audience: "basic",
    },
    {
      name: "status", kind: "core", type: "enum", widget_key: null, fields: [],
      options: [{ value: "draft", label_de: "Entwurf", label_en: "Draft" }],
      required: false, visible: true, locked: false, editable: "workflow", section: "basics",
      order: 1, label: { de: "Status", en: "Status" }, help_text: { de: "", en: "" },
      default: null, validation: {}, ai_elicit: false, export: true, audience: "basic",
    },
  ],
};

function page(results: unknown[], count = results.length) {
  return { count, next: null, previous: null, results };
}

const ROW = {
  id: "row-1",
  artifact_id: "artifact-1",
  item_type: "Requirement",
  version: 2,
  values: { title: "Alpha", status: "draft" },
  locked: null,
};

function renderView() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ArtifactTableView itemType="Requirement" />
    </QueryClientProvider>
  );
}

describe("ArtifactTableView", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getWorkspace.mockResolvedValue(DEFINITION);
    getState.mockResolvedValue({ columns: [], filters: {}, sort: [] });
    putState.mockResolvedValue({ columns: [], filters: {}, sort: [] });
    listViews.mockResolvedValue([]);
    query.mockResolvedValue(page([ROW], 1));
    bulkUpdate.mockResolvedValue({ committed: true, mode: "atomic", updated: [], failed: [] });
  });

  it("loads definition, state and rows and renders the columns", async () => {
    renderView();
    expect(await screen.findByTestId("table-row-row-1")).toBeInTheDocument();
    expect(screen.getByTestId("sort-title")).toBeInTheDocument();
    expect(getWorkspace).toHaveBeenCalledWith("ws", "Requirement");
    expect(getState).toHaveBeenCalledWith("ws", "Requirement");
  });

  it("refetches with JSON filters and resets the page", async () => {
    const user = userEvent.setup();
    query.mockResolvedValue(page([ROW], 120));
    renderView();
    await screen.findByTestId("table-row-row-1");
    await user.click(screen.getByTestId("table-page-next"));
    await waitFor(() =>
      expect(query.mock.calls.some(([params]) => params.page === 2)).toBe(true)
    );

    await user.click(screen.getByTestId("filter-trigger-title"));
    await user.type(screen.getByTestId("filter-title-contains"), "abc");
    await waitFor(() =>
      expect(
        query.mock.calls.some(
          ([params]) =>
            params.filters?.title?.op === "contains" &&
            params.filters?.title?.value === "abc" &&
            params.page === 1
        )
      ).toBe(true)
    );
  });

  it("refetches on a sort change", async () => {
    const user = userEvent.setup();
    renderView();
    await screen.findByTestId("table-row-row-1");
    await user.click(screen.getByTestId("sort-title"));
    await waitFor(() =>
      expect(
        query.mock.calls.some(
          ([params]) =>
            Array.isArray(params.sort) && params.sort[0]?.field === "title"
        )
      ).toBe(true)
    );
  });

  it("applies a saved view's filters, sort and columns", async () => {
    const user = userEvent.setup();
    listViews.mockResolvedValue([
      {
        id: "v1", workspace_id: "ws", item_type: "Requirement", owner_id: "me",
        name: "Mine", visibility: "private", version: 1,
        columns: [{ field: "status", order: 0 }],
        filters: { status: { op: "in", value: ["draft"] } },
        sort: [{ field: "title", dir: "desc" }],
      },
    ]);
    applyView.mockResolvedValue({ ...page([]), warnings: [] });
    renderView();
    await screen.findByText("Mine");
    await user.selectOptions(screen.getByTestId("saved-view-select"), "v1");
    await waitFor(() =>
      expect(
        query.mock.calls.some(
          ([params]) =>
            params.filters?.status?.value?.[0] === "draft" &&
            params.sort?.[0]?.dir === "desc"
        )
      ).toBe(true)
    );
  });

  it("enables the bulk bar on selection and refetches after done", async () => {
    const user = userEvent.setup();
    renderView();
    await screen.findByTestId("table-row-row-1");
    const callsBefore = query.mock.calls.length;
    await user.click(screen.getByTestId("row-select-row-1"));
    expect(screen.getByTestId("bulk-action-bar")).toBeInTheDocument();
    await user.click(screen.getByTestId("bulk-edit-fields"));
    await user.type(screen.getByTestId("bulk-field-title"), "Beta");
    await user.click(screen.getByTestId("bulk-submit"));
    expect(bulkUpdate).toHaveBeenCalled();
    await waitFor(() => expect(query.mock.calls.length).toBeGreaterThan(callsBefore));
  });

  it("shows the empty state together with active filter chips", async () => {
    const user = userEvent.setup();
    query.mockResolvedValue(page([]));
    renderView();
    await screen.findByTestId("artifact-table-empty-state");
    await user.click(screen.getByTestId("filter-trigger-title"));
    await user.type(screen.getByTestId("filter-title-contains"), "zzz");
    expect(await screen.findByTestId("active-filter-chips")).toBeInTheDocument();
    expect(screen.getByTestId("artifact-table-empty-state")).toBeInTheDocument();
  });
});

describe("Requirement view toggle", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  function Harness(): JSX.Element {
    const [mode, setMode] = useState<RequirementViewMode>(readRequirementViewMode);
    return (
      <div>
        <RequirementViewToggle
          mode={mode}
          onChange={(next) => {
            setMode(next);
            writeRequirementViewMode(next);
          }}
        />
        <p data-testid="mode">{mode}</p>
      </div>
    );
  }

  it("switches between list and table", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    expect(screen.getByTestId("mode")).toHaveTextContent("list");
    await user.click(screen.getByTestId("req-view-toggle-table"));
    expect(screen.getByTestId("mode")).toHaveTextContent("table");
    expect(window.localStorage.getItem(REQUIREMENT_VIEW_MODE_KEY)).toBe("table");
  });

  it("survives a localStorage failure", () => {
    const getItem = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(readRequirementViewMode()).toBe("list");
    expect(() => writeRequirementViewMode("table")).not.toThrow();
    getItem.mockRestore();
    setItem.mockRestore();
  });
});
