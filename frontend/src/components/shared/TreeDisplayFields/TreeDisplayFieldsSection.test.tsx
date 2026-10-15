/**
 * Issue #1257 — the settings editor for one level of the tree-display config.
 *
 * Pins the interaction contract every level (personal / workspace / tenant-wide)
 * shares: show what *this* level stores (never the resolved value), mark an
 * unconfigured item type as inherited, save add/reorder/remove immediately, and
 * reset with an explicit `fields: null`. A rejected save must roll back and be
 * announced through `role="alert"`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { treeDisplayConfigApi } from "../../../api/tree-display-config";
import {
  getTreeDisplayFields,
  resetTreeDisplayFields,
} from "../../../hooks/useTreeDisplayFields";
import { TreeDisplayFieldsSection } from "./TreeDisplayFieldsSection";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../api/tree-display-config", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../../api/tree-display-config")>();
  return {
    ...actual,
    treeDisplayConfigApi: {
      getScope: vi.fn(),
      getEffective: vi.fn(),
      set: vi.fn(),
    },
  };
});

const CATALOG = [
  {
    key: "uid",
    label_key: "treeDisplay.field.uid",
    label: "ID",
    width: "half" as const,
    system: true,
  },
  {
    key: "level",
    label_key: "treeDisplay.field.level",
    label: "Level",
    width: "half" as const,
    system: true,
  },
  {
    key: "status",
    label_key: "treeDisplay.field.status",
    label: "Status",
    width: "half" as const,
    system: true,
  },
];

const STORED = [{ key: "uid", width: "half" as const }];

/** What the (mocked) server would answer after the last successful write. */
let serverFields: { key: string; width: "full" | "half" }[] = [...STORED];

function renderSection(workspaceId: string | null = null) {
  return render(
    <TreeDisplayFieldsSection
      scope={workspaceId ? "workspace" : "user"}
      workspaceId={workspaceId}
      titleKey="treeDisplay.user.title"
      hintKey="treeDisplay.user.hint"
      testId="cfg"
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  resetTreeDisplayFields();
  serverFields = [...STORED];
  vi.mocked(treeDisplayConfigApi.getScope).mockResolvedValue({
    scope: "user",
    config: { Requirement: STORED },
    catalog: CATALOG,
  });
  vi.mocked(treeDisplayConfigApi.set).mockImplementation(async (_scope, write) => {
    serverFields = (write.fields ?? [])
      .map((entry) => (typeof entry === "string" ? { key: entry, width: "half" as const } : entry));
    return {
      scope: "user",
      item_type: write.itemType,
      fields: serverFields,
      catalog: CATALOG,
    };
  });
  // The store refresh after a save reads the *effective* value; here that is
  // whatever the last write stored.
  vi.mocked(treeDisplayConfigApi.getEffective).mockImplementation(async () => ({
    item_type: "Requirement",
    scope: "user",
    fields: serverFields,
    catalog: CATALOG,
  }));
});

afterEach(() => resetTreeDisplayFields());

describe("TreeDisplayFieldsSection", () => {
  it("loads the level's own map and the catalogue", async () => {
    renderSection();

    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );
    expect(treeDisplayConfigApi.getScope).toHaveBeenCalledWith("user", {
      workspaceId: null,
    });
    expect(screen.getByTestId("cfg-field-Requirement-uid")).toBeInTheDocument();
    // The catalogue offers the not-yet-selected fields in the add menu.
    expect(screen.getByTestId("cfg-add-Requirement")).toBeInTheDocument();
  });

  it("marks an item type without a stored entry as inherited", async () => {
    renderSection();

    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );
    expect(screen.getByTestId("cfg-inherited-Adr")).toBeInTheDocument();
    expect(screen.queryByTestId("cfg-fields-Adr")).not.toBeInTheDocument();
    // Nothing to reset on an inherited level.
    expect(screen.getByTestId("cfg-reset-Adr")).toBeDisabled();
  });

  it("adds a field at the end of the ordered list and saves immediately", async () => {
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    fireEvent.change(screen.getByTestId("cfg-add-Requirement"), {
      target: { value: "status" },
    });

    await waitFor(() =>
      expect(treeDisplayConfigApi.set).toHaveBeenCalledWith(
        "user",
        {
          itemType: "Requirement",
          fields: [
            { key: "uid", width: "half" },
            { key: "status", width: "half" },
          ],
        },
        null
      )
    );
  });

  it("reorders with the arrow buttons", async () => {
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );
    fireEvent.change(screen.getByTestId("cfg-add-Requirement"), {
      target: { value: "status" },
    });
    await waitFor(() => expect(treeDisplayConfigApi.set).toHaveBeenCalledTimes(1));

    fireEvent.click(screen.getByTestId("cfg-up-Requirement-status"));

    await waitFor(() =>
      expect(treeDisplayConfigApi.set).toHaveBeenLastCalledWith(
        "user",
        {
          itemType: "Requirement",
          fields: [
            { key: "status", width: "half" },
            { key: "uid", width: "half" },
          ],
        },
        null
      )
    );
    // First row's "up" is disabled, last row's "down" is disabled.
    expect(screen.getByTestId("cfg-up-Requirement-status")).toBeDisabled();
    expect(screen.getByTestId("cfg-down-Requirement-uid")).toBeDisabled();
  });

  it("removes a field", async () => {
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("cfg-remove-Requirement-uid"));

    await waitFor(() =>
      expect(treeDisplayConfigApi.set).toHaveBeenCalledWith(
        "user",
        { itemType: "Requirement", fields: [] },
        null
      )
    );
  });

  it("resets the level with an explicit null", async () => {
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("cfg-reset-Requirement"));

    await waitFor(() =>
      expect(treeDisplayConfigApi.set).toHaveBeenCalledWith(
        "user",
        { itemType: "Requirement", fields: null },
        null
      )
    );
    await waitFor(() =>
      expect(screen.getByTestId("cfg-inherited-Requirement")).toBeInTheDocument()
    );
  });

  it("refreshes the tree's own store after a save", async () => {
    // The workspace section knows the workspace the tree reads from, so the
    // refresh targets exactly that cache entry.
    renderSection("ws-7");
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    fireEvent.change(screen.getByTestId("cfg-add-Requirement"), {
      target: { value: "level" },
    });

    await waitFor(() =>
      expect(treeDisplayConfigApi.getEffective).toHaveBeenCalledWith({
        itemType: "Requirement",
        workspaceId: "ws-7",
      })
    );
    await waitFor(() =>
      expect(getTreeDisplayFields("Requirement")).toEqual(["uid", "level"])
    );
  });

  it("rolls back and reports a rejected save", async () => {
    vi.mocked(treeDisplayConfigApi.set).mockRejectedValue(
      new Error("Permission denied")
    );
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    fireEvent.change(screen.getByTestId("cfg-add-Requirement"), {
      target: { value: "status" },
    });

    await waitFor(() =>
      expect(screen.getByTestId("cfg-error")).toHaveTextContent("Permission denied")
    );
    // The optimistic entry is gone again.
    expect(screen.queryByTestId("cfg-field-Requirement-status")).not.toBeInTheDocument();
  });

  it("scopes a workspace section to its workspace", async () => {
    renderSection("ws-7");

    await waitFor(() =>
      expect(treeDisplayConfigApi.getScope).toHaveBeenCalledWith("workspace", {
        workspaceId: "ws-7",
      })
    );
  });

  it("reports a failed load instead of pretending the level is empty", async () => {
    vi.mocked(treeDisplayConfigApi.getScope).mockRejectedValue(
      new Error("boom")
    );
    renderSection();

    await waitFor(() =>
      expect(screen.getByTestId("cfg-error")).toHaveTextContent("boom")
    );
  });
});
