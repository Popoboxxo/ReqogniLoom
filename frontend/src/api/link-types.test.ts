import { describe, expect, it, vi, beforeEach } from "vitest";

import { apiClient } from "./client";
import { linkTypesApi } from "./link-types";

vi.mock("./client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

const definition = {
  label: {
    de: { downstream: "verifiziert", upstream: "wird verifiziert von", neutral: "Verifikation" },
    en: { downstream: "verifies", upstream: "is verified by", neutral: "Verification" },
  },
  allowed_pairs: [{ source_type: "TestCase", target_type: "Requirement" }],
  coverage_relevant: true,
  suspect_rule: "target_change_flags_source" as const,
  impact_weight: 1.0,
  manual_creatable: true,
  system_owned: false,
  active: true,
  built_in: true,
};

const row = {
  id: "11111111-1111-1111-1111-111111111111",
  workspace_id: "22222222-2222-2222-2222-222222222222",
  key: "verifies",
  definition,
  is_customized: false,
  source_global_id: null,
  version: 1,
};

describe("linkTypesApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("reads the workspace catalog from the workspace-scoped route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([row]);
    const result = await linkTypesApi.listForWorkspace(row.workspace_id);
    expect(apiClient.get).toHaveBeenCalledWith(
      `/workspaces/${row.workspace_id}/link-type-definitions/`,
    );
    expect(result[0].key).toBe("verifies");
  });

  it("sends the definition wrapped in a definition envelope on update", async () => {
    vi.mocked(apiClient.put).mockResolvedValue({ ...row, is_customized: true });
    const result = await linkTypesApi.updateForWorkspace(
      row.workspace_id,
      "verifies",
      definition,
    );
    expect(apiClient.put).toHaveBeenCalledWith(
      `/workspaces/${row.workspace_id}/link-type-definitions/verifies/`,
      { definition },
    );
    expect(result.is_customized).toBe(true);
  });

  it("resets via the dedicated reset route", async () => {
    vi.mocked(apiClient.post).mockResolvedValue(row);
    await linkTypesApi.resetForWorkspace(row.workspace_id, "verifies");
    expect(apiClient.post).toHaveBeenCalledWith(
      `/workspaces/${row.workspace_id}/link-type-definitions/verifies/reset/`,
      {},
    );
  });

  it("reads global defaults from the tenant route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue([]);
    await linkTypesApi.listGlobal();
    expect(apiClient.get).toHaveBeenCalledWith("/link-type-defaults/");
  });

  it("creates a global type with key and definition", async () => {
    vi.mocked(apiClient.post).mockResolvedValue({ key: "conflicts-with", definition });
    await linkTypesApi.createGlobal("conflicts-with", definition);
    expect(apiClient.post).toHaveBeenCalledWith("/link-type-defaults/", {
      key: "conflicts-with",
      definition,
    });
  });

  it("returns an empty list when the response is not an array", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(undefined as never);
    await expect(linkTypesApi.listForWorkspace(row.workspace_id)).resolves.toEqual([]);
  });
});
