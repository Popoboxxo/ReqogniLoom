/**
 * P5 Task 5.2 — card-field configuration round-trip and mandatory-marker rule.
 *
 * The configuration travels through the registered preference key only — no
 * client-side mirror. These tests pin the serialization, the normalization of
 * stored documents, the row layout, the "absent key means defaults" contract
 * and the one non-negotiable rule: a mandatory marker (lock) cannot be hidden —
 * the validator (and therefore `save`) rejects it before anything is written.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  CARD_FIELDS_PREFERENCE_KEY,
  cardFieldsApi,
  defaultCardFieldConfig,
  defaultCardFieldConfigMap,
  layoutCardFields,
  normalizeCardFieldConfig,
  parseCardFieldConfigMap,
  serializeCardFieldConfigMap,
  validateCardFieldConfig,
  visibleCardFields,
  type CardFieldConfigMap,
} from "./cardFields";

vi.mock("../../api/preference-values", () => ({
  preferenceValuesApi: {
    effective: vi.fn(),
    patchLevel: vi.fn(),
  },
}));

import { preferenceValuesApi } from "../../api/preference-values";

/** The mirror key the removed fallback used; it must stay unused. */
const REMOVED_LOCAL_KEY = "reqlo.allocation_graph.card_fields.ws-1";

beforeEach(() => {
  vi.clearAllMocks();
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("card field configuration", () => {
  it("round-trips the defaults through serialization", () => {
    const defaults = defaultCardFieldConfigMap();
    expect(parseCardFieldConfigMap(serializeCardFieldConfigMap(defaults))).toEqual(
      defaults
    );
  });

  it("keeps order, visibility and row count through the round-trip", () => {
    const custom: CardFieldConfigMap = defaultCardFieldConfigMap();
    custom.requirement = {
      rows: 3,
      fields: [
        { key: "title", visible: true },
        { key: "owner", visible: true },
        { key: "state", visible: false },
        { key: "lock", visible: true },
      ],
    };

    const parsed = parseCardFieldConfigMap(
      serializeCardFieldConfigMap(custom)
    );

    expect(parsed.requirement).toEqual(custom.requirement);
    expect(visibleCardFields(parsed.requirement)).toEqual(["title", "owner"]);
  });

  it("normalizes a stored document that tries to hide the lock marker", () => {
    const normalized = normalizeCardFieldConfig("requirement", {
      rows: 2,
      fields: [
        { key: "title", visible: true },
        { key: "lock", visible: false },
        { key: "unknown", visible: true },
      ],
    });

    expect(normalized.fields).toContainEqual({ key: "lock", visible: true });
    expect(normalized.fields.some((field) => field.key === "lock")).toBe(true);
    expect(
      normalized.fields.some((field) => String(field.key) === "unknown")
    ).toBe(false);
  });

  it("rejects hiding a mandatory marker", () => {
    const config = defaultCardFieldConfig("requirement");
    config.fields = config.fields.map((field) =>
      field.key === "lock" ? { ...field, visible: false } : field
    );

    expect(() => validateCardFieldConfig("requirement", config)).toThrow(
      /lock/
    );
  });

  it("rejects a row count outside the supported range", () => {
    const config = defaultCardFieldConfig("element");
    expect(() =>
      validateCardFieldConfig("element", { ...config, rows: 0 })
    ).toThrow(/rows/);
    expect(() =>
      validateCardFieldConfig("element", { ...config, rows: 9 })
    ).toThrow(/rows/);
  });

  it("distributes the visible fields over the configured rows", () => {
    const config = defaultCardFieldConfig("requirement");
    config.rows = 2;

    const rows = layoutCardFields(config);

    expect(rows).toHaveLength(2);
    expect(rows.flat()).toEqual(visibleCardFields(config));
  });
});

describe("cardFieldsApi — preference persistence without a local mirror", () => {
  it("loads the stored configuration for the workspace", async () => {
    const custom: CardFieldConfigMap = defaultCardFieldConfigMap();
    custom.element = {
      rows: 1,
      fields: [
        { key: "title", visible: true },
        { key: "group", visible: true },
        { key: "lock", visible: true },
      ],
    };
    const serialized = serializeCardFieldConfigMap(custom);
    vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
      workspace_id: "ws-1",
      values: {
        [CARD_FIELDS_PREFERENCE_KEY]: { value: serialized, source: "workspace" },
      },
    });

    const getItem = vi.spyOn(Storage.prototype, "getItem");
    const setItem = vi.spyOn(Storage.prototype, "setItem");

    await expect(cardFieldsApi.load("ws-1")).resolves.toEqual(custom);
    expect(preferenceValuesApi.effective).toHaveBeenCalledWith("ws-1");
    expect(getItem).not.toHaveBeenCalled();
    expect(setItem).not.toHaveBeenCalled();
  });

  it("saves at the workspace level and writes no local mirror", async () => {
    vi.mocked(preferenceValuesApi.patchLevel).mockResolvedValue({
      scope: "workspace",
      workspace_id: "ws-1",
      values: {},
    });
    const config = defaultCardFieldConfigMap();
    const setItem = vi.spyOn(Storage.prototype, "setItem");

    await cardFieldsApi.save("ws-1", config);

    const serialized = serializeCardFieldConfigMap(config);
    expect(preferenceValuesApi.patchLevel).toHaveBeenCalledWith(
      "workspace",
      { [CARD_FIELDS_PREFERENCE_KEY]: serialized },
      "ws-1"
    );
    expect(setItem).not.toHaveBeenCalled();
    expect(window.localStorage.getItem(REMOVED_LOCAL_KEY)).toBeNull();
  });

  it("never sends a configuration that hides a mandatory marker", async () => {
    const config = defaultCardFieldConfigMap();
    config.requirement.fields = config.requirement.fields.map((field) =>
      field.key === "lock" ? { ...field, visible: false } : field
    );

    await expect(cardFieldsApi.save("ws-1", config)).rejects.toThrow(/lock/);
    expect(preferenceValuesApi.patchLevel).not.toHaveBeenCalled();
  });

  it("propagates a rejected save instead of swallowing it", async () => {
    vi.mocked(preferenceValuesApi.patchLevel).mockRejectedValue(
      new Error("preference store unavailable")
    );

    await expect(
      cardFieldsApi.save("ws-1", defaultCardFieldConfigMap())
    ).rejects.toThrow("preference store unavailable");
  });

  it("treats an absent preference key as the built-in defaults", async () => {
    const config = defaultCardFieldConfigMap();
    config.requirement.rows = 3;
    window.localStorage.setItem(
      REMOVED_LOCAL_KEY,
      JSON.stringify(serializeCardFieldConfigMap(config))
    );
    vi.mocked(preferenceValuesApi.effective).mockResolvedValue({
      workspace_id: "ws-1",
      values: {},
    });

    await expect(cardFieldsApi.load("ws-1")).resolves.toEqual(
      defaultCardFieldConfigMap()
    );
  });

  it("never rejects on a read error and ignores the removed local mirror", async () => {
    const stale = defaultCardFieldConfigMap();
    stale.requirement.rows = 3;
    window.localStorage.setItem(
      REMOVED_LOCAL_KEY,
      JSON.stringify(serializeCardFieldConfigMap(stale))
    );
    vi.mocked(preferenceValuesApi.effective).mockRejectedValue({
      error: { code: "VALIDATION_ERROR", message: "unknown key", details: [] },
    });

    await expect(cardFieldsApi.load("ws-1")).resolves.toEqual(
      defaultCardFieldConfigMap()
    );
  });
});
