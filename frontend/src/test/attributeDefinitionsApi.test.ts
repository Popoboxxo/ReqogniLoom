import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "../api/client";
import { attributeDefinitionsApi } from "../api/attribute-definitions";

vi.mock("../api/client", () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
    post: vi.fn(),
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
});
