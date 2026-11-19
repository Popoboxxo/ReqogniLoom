/**
 * Issue #1096 / Task 2 — displayPreferencesApi unit tests.
 *
 * The wrapper is thin, so the contract worth pinning is the wire shape:
 * the self-service path (no user_id/workspace_id parameter) and the
 * snake_case body/response fields. Task 2 adds two INDEPENDENT display flags,
 * `trace_footer_enabled` and `inspector_enabled`, on top of `show_readable_ids`
 * / `visible_metrics`. The Q1 keys behind them (`ui.trace_footer.enabled`,
 * `ui.inspector.enabled`) are backend-internal — the client only ever sees
 * these HTTP field names.
 */

import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { beforeEach, describe, expect, it, vi } from "vitest";

import { apiClient } from "./client";
import { displayPreferencesApi } from "./display-preferences";

vi.mock("./client", async (importOriginal) => {
  const actual = await importOriginal<typeof import("./client")>();
  return {
    ...actual,
    apiClient: { get: vi.fn(), patch: vi.fn() },
  };
});

const FULL_PREFS = {
  show_readable_ids: true,
  visible_metrics: null,
  trace_footer_enabled: true,
  inspector_enabled: true,
};

describe("displayPreferencesApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("declares both new snake_case fields on the wire interface", () => {
    // The wrapper is a generic passthrough, so runtime tests cannot assert a
    // TypeScript interface. Pin the field names at source level instead.
    const source = readFileSync(
      resolve(__dirname, "./display-preferences.ts"),
      "utf8"
    );
    expect(source).toMatch(
      /interface DisplayPreferences[\s\S]*?trace_footer_enabled:\s*boolean/
    );
    expect(source).toMatch(
      /interface DisplayPreferences[\s\S]*?inspector_enabled:\s*boolean/
    );
  });

  it("GETs the caller's own display flags from the self-service route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue(FULL_PREFS);

    const result = await displayPreferencesApi.get();

    expect(apiClient.get).toHaveBeenCalledWith("/users/me/display-preferences/");
    expect(result.show_readable_ids).toBe(true);
    expect(result.trace_footer_enabled).toBe(true);
    expect(result.inspector_enabled).toBe(true);
  });

  it("PATCHes a flag without a user_id/workspace_id parameter", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      ...FULL_PREFS,
      show_readable_ids: false,
    });

    const result = await displayPreferencesApi.update({ show_readable_ids: false });

    expect(apiClient.patch).toHaveBeenCalledWith("/users/me/display-preferences/", {
      show_readable_ids: false,
    });
    expect(result.show_readable_ids).toBe(false);
  });

  it("GETs both new flags under their exact snake_case names", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({
      ...FULL_PREFS,
      trace_footer_enabled: false,
      inspector_enabled: false,
    });

    const result = await displayPreferencesApi.get();

    expect(result).toHaveProperty("trace_footer_enabled", false);
    expect(result).toHaveProperty("inspector_enabled", false);
    // No camelCase aliases leaked into the wire contract.
    expect(result).not.toHaveProperty("traceFooterEnabled");
    expect(result).not.toHaveProperty("inspectorEnabled");
  });

  it("PATCHes trace_footer_enabled alone and leaves the inspector untouched", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      ...FULL_PREFS,
      trace_footer_enabled: false,
    });

    const result = await displayPreferencesApi.update({
      trace_footer_enabled: false,
    });

    expect(apiClient.patch).toHaveBeenCalledWith("/users/me/display-preferences/", {
      trace_footer_enabled: false,
    });
    expect(result.trace_footer_enabled).toBe(false);
    expect(result.inspector_enabled).toBe(true);
  });

  it("PATCHes inspector_enabled alone and leaves the footer untouched", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      ...FULL_PREFS,
      inspector_enabled: false,
    });

    const result = await displayPreferencesApi.update({
      inspector_enabled: false,
    });

    expect(apiClient.patch).toHaveBeenCalledWith("/users/me/display-preferences/", {
      inspector_enabled: false,
    });
    expect(result.inspector_enabled).toBe(false);
    expect(result.trace_footer_enabled).toBe(true);
  });

  it("PATCHes both flags in one request with the pinned field names", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({
      ...FULL_PREFS,
      trace_footer_enabled: false,
      inspector_enabled: false,
    });

    const result = await displayPreferencesApi.update({
      trace_footer_enabled: false,
      inspector_enabled: false,
    });

    expect(apiClient.patch).toHaveBeenCalledWith("/users/me/display-preferences/", {
      trace_footer_enabled: false,
      inspector_enabled: false,
    });
    expect(result.trace_footer_enabled).toBe(false);
    expect(result.inspector_enabled).toBe(false);
  });
});
