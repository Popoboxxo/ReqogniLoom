/**
 * AttributeCatalogPage.test.tsx (WS5 #942).
 *
 * Covers the admin gate on the "Aus Katalog hinzufügen" entry point and the
 * end-to-end add flow through the dialog, at the page level.
 */

import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import "../i18n/index";
import { attributeDefinitionsApi } from "../api/attribute-definitions";
import type { AttributeCatalogEntry } from "../api/attributeCatalog";
import { attributeCatalogApi } from "../api/attributeCatalog";
import type {
  AttributeSpec,
  ResolvedAttributeDefinition,
} from "../api/attribute-definitions";
import { AttributeEditorPage } from "../components/AttributeEditor";

const authState = vi.hoisted(() => ({ roles: ["admin"] as string[] }));

vi.mock("../api/attribute-definitions", () => ({
  attributeDefinitionsApi: {
    getWorkspace: vi.fn(),
    putWorkspace: vi.fn(),
    resetWorkspace: vi.fn(),
    getGlobal: vi.fn(),
    putGlobal: vi.fn(),
  },
}));
vi.mock("../api/attributeCatalog", () => ({
  attributeCatalogApi: {
    listEntries: vi.fn(),
    searchEntries: vi.fn(),
    addToDefinition: vi.fn(),
  },
}));
vi.mock("../context/WorkspaceContext", () => ({
  useWorkspace: () => ({ activeWorkspace: { id: "ws-1", preset: "standard" } }),
}));
vi.mock("../context/AuthContext", () => ({
  useAuth: () => ({ roles: authState.roles }),
}));

function attr(over: Partial<AttributeSpec>): AttributeSpec {
  return {
    name: "title",
    kind: "core",
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

const CATALOG_ENTRY: AttributeCatalogEntry = {
  id: "e1",
  name: "risk_score",
  definition: attr({ name: "risk_score", kind: "extended" }),
  category: "risk",
  tags: ["risk"],
  label: { de: "", en: "" },
  help_text: { de: "", en: "" },
  origin: "",
  deprecated: false,
  version: 1,
  created_at: "2026-09-13T00:00:00Z",
  modified_at: "2026-09-13T00:00:00Z",
};

const DEFINITION: ResolvedAttributeDefinition = {
  item_type: "Requirement",
  preset: "standard",
  is_customized: false,
  version: 1,
  attributes: [attr({ name: "title" })],
  origins: {},
  sections: [],
};

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/attributes/Requirement"]}>
      <AttributeEditorPage scope="workspace" />
    </MemoryRouter>
  );
}

describe("AttributeEditorPage catalog entry (WS5 #942)", () => {
  beforeEach(() => {
    authState.roles = ["admin"];
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockReset();
    vi.mocked(attributeDefinitionsApi.getWorkspace).mockResolvedValue(DEFINITION);
    vi.mocked(attributeCatalogApi.listEntries).mockReset();
    vi.mocked(attributeCatalogApi.searchEntries).mockReset();
    vi.mocked(attributeCatalogApi.addToDefinition).mockReset();
    vi.mocked(attributeCatalogApi.listEntries).mockResolvedValue([CATALOG_ENTRY]);
    vi.mocked(attributeCatalogApi.addToDefinition).mockResolvedValue({
      definition: DEFINITION,
      catalog_entry_id: "e1",
      on_collision: "skip",
    });
  });

  it("hides the catalog entry point from non-admins", async () => {
    authState.roles = ["editor"];
    renderPage();
    await screen.findByTestId("attribute-row-title");
    expect(
      screen.queryByTestId("attribute-editor-add-from-catalog")
    ).not.toBeInTheDocument();
  });

  it("shows the entry point for admins and applies a chosen entry", async () => {
    renderPage();
    await screen.findByTestId("attribute-row-title");
    await userEvent.click(screen.getByTestId("attribute-editor-add-from-catalog"));

    // The dialog searches/browses the catalog.
    await screen.findByTestId("attribute-catalog-entry-e1");
    fireEvent.click(screen.getByTestId("attribute-catalog-entry-e1"));
    fireEvent.click(screen.getByTestId("attribute-catalog-on-collision-overwrite"));
    fireEvent.click(screen.getByTestId("attribute-catalog-add"));

    await waitFor(() =>
      expect(attributeCatalogApi.addToDefinition).toHaveBeenCalledWith("e1", {
        item_type: "Requirement",
        workspace_id: "ws-1",
        on_collision: "overwrite",
      })
    );
    // A successful apply reloads the definition (initial load + reload).
    await waitFor(() =>
      expect(attributeDefinitionsApi.getWorkspace).toHaveBeenCalledTimes(2)
    );
    expect(await screen.findByTestId("attribute-editor-toast")).toHaveTextContent(
      "risk_score"
    );
  });
});
