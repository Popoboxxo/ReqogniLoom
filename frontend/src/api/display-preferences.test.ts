/**
 * Issue #1096 — displayPreferencesApi unit tests.
 *
 * The wrapper is thin, so the contract worth pinning is the wire shape:
 * the self-service path (no user_id/workspace_id parameter) and the
 * `{ show_readable_ids: <bool> }` body. The component tests cover the
 * load/save lifecycle on top of it.
 */

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

describe("displayPreferencesApi", () => {
  beforeEach(() => vi.clearAllMocks());

  it("GETs the caller's own display flags from the self-service route", async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ show_readable_ids: true });

    const result = await displayPreferencesApi.get();

    expect(apiClient.get).toHaveBeenCalledWith("/users/me/display-preferences/");
    expect(result.show_readable_ids).toBe(true);
  });

  it("PATCHes the flag without a user_id/workspace_id parameter", async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ show_readable_ids: false });

    const result = await displayPreferencesApi.update({ show_readable_ids: false });

    expect(apiClient.patch).toHaveBeenCalledWith("/users/me/display-preferences/", {
      show_readable_ids: false,
    });
    expect(result.show_readable_ids).toBe(false);
  });
});
