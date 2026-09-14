/**
 * AttributeCatalogDialog.test.tsx (WS5 #942, spec section 8).
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import type { AttributeCatalogEntry } from "../../api/attributeCatalog";
import { attributeCatalogApi } from "../../api/attributeCatalog";
import { AttributeCatalogDialog } from "./AttributeCatalogDialog";
import type { AttributeSpec } from "../../api/attribute-definitions";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

vi.mock("../../api/attributeCatalog", () => ({
  attributeCatalogApi: {
    listEntries: vi.fn(),
    searchEntries: vi.fn(),
  },
}));

function attr(over: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "risk_score",
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
    ...over,
  };
}

function entry(over: Partial<AttributeCatalogEntry> = {}): AttributeCatalogEntry {
  return {
    id: "e1",
    name: "risk_score",
    definition: attr({}),
    category: "quality",
    tags: ["risk"],
    label: { de: "", en: "" },
    help_text: { de: "", en: "" },
    origin: "",
    deprecated: false,
    version: 1,
    created_at: "2026-09-13T00:00:00Z",
    modified_at: "2026-09-13T00:00:00Z",
    ...over,
  };
}

function renderDialog(over: Partial<React.ComponentProps<typeof AttributeCatalogDialog>> = {}) {
  return render(
    <AttributeCatalogDialog
      itemType="Requirement"
      onAdd={vi.fn().mockResolvedValue(undefined)}
      onClose={vi.fn()}
      {...over}
    />
  );
}

describe("AttributeCatalogDialog", () => {
  beforeEach(() => {
    vi.mocked(attributeCatalogApi.listEntries).mockReset();
    vi.mocked(attributeCatalogApi.searchEntries).mockReset();
  });

  it("loads non-deprecated entries on mount and renders them", async () => {
    vi.mocked(attributeCatalogApi.listEntries).mockResolvedValue([entry()]);
    renderDialog();
    expect(await screen.findByTestId("attribute-catalog-entry-e1")).toBeInTheDocument();
    expect(attributeCatalogApi.listEntries).toHaveBeenCalledWith({
      includeDeprecated: false,
    });
    // Category and tag are visible as browse metadata.
    expect(screen.getByText("quality")).toBeInTheDocument();
    expect(screen.getByText("risk")).toBeInTheDocument();
  });

  it("searches by name once a term is typed", async () => {
    vi.mocked(attributeCatalogApi.listEntries).mockResolvedValue([]);
    vi.mocked(attributeCatalogApi.searchEntries).mockResolvedValue([entry({ name: "alpha" })]);
    renderDialog();
    await screen.findByTestId("attribute-catalog-empty");

    fireEvent.change(screen.getByTestId("attribute-catalog-search"), {
      target: { value: "alp" },
    });
    await waitFor(() =>
      expect(attributeCatalogApi.searchEntries).toHaveBeenCalledWith("alp", {
        includeDeprecated: false,
      })
    );
    expect(await screen.findByTestId("attribute-catalog-entry-e1")).toBeInTheDocument();
  });

  it("includes deprecated entries when the checkbox is ticked", async () => {
    vi.mocked(attributeCatalogApi.listEntries).mockResolvedValue([]);
    renderDialog();
    await screen.findByTestId("attribute-catalog-empty");

    fireEvent.click(screen.getByTestId("attribute-catalog-include-deprecated"));
    await waitFor(() =>
      expect(attributeCatalogApi.listEntries).toHaveBeenLastCalledWith({
        includeDeprecated: true,
      })
    );
  });

  it("shows the empty state when nothing matches", async () => {
    vi.mocked(attributeCatalogApi.listEntries).mockResolvedValue([]);
    renderDialog();
    expect(await screen.findByTestId("attribute-catalog-empty")).toBeInTheDocument();
  });

  it("shows an error state when the catalog cannot be loaded", async () => {
    vi.mocked(attributeCatalogApi.listEntries).mockRejectedValue(new Error("boom"));
    renderDialog();
    expect(await screen.findByTestId("attribute-catalog-error")).toHaveTextContent("boom");
  });

  it("keeps the add action disabled until an entry is selected", async () => {
    vi.mocked(attributeCatalogApi.listEntries).mockResolvedValue([entry()]);
    renderDialog();
    await screen.findByTestId("attribute-catalog-entry-e1");
    expect(screen.getByTestId("attribute-catalog-add")).toBeDisabled();

    fireEvent.click(screen.getByTestId("attribute-catalog-entry-e1"));
    expect(screen.getByTestId("attribute-catalog-add")).toBeEnabled();
  });

  it("calls onAdd with the selected entry and collision choice, then closes", async () => {
    const onAdd = vi.fn().mockResolvedValue(undefined);
    const onClose = vi.fn();
    vi.mocked(attributeCatalogApi.listEntries).mockResolvedValue([entry()]);
    renderDialog({ onAdd, onClose });
    await screen.findByTestId("attribute-catalog-entry-e1");

    fireEvent.click(screen.getByTestId("attribute-catalog-entry-e1"));
    fireEvent.click(screen.getByTestId("attribute-catalog-on-collision-overwrite"));
    fireEvent.click(screen.getByTestId("attribute-catalog-add"));

    await waitFor(() =>
      expect(onAdd).toHaveBeenCalledWith(
        expect.objectContaining({ id: "e1" }),
        "overwrite"
      )
    );
    await waitFor(() => expect(onClose).toHaveBeenCalledTimes(1));
  });

  it("shows the rejection and keeps the dialog open when applying fails", async () => {
    const onAdd = vi.fn().mockRejectedValue(new Error("reserved name"));
    const onClose = vi.fn();
    vi.mocked(attributeCatalogApi.listEntries).mockResolvedValue([entry()]);
    renderDialog({ onAdd, onClose });
    await screen.findByTestId("attribute-catalog-entry-e1");

    fireEvent.click(screen.getByTestId("attribute-catalog-entry-e1"));
    fireEvent.click(screen.getByTestId("attribute-catalog-add"));

    await waitFor(() =>
      expect(screen.getByTestId("attribute-catalog-submit-error")).toHaveTextContent(
        "reserved name"
      )
    );
    expect(onClose).not.toHaveBeenCalled();
  });
});
