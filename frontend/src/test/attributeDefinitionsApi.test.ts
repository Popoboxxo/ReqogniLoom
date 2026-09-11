import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { attributeDefinitionsApi } from "../api/attribute-definitions";

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

const DEFINITION = {
  item_type: "Risk",
  preset: "standard",
  is_customized: false,
  version: 1,
  attributes: [],
};

describe("attributeDefinitionsApi", () => {
  beforeEach(() => {
    vi.mocked(apiClient.get).mockReset();
    vi.mocked(apiClient.put).mockReset();
    vi.mocked(apiClient.post).mockReset();
    vi.mocked(apiClient.delete).mockReset();
  });

  it("reads a global default per item type and preset", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ ...DEFINITION, initialized: true });
    await attributeDefinitionsApi.getGlobal("Risk", "standard");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/attribute-defaults/Risk/standard/"
    );
  });

  it("url-encodes the item type", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ ...DEFINITION, initialized: true });
    await attributeDefinitionsApi.getGlobal("Architecture Element", "minimal");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/attribute-defaults/Architecture%20Element/minimal/"
    );
  });

  it("lists global defaults with optional filters", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ definitions: [] });
    await attributeDefinitionsApi.listGlobal({ itemType: "Risk" });
    expect(apiClient.get).toHaveBeenCalledWith(
      "/attribute-defaults/?item_type=Risk"
    );
  });

  it("sends the attribute list as the PUT body", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ ...DEFINITION, initialized: true });
    await attributeDefinitionsApi.putGlobal("Risk", "standard", []);
    expect(apiClient.put).toHaveBeenCalledWith(
      "/attribute-defaults/Risk/standard/",
      { attributes: [] }
    );
  });

  it("includes sections in the PUT body when given", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ ...DEFINITION, initialized: true });
    await attributeDefinitionsApi.putGlobal("Risk", "standard", [], [
      { name: "general", order: 0, visible: true, layout: "full" },
    ]);
    expect(apiClient.put).toHaveBeenCalledWith(
      "/attribute-defaults/Risk/standard/",
      {
        attributes: [],
        sections: [{ name: "general", order: 0, visible: true, layout: "full" }],
      }
    );
  });

  it("reads a workspace definition", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(DEFINITION);
    await attributeDefinitionsApi.getWorkspace("ws-1", "Risk");
    expect(apiClient.get).toHaveBeenCalledWith(
      "/workspaces/ws-1/attribute-definitions/Risk/"
    );
  });

  it("resets a workspace definition", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(DEFINITION);
    await attributeDefinitionsApi.resetWorkspace("ws-1", "Risk");
    expect(apiClient.post).toHaveBeenCalledWith(
      "/workspaces/ws-1/attribute-definitions/Risk/reset/",
      {}
    );
  });

  it("posts a new extended attribute to the global default", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ...DEFINITION, initialized: true });
    await attributeDefinitionsApi.createGlobalAttribute("Risk", "standard", {
      name: "risk_comment",
      type: "text",
      required: false,
      section: "general",
    });
    expect(apiClient.post).toHaveBeenCalledWith("/attribute-defaults/Risk/standard/", {
      name: "risk_comment",
      kind: "extended",
      type: "text",
      required: false,
      section: "general",
    });
  });

  it("includes options when creating an enum global attribute", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ ...DEFINITION, initialized: true });
    await attributeDefinitionsApi.createGlobalAttribute("Risk", "standard", {
      name: "risk_category",
      type: "enum",
      required: false,
      section: "general",
      options: [{ value: "low", label_de: "low", label_en: "low" }],
    });
    expect(apiClient.post).toHaveBeenCalledWith("/attribute-defaults/Risk/standard/", {
      name: "risk_category",
      kind: "extended",
      type: "enum",
      required: false,
      section: "general",
      options: [{ value: "low", label_de: "low", label_en: "low" }],
    });
  });

  it("deletes a global attribute by name via a query parameter", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue(DEFINITION);
    await attributeDefinitionsApi.deleteGlobalAttribute("Risk", "standard", "note");
    expect(apiClient.delete).toHaveBeenCalledWith(
      "/attribute-defaults/Risk/standard/?name=note"
    );
  });

  it("posts a new workspace-only attribute", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(DEFINITION);
    await attributeDefinitionsApi.createWorkspaceAttribute("ws-1", "Risk", {
      name: "risk_comment",
      type: "text",
      required: false,
      section: "general",
    });
    expect(apiClient.post).toHaveBeenCalledWith(
      "/workspaces/ws-1/attribute-definitions/Risk/",
      { name: "risk_comment", kind: "extended", type: "text", required: false, section: "general" }
    );
  });

  it("deletes a workspace attribute by name via a query parameter", async () => {
    vi.mocked(apiClient.delete).mockResolvedValue(DEFINITION);
    await attributeDefinitionsApi.deleteWorkspaceAttribute("ws-1", "Risk", "note");
    expect(apiClient.delete).toHaveBeenCalledWith(
      "/workspaces/ws-1/attribute-definitions/Risk/?name=note"
    );
  });
});
