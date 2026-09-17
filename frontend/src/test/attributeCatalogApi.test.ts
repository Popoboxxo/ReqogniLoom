import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import {
  attributeCatalogApi,
  type AttributeCatalogDocument,
  type CatalogEntryInput,
} from "../api/attributeCatalog";
import type { AttributeSpec } from "../api/attribute-definitions";

function attr(over: Partial<AttributeSpec> = {}): AttributeSpec {
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

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
    patch: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const ENTRY = {
  id: "e1",
  name: "risk_score",
  definition: { name: "risk_score" },
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

const DOCUMENT: AttributeCatalogDocument = {
  schema_version: 1,
  document_type: "attribute_catalog",
  entries: [],
};

describe("attributeCatalogApi", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.patch).mockReset();
  });

  it("lists catalog entries without filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ entries: [ENTRY] });
    const result = await attributeCatalogApi.listEntries();
    expect(apiClient.get).toHaveBeenCalledWith("/attribute-catalog/");
    expect(result).toEqual([ENTRY]);
  });

  it("encodes name, category, tag and include_deprecated filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ entries: [] });
    await attributeCatalogApi.listEntries({
      query: "risk",
      category: "risk",
      tags: ["a", "b"],
      includeDeprecated: true,
    });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/attribute-catalog/?query=risk&category=risk&tag=a&tag=b&include_deprecated=true"
    );
  });

  it("searches with a required q parameter", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ entries: [ENTRY] });
    await attributeCatalogApi.searchEntries("risk");
    expect(apiClient.get).toHaveBeenCalledWith("/attribute-catalog/search/?q=risk");
  });

  it("passes include_deprecated through to the search endpoint", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ entries: [] });
    await attributeCatalogApi.searchEntries("risk", { includeDeprecated: true });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/attribute-catalog/search/?q=risk&include_deprecated=true"
    );
  });

  it("reads a single entry by id", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(ENTRY);
    await attributeCatalogApi.getEntry("e1");
    expect(apiClient.get).toHaveBeenCalledWith("/attribute-catalog/e1/");
  });

  it("creates an entry", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(ENTRY);
    const input: CatalogEntryInput = { name: "risk_score", definition: attr() };
    await attributeCatalogApi.createEntry(input);
    expect(apiClient.post).toHaveBeenCalledWith("/attribute-catalog/", input);
  });

  it("patches an entry", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue(ENTRY);
    await attributeCatalogApi.updateEntry("e1", { category: "quality" });
    expect(apiClient.patch).toHaveBeenCalledWith("/attribute-catalog/e1/", {
      category: "quality",
    });
  });

  it("deprecates and un-deprecates an entry", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(ENTRY);
    await attributeCatalogApi.deprecateEntry("e1");
    await attributeCatalogApi.deprecateEntry("e1", false);
    expect(apiClient.post).toHaveBeenNthCalledWith(
      1,
      "/attribute-catalog/e1/deprecate/",
      { deprecated: true }
    );
    expect(apiClient.post).toHaveBeenNthCalledWith(
      2,
      "/attribute-catalog/e1/deprecate/",
      { deprecated: false }
    );
  });

  it("adds to a global definition via preset", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      definition: {},
      catalog_entry_id: "e1",
      on_collision: "rename",
    });
    await attributeCatalogApi.addToDefinition("e1", {
      item_type: "Requirement",
      preset: "standard",
      on_collision: "rename",
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/attribute-catalog/e1/add-to-definition/",
      { item_type: "Requirement", on_collision: "rename", preset: "standard" }
    );
  });

  it("adds to a workspace definition via workspace_id and defaults to skip", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({
      definition: {},
      catalog_entry_id: "e1",
      on_collision: "skip",
    });
    await attributeCatalogApi.addToDefinition("e1", {
      item_type: "Requirement",
      workspace_id: "ws-1",
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/attribute-catalog/e1/add-to-definition/",
      { item_type: "Requirement", on_collision: "skip", workspace_id: "ws-1" }
    );
  });

  it("exports the catalog document", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(DOCUMENT);
    const result = await attributeCatalogApi.exportCatalog();
    expect(apiClient.get).toHaveBeenCalledWith(
      "/attribute-catalog/export/?include_deprecated=true"
    );
    expect(result).toEqual(DOCUMENT);
  });

  it("imports the catalog document with an on_collision", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ created: 0, updated: 0, total: 0 });
    await attributeCatalogApi.importCatalog(DOCUMENT, "overwrite");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/attribute-catalog/import/?on_collision=overwrite",
      DOCUMENT
    );
  });
});
