/**
 * ARCH-L1-001 ReactFrontend — prompt variable API wrapper (spec §3.1, §5).
 *
 * Pins the URL shapes and payloads, which is the part a component test with a
 * mocked module can never catch.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

const get = vi.fn();
const put = vi.fn();
const del = vi.fn();

vi.mock("../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => get(...args),
    put: (...args: unknown[]) => put(...args),
    delete: (...args: unknown[]) => del(...args),
  },
}));

const WORKSPACE_ID = "11111111-1111-1111-1111-111111111111";

describe("promptVariablesApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    get.mockResolvedValue({ variables: [], count: 0, workspace_id: null });
    put.mockResolvedValue({});
    del.mockResolvedValue({});
  });

  it("lists tenant-global variables without a query string", async () => {
    const { promptVariablesApi } = await import("../api/prompt-variables");

    await promptVariablesApi.list();

    expect(get).toHaveBeenCalledWith("/prompt-variables/");
  });

  it("lists workspace-scoped variables with an encoded query string", async () => {
    const { promptVariablesApi } = await import("../api/prompt-variables");

    await promptVariablesApi.list(WORKSPACE_ID);

    expect(get).toHaveBeenCalledWith(
      `/prompt-variables/?workspace_id=${WORKSPACE_ID}`
    );
  });

  it("saves a value as a JSON body at the requested scope", async () => {
    const { promptVariablesApi } = await import("../api/prompt-variables");

    await promptVariablesApi.save("max_breadth", 4, WORKSPACE_ID);

    expect(put).toHaveBeenCalledWith(
      `/prompt-variables/max_breadth/?workspace_id=${WORKSPACE_ID}`,
      { value: 4 }
    );
  });

  it("passes var_type and description when creating a new variable", async () => {
    const { promptVariablesApi } = await import("../api/prompt-variables");

    await promptVariablesApi.save("tone_hint", "Be terse.", null, {
      varType: "str",
      description: "Style instruction.",
    });

    expect(put).toHaveBeenCalledWith("/prompt-variables/tone_hint/", {
      value: "Be terse.",
      var_type: "str",
      description: "Style instruction.",
    });
  });

  it("encodes the variable name in the path", async () => {
    const { promptVariablesApi } = await import("../api/prompt-variables");

    await promptVariablesApi.clear("weird name");

    expect(del).toHaveBeenCalledWith("/prompt-variables/weird%20name/");
  });
});
