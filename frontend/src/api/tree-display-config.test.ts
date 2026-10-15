/**
 * Issue #1257 — treeDisplayConfigApi unit tests.
 *
 * The wrapper is thin, so the contract worth pinning is the wire shape: which
 * route each scope uses, how `item_type`/`resolve` are encoded, and that a
 * reset travels as an explicit `fields: null` (never as an omitted key, which
 * would read as a no-op).
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { treeDisplayConfigApi } from "./tree-display-config";

vi.mock("./client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./client")>();
  return {
    ...actual,
    apiClient: { get: vi.fn(), patch: vi.fn() },
  };
});

const CATALOG = [
  {
    key: "uid",
    label_key: "treeDisplay.field.uid",
    label: "ID",
    width: "half",
    system: true,
  },
];

describe("treeDisplayConfigApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("GETs the whole per-level map from the personal route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      scope: "user",
      config: {},
      catalog: CATALOG,
    });

    await treeDisplayConfigApi.getScope("user");

    expect(apiClient.get).toHaveBeenCalledWith("/users/me/tree-display-config/");
  });

  it("GETs one item type from the workspace route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      scope: "workspace",
      item_type: "Requirement",
      fields: [],
      catalog: CATALOG,
    });

    await treeDisplayConfigApi.getScope("workspace", {
      itemType: "Requirement",
      workspaceId: "ws-1",
    });

    expect(apiClient.get).toHaveBeenCalledWith(
      "/workspaces/ws-1/tree-display-config/?item_type=Requirement"
    );
  });

  it("GETs the tenant-wide default from the system route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      scope: "global",
      config: {},
      catalog: CATALOG,
    });

    await treeDisplayConfigApi.getScope("global");

    expect(apiClient.get).toHaveBeenCalledWith("/system/tree-display-config/");
  });

  it("requests the effective resolution on the workspace route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      item_type: "Requirement",
      scope: "workspace",
      fields: [{ key: "uid", width: "half" }],
      catalog: CATALOG,
    });

    await treeDisplayConfigApi.getEffective({
      itemType: "Requirement",
      workspaceId: "ws-1",
    });

    expect(apiClient.get).toHaveBeenCalledWith(
      "/workspaces/ws-1/tree-display-config/?item_type=Requirement&resolve=effective"
    );
  });

  it("falls back to the personal route when no workspace is active", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      item_type: "Requirement",
      scope: "default",
      fields: [],
      catalog: CATALOG,
    });

    await treeDisplayConfigApi.getEffective({ itemType: "Requirement" });

    expect(apiClient.get).toHaveBeenCalledWith(
      "/users/me/tree-display-config/?item_type=Requirement&resolve=effective"
    );
  });

  it("PATCHes the ordered fields for one item type", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      scope: "user",
      item_type: "Requirement",
      fields: [{ key: "status", width: "full" }],
      catalog: CATALOG,
    });

    await treeDisplayConfigApi.set("user", {
      itemType: "Requirement",
      fields: ["status"],
    });

    expect(apiClient.patch).toHaveBeenCalledWith("/users/me/tree-display-config/", {
      item_type: "Requirement",
      fields: ["status"],
    });
  });

  it("sends a reset as an explicit null", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      scope: "global",
      item_type: "Requirement",
      fields: null,
      catalog: CATALOG,
    });

    await treeDisplayConfigApi.set("global", {
      itemType: "Requirement",
      fields: null,
    });

    expect(apiClient.patch).toHaveBeenCalledWith("/system/tree-display-config/", {
      item_type: "Requirement",
      fields: null,
    });
  });

  it("refuses the workspace scope without a workspace id", async () => {
    await expect(
      treeDisplayConfigApi.set("workspace", { itemType: "Requirement", fields: [] })
    ).rejects.toThrow("workspace_id");
  });
});
