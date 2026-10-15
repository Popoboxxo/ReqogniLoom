/**
 * Issue #1257 — `useTreeDisplayFields` store/loader unit tests.
 *
 * The store is the synchronous read surface every tree row uses, so the
 * contract worth pinning is:
 *   - an unknown item type (or no item type at all) reads as the pre-#1257
 *     default and never triggers a request;
 *   - a load writes the resolved keys and is deduplicated per
 *     (itemType, workspace);
 *   - a *failed* load degrades to the default instead of throwing or clearing
 *     the tree — and is not retried in a loop.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import { act, renderHook, waitFor } from "@testing-library/react";

import { treeDisplayConfigApi } from "../api/tree-display-config";
import {
  DEFAULT_TREE_DISPLAY_FIELDS,
  getTreeDisplayFields,
  loadTreeDisplayFields,
  resetTreeDisplayFields,
  setTreeDisplayFields,
  useTreeDisplayFields,
  useTreeDisplayFieldsLoader,
} from "./useTreeDisplayFields";

vi.mock("../api/tree-display-config", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../api/tree-display-config")>();
  return {
    ...actual,
    treeDisplayConfigApi: { getEffective: vi.fn(), getScope: vi.fn(), set: vi.fn() },
  };
});

function payload(keys: string[]) {
  return {
    item_type: "Requirement",
    scope: "workspace" as const,
    fields: keys.map((key) => ({ key, width: "half" as const })),
    catalog: [],
  };
}

describe("useTreeDisplayFields", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetTreeDisplayFields();
  });

  it("reads the pre-#1257 default for an unconfigured item type", () => {
    expect(getTreeDisplayFields("Requirement")).toEqual(DEFAULT_TREE_DISPLAY_FIELDS);
    expect(DEFAULT_TREE_DISPLAY_FIELDS).toEqual([
      "uid",
      "level",
      "status",
      "updated_at",
      "version",
    ]);
  });

  it("reads the default without an item type and never requests anything", async () => {
    const { result } = renderHook(() => useTreeDisplayFields());

    expect(result.current).toEqual(DEFAULT_TREE_DISPLAY_FIELDS);
    expect(treeDisplayConfigApi.getEffective).not.toHaveBeenCalled();
  });

  it("publishes a stored selection synchronously to subscribers", () => {
    setTreeDisplayFields("Requirement", ["status", "uid"]);

    expect(getTreeDisplayFields("Requirement")).toEqual(["status", "uid"]);
  });

  it("clears a selection back to the default when set to null", () => {
    setTreeDisplayFields("Requirement", ["status"]);
    setTreeDisplayFields("Requirement", null);

    expect(getTreeDisplayFields("Requirement")).toEqual(DEFAULT_TREE_DISPLAY_FIELDS);
  });

  it("loads the resolved keys into the store", async () => {
    vi.mocked(treeDisplayConfigApi.getEffective).mockResolvedValue(
      payload(["owner", "uid"])
    );

    await loadTreeDisplayFields("Requirement", "ws-1");

    expect(treeDisplayConfigApi.getEffective).toHaveBeenCalledWith({
      itemType: "Requirement",
      workspaceId: "ws-1",
    });
    expect(getTreeDisplayFields("Requirement")).toEqual(["owner", "uid"]);
  });

  it("deduplicates concurrent loads for the same target", async () => {
    vi.mocked(treeDisplayConfigApi.getEffective).mockResolvedValue(payload(["uid"]));

    await Promise.all([
      loadTreeDisplayFields("Requirement", "ws-1"),
      loadTreeDisplayFields("Requirement", "ws-1"),
    ]);

    expect(treeDisplayConfigApi.getEffective).toHaveBeenCalledTimes(1);
  });

  it("does not refetch an already-loaded target, but honours force", async () => {
    vi.mocked(treeDisplayConfigApi.getEffective).mockResolvedValue(payload(["uid"]));

    await loadTreeDisplayFields("Requirement", "ws-1");
    await loadTreeDisplayFields("Requirement", "ws-1");
    expect(treeDisplayConfigApi.getEffective).toHaveBeenCalledTimes(1);

    await loadTreeDisplayFields("Requirement", "ws-1", { force: true });
    expect(treeDisplayConfigApi.getEffective).toHaveBeenCalledTimes(2);
  });

  it("keeps the default when the load fails instead of clearing the tree", async () => {
    vi.mocked(treeDisplayConfigApi.getEffective).mockRejectedValue(
      new Error("network down")
    );

    await expect(
      loadTreeDisplayFields("Requirement", "ws-1")
    ).resolves.toBeUndefined();
    expect(getTreeDisplayFields("Requirement")).toEqual(DEFAULT_TREE_DISPLAY_FIELDS);

    // A failed attempt is remembered: the effect does not retry in a loop.
    await loadTreeDisplayFields("Requirement", "ws-1", { force: true });
    expect(treeDisplayConfigApi.getEffective).toHaveBeenCalledTimes(2);
  });

  it("loads on mount through the loader hook and re-renders subscribers", async () => {
    vi.mocked(treeDisplayConfigApi.getEffective).mockResolvedValue(
      payload(["status"])
    );

    const { result } = renderHook(() => {
      useTreeDisplayFieldsLoader("Requirement", "ws-1");
      return useTreeDisplayFields("Requirement");
    });

    expect(result.current).toEqual(DEFAULT_TREE_DISPLAY_FIELDS);
    await act(async () => {
      await waitFor(() => expect(result.current).toEqual(["status"]));
    });
  });

  it("does not load without an item type", async () => {
    renderHook(() => useTreeDisplayFieldsLoader(undefined, "ws-1"));

    await Promise.resolve();
    expect(treeDisplayConfigApi.getEffective).not.toHaveBeenCalled();
  });

  it("does not load without a workspace", async () => {
    // The workspace level is what the request resolves; without one the tree
    // keeps the built-in default instead of showing another level's choice.
    renderHook(() => useTreeDisplayFieldsLoader("Requirement", null));

    await Promise.resolve();
    expect(treeDisplayConfigApi.getEffective).not.toHaveBeenCalled();
  });
});
