/**
 * P3 Task 3.2 — saved connection views live in the registered preference key
 * and nowhere else.
 *
 * The key `ui.connection_view.saved_views` is a user-scoped `str_list` of
 * JSON-encoded view documents in the backend preference registry. These tests
 * pin the read/write contract: an absent key means "no saved views", a read
 * error never rejects (the view must not crash), a rejected write is handed to
 * the caller, and no `localStorage` fallback exists any more.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  SAVED_VIEWS_PREFERENCE_KEY,
  connectionViewsApi,
  type SavedConnectionView,
} from "./connection-views";

vi.mock("./preference-values", () => ({
  preferenceValuesApi: {
    getLevel: vi.fn(),
    patchLevel: vi.fn(),
  },
}));

import { preferenceValuesApi } from "./preference-values";

const VIEWS: SavedConnectionView[] = [
  { id: "v1", name: "Offen", params: { q: "bremse", view: "graph" } },
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("connectionViewsApi — preference-backed saved views", () => {
  it("round-trips saved views through the user preference level", async () => {
    vi.mocked(preferenceValuesApi.patchLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {},
    });

    await connectionViewsApi.save(VIEWS);

    expect(preferenceValuesApi.patchLevel).toHaveBeenCalledWith("user", {
      [SAVED_VIEWS_PREFERENCE_KEY]: VIEWS.map((view) => JSON.stringify(view)),
    });

    const serialized = VIEWS.map((view) => JSON.stringify(view));
    vi.mocked(preferenceValuesApi.getLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: { [SAVED_VIEWS_PREFERENCE_KEY]: serialized },
    });

    await expect(connectionViewsApi.load()).resolves.toEqual(VIEWS);
    expect(preferenceValuesApi.getLevel).toHaveBeenCalledWith("user");
  });

  it("treats an absent key as no saved views and touches no local storage", async () => {
    vi.mocked(preferenceValuesApi.getLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {},
    });
    const getItem = vi.spyOn(Storage.prototype, "getItem");
    const setItem = vi.spyOn(Storage.prototype, "setItem");

    await expect(connectionViewsApi.load()).resolves.toEqual([]);

    expect(getItem).not.toHaveBeenCalled();
    expect(setItem).not.toHaveBeenCalled();
  });

  it("never rejects on a read error and falls back to an empty list", async () => {
    vi.mocked(preferenceValuesApi.getLevel).mockRejectedValue(
      new Error("preference store unavailable")
    );
    const getItem = vi.spyOn(Storage.prototype, "getItem");

    await expect(connectionViewsApi.load()).resolves.toEqual([]);

    expect(getItem).not.toHaveBeenCalled();
  });

  it("propagates a rejected save instead of swallowing it", async () => {
    vi.mocked(preferenceValuesApi.patchLevel).mockRejectedValue(
      new Error("preference store unavailable")
    );

    await expect(connectionViewsApi.save(VIEWS)).rejects.toThrow(
      "preference store unavailable"
    );
  });

  it("writes no local mirror on save", async () => {
    vi.mocked(preferenceValuesApi.patchLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {},
    });
    const setItem = vi.spyOn(Storage.prototype, "setItem");

    await connectionViewsApi.save(VIEWS);

    expect(setItem).not.toHaveBeenCalled();
  });

  it("ignores malformed stored items", async () => {
    vi.mocked(preferenceValuesApi.getLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {
        [SAVED_VIEWS_PREFERENCE_KEY]: [
          "not json",
          JSON.stringify(VIEWS[0]),
          JSON.stringify({ id: 1, name: "broken" }),
        ],
      },
    });

    await expect(connectionViewsApi.load()).resolves.toEqual(VIEWS);
  });
});
