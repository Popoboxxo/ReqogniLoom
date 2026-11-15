/**
 * P3 Task 3.2 — saved connection views live in the registered preference key
 * and nowhere else.
 *
 * The key `ui.connection_view.saved_views` is a user-scoped `str_list` of
 * JSON-encoded view documents in the backend preference registry. These tests
 * pin the read/write contract: an absent key means "no saved views", a read
 * error never rejects (the view must not crash), a rejected write is handed to
 * the caller, and no `localStorage` fallback exists any more.
 *
 * The same file covers the connection view's two display switches
 * (`ui.connection_view.show_edges`, `ui.connection_view.filters_expanded`,
 * navigation plan V.0): user-level booleans whose read falls back to the
 * registry default and whose failed write reports back to the caller while the
 * caller's local state stays untouched.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  FILTERS_EXPANDED_DEFAULT,
  FILTERS_EXPANDED_PREFERENCE_KEY,
  SAVED_VIEWS_PREFERENCE_KEY,
  SHOW_EDGES_DEFAULT,
  SHOW_EDGES_PREFERENCE_KEY,
  connectionViewsApi,
  loadFiltersExpanded,
  loadShowEdges,
  saveFiltersExpanded,
  saveShowEdges,
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

describe("connection view display preferences (navigation plan V.0)", () => {
  it("round-trips show_edges through the user preference level", async () => {
    vi.mocked(preferenceValuesApi.patchLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {},
    });

    await saveShowEdges(false);

    expect(preferenceValuesApi.patchLevel).toHaveBeenCalledWith("user", {
      [SHOW_EDGES_PREFERENCE_KEY]: false,
    });

    vi.mocked(preferenceValuesApi.getLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: { [SHOW_EDGES_PREFERENCE_KEY]: false },
    });

    await expect(loadShowEdges()).resolves.toBe(false);
    expect(preferenceValuesApi.getLevel).toHaveBeenCalledWith("user");
  });

  it("round-trips filters_expanded through the user preference level", async () => {
    vi.mocked(preferenceValuesApi.patchLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {},
    });

    await saveFiltersExpanded(true);

    expect(preferenceValuesApi.patchLevel).toHaveBeenCalledWith("user", {
      [FILTERS_EXPANDED_PREFERENCE_KEY]: true,
    });

    vi.mocked(preferenceValuesApi.getLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: { [FILTERS_EXPANDED_PREFERENCE_KEY]: true },
    });

    await expect(loadFiltersExpanded()).resolves.toBe(true);
  });

  it("load_falls_back_to_default_on_error", async () => {
    vi.mocked(preferenceValuesApi.getLevel).mockRejectedValue(
      new Error("preference store unavailable")
    );
    const getItem = vi.spyOn(Storage.prototype, "getItem");

    await expect(loadShowEdges()).resolves.toBe(SHOW_EDGES_DEFAULT);
    await expect(loadFiltersExpanded()).resolves.toBe(FILTERS_EXPANDED_DEFAULT);

    expect(SHOW_EDGES_DEFAULT).toBe(true);
    expect(FILTERS_EXPANDED_DEFAULT).toBe(false);
    expect(getItem).not.toHaveBeenCalled();
  });

  it("load_falls_back_to_default_when_the_key_is_absent", async () => {
    vi.mocked(preferenceValuesApi.getLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {},
    });

    await expect(loadShowEdges()).resolves.toBe(true);
    await expect(loadFiltersExpanded()).resolves.toBe(false);
  });

  it("load_ignores_a_stored_value_that_is_not_a_boolean", async () => {
    vi.mocked(preferenceValuesApi.getLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {
        [SHOW_EDGES_PREFERENCE_KEY]: "yes",
        [FILTERS_EXPANDED_PREFERENCE_KEY]: 1,
      },
    });

    await expect(loadShowEdges()).resolves.toBe(true);
    await expect(loadFiltersExpanded()).resolves.toBe(false);
  });

  it("save_failure_keeps_local_state", async () => {
    vi.mocked(preferenceValuesApi.patchLevel).mockRejectedValue(
      new Error("preference store unavailable")
    );
    const setItem = vi.spyOn(Storage.prototype, "setItem");

    // The component owns the switch: it flips locally, then tries to persist.
    const localState = { showEdges: false, filtersExpanded: true };

    await expect(saveShowEdges(localState.showEdges)).rejects.toThrow(
      "preference store unavailable"
    );
    await expect(
      saveFiltersExpanded(localState.filtersExpanded)
    ).rejects.toThrow("preference store unavailable");

    // The failure is reported (above) and changes nothing else: the local state
    // keeps the user's choice, and the module kept no mirror of the value it
    // failed to persist — a later read still resolves the registry default.
    expect(localState).toEqual({ showEdges: false, filtersExpanded: true });
    vi.mocked(preferenceValuesApi.getLevel).mockResolvedValue({
      scope: "user",
      workspace_id: null,
      values: {},
    });
    await expect(loadShowEdges()).resolves.toBe(SHOW_EDGES_DEFAULT);
    expect(setItem).not.toHaveBeenCalled();
  });
});
