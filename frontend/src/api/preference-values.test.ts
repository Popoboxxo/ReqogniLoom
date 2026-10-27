/**
 * Q1 preference-values API wrapper (Plan C, T-C2-5) — wire-contract tests.
 *
 * The wrapper is thin, so what is pinned here is the route per scope and the
 * `{ values: … }` envelope: the three level routes are *different paths* and a
 * swappable one would silently write a personal value into the tenant-wide
 * default. `null` is a first-class value (reset = inherit), so it must survive
 * the body unchanged.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { preferenceValuesApi } from "./preference-values";

vi.mock("./client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./client")>();
  return {
    ...actual,
    apiClient: { get: vi.fn(), patch: vi.fn() },
  };
});

describe("preferenceValuesApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("GETs the registry from the metadata route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ keys: [] });

    const result = await preferenceValuesApi.registry();

    expect(apiClient.get).toHaveBeenCalledWith("/preference-values/registry/");
    expect(result.keys).toEqual([]);
  });

  it("GETs the account-wide effective values without a workspace", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      workspace_id: null,
      values: {},
    });

    await preferenceValuesApi.effective();

    expect(apiClient.get).toHaveBeenCalledWith(
      "/users/me/preference-values/effective/"
    );
  });

  it("GETs the effective values through the workspace route when one is given", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      workspace_id: "ws-1",
      values: {},
    });

    await preferenceValuesApi.effective("ws-1");

    expect(apiClient.get).toHaveBeenCalledWith(
      "/workspaces/ws-1/preference-values/effective/"
    );
  });

  it("GETs each level from its own route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {},
    });

    await preferenceValuesApi.getLevel("user");
    await preferenceValuesApi.getLevel("workspace", "ws-1");
    await preferenceValuesApi.getLevel("global");

    expect(vi.mocked(apiClient.get).mock.calls.map((call) => call[0])).toEqual([
      "/users/me/preference-values/",
      "/workspaces/ws-1/preference-values/",
      "/system/preference-values/",
    ]);
  });

  it("refuses a workspace level call without a workspace id instead of guessing", async () => {
    await expect(preferenceValuesApi.getLevel("workspace")).rejects.toThrow(
      /workspace/i
    );
    await expect(
      preferenceValuesApi.patchLevel("workspace", { "ui.ids.show_readable": true })
    ).rejects.toThrow(/workspace/i);
    expect(apiClient.get).not.toHaveBeenCalled();
    expect(apiClient.patch).not.toHaveBeenCalled();
  });

  it("PATCHes the level's `values` envelope and keeps an explicit null (reset)", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      scope: "global",
      workspace_id: null,
      values: {},
    });

    await preferenceValuesApi.patchLevel("global", {
      "ui.markdown.toolbar": "on",
      "ui.ids.show_readable": null,
    });

    expect(apiClient.patch).toHaveBeenCalledWith("/system/preference-values/", {
      values: {
        "ui.markdown.toolbar": "on",
        "ui.ids.show_readable": null,
      },
    });
  });

  it("PATCHes the workspace level through the workspace route", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      scope: "workspace",
      workspace_id: "ws-1",
      values: {},
    });

    await preferenceValuesApi.patchLevel(
      "workspace",
      { "ui.ids.show_readable": false },
      "ws-1"
    );

    expect(apiClient.patch).toHaveBeenCalledWith(
      "/workspaces/ws-1/preference-values/",
      { values: { "ui.ids.show_readable": false } }
    );
  });
});
