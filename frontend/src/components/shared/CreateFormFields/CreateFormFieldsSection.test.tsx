/**
 * Issue #1263 — the settings editor for one level of the create-dialog form
 * definition.
 *
 * Pins the interaction contract every level shares: show what *this* level
 * stores (never the resolved value), mark an unconfigured item type as inherited,
 * save visible/required/order changes immediately, render a live preview of the
 * resulting dialog, and reset with an explicit `fields: null`. A rejected save
 * must roll back and be announced through `role="alert"`.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import { createFormConfigApi } from "../../../api/create-form-config";
import { CreateFormFieldsSection } from "./CreateFormFieldsSection";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../../api/create-form-config", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("../../../api/create-form-config")>();
  return {
    ...actual,
    createFormConfigApi: {
      getScope: vi.fn(),
      getEffective: vi.fn(),
      set: vi.fn(),
    },
  };
});

/** The definition-derived base: all three editable attributes. */
const CATALOG = [
  {
    field_key: "title",
    visible: true,
    required: true,
    order: 0,
    default: null,
  },
  {
    field_key: "description",
    visible: true,
    required: false,
    order: 1,
    default: null,
  },
  {
    field_key: "priority",
    visible: true,
    required: false,
    order: 2,
    default: "medium",
  },
];

const STORED = [
  { field_key: "description", visible: false, required: false, order: 0, default: null },
];

let serverStored: typeof STORED | null = [...STORED];

function renderSection(workspaceId: string | null = null) {
  return render(
    <CreateFormFieldsSection
      scope={workspaceId ? "workspace" : "global"}
      workspaceId={workspaceId}
      titleKey="createForm.global.title"
      hintKey="createForm.global.hint"
      testId="cfg"
    />
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  serverStored = [...STORED];
  vi.mocked(createFormConfigApi.getScope).mockImplementation(async () => ({
    scope: "global",
    item_type: "Requirement",
    fields: serverStored,
    catalog: CATALOG,
  }));
  vi.mocked(createFormConfigApi.set).mockImplementation(async (_scope, write) => {
    serverStored = write.fields;
    return {
      scope: "global",
      item_type: write.itemType,
      fields: serverStored,
      catalog: CATALOG,
    };
  });
});

afterEach(() => vi.clearAllMocks());

describe("CreateFormFieldsSection", () => {
  it("renders the base fields and the live preview in order", async () => {
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    expect(createFormConfigApi.getScope).toHaveBeenCalledWith("global", {
      itemType: "Requirement",
      workspaceId: null,
    });
    // A stored `description` overrides the base entry; title/priority keep theirs.
    expect(screen.getByTestId("cfg-field-title")).toBeInTheDocument();
    expect(screen.getByTestId("cfg-field-priority")).toBeInTheDocument();
    // `description` is hidden at this level, so it is absent from the preview.
    expect(
      screen.queryByTestId("cfg-preview-field-description")
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("cfg-preview-field-title")).toBeInTheDocument();
  });

  it("marks the level as inherited when nothing is stored", async () => {
    serverStored = null;
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );
    expect(screen.getByTestId("cfg-inherited-Requirement")).toBeInTheDocument();
    // Reset is a no-op on an inherited level.
    expect(screen.getByTestId("cfg-reset-Requirement")).toBeDisabled();
    // The preview still shows the definition default.
    expect(screen.getByTestId("cfg-preview-field-title")).toBeInTheDocument();
  });

  it("hides a field and updates the preview immediately", async () => {
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("cfg-visible-title"));

    await waitFor(() =>
      expect(createFormConfigApi.set).toHaveBeenCalled()
    );
    const [, write] = vi.mocked(createFormConfigApi.set).mock.calls[0];
    const title = write.fields?.find((entry) => entry.field_key === "title");
    expect(title?.visible).toBe(false);
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-preview-field-title")).not.toBeInTheDocument()
    );
  });

  it("marks a field required", async () => {
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("cfg-required-description"));

    await waitFor(() => expect(createFormConfigApi.set).toHaveBeenCalled());
    const [, write] = vi.mocked(createFormConfigApi.set).mock.calls[0];
    const description = write.fields?.find(
      (entry) => entry.field_key === "description"
    );
    expect(description?.required).toBe(true);
  });

  it("reorders with the arrow buttons and writes dense order values", async () => {
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("cfg-down-title"));

    await waitFor(() => expect(createFormConfigApi.set).toHaveBeenCalled());
    const [, write] = vi.mocked(createFormConfigApi.set).mock.calls[0];
    // `title` was second (after the stored `description` at 0); ↓ moves it one
    // position down, below `priority`, and the order values stay dense.
    expect(write.fields?.map((entry) => entry.field_key)).toEqual([
      "description",
      "priority",
      "title",
    ]);
    expect(write.fields?.map((entry) => entry.order)).toEqual([0, 1, 2]);
  });

  it("resets the level with an explicit null", async () => {
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("cfg-reset-Requirement"));

    await waitFor(() =>
      expect(createFormConfigApi.set).toHaveBeenCalledWith(
        "global",
        { itemType: "Requirement", fields: null },
        null
      )
    );
    await waitFor(() =>
      expect(screen.getByTestId("cfg-inherited-Requirement")).toBeInTheDocument()
    );
  });

  it("scopes a workspace section to its workspace", async () => {
    renderSection("ws-7");
    await waitFor(() =>
      expect(createFormConfigApi.getScope).toHaveBeenCalledWith("workspace", {
        itemType: "Requirement",
        workspaceId: "ws-7",
      })
    );
  });

  it("rolls back and reports a rejected save", async () => {
    vi.mocked(createFormConfigApi.set).mockRejectedValue(
      new Error("Permission denied")
    );
    renderSection();
    await waitFor(() =>
      expect(screen.queryByTestId("cfg-loading")).not.toBeInTheDocument()
    );

    fireEvent.click(screen.getByTestId("cfg-visible-title"));

    await waitFor(() =>
      expect(screen.getByTestId("cfg-error")).toHaveTextContent("Permission denied")
    );
    // The optimistic change is gone again: title is visible once more.
    expect(screen.getByTestId("cfg-preview-field-title")).toBeInTheDocument();
  });

  it("reports a failed load instead of pretending the level is empty", async () => {
    vi.mocked(createFormConfigApi.getScope).mockRejectedValue(new Error("boom"));
    renderSection();
    await waitFor(() =>
      expect(screen.getByTestId("cfg-error")).toHaveTextContent("boom")
    );
  });
});
