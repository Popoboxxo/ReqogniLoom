/**
 * ARCH-L1-001 ReactFrontend — CSV import API client error handling (UI-30).
 *
 * leaf_id: COMP-RF-001 (api/import)
 * req_id:  REQ-L0-013 (CSV bulk import)
 *
 * `CsvImportView` answers a rejected import with **HTTP 400 and a complete
 * ImportResult** — `success: false` plus the per-row error list. The client
 * used to treat every non-2xx as an opaque transport error, so that list was
 * discarded before it ever reached the component and the user saw a bare
 * "Import failed (HTTP 400)". These cases pin the distinction between "the
 * server rejected the data" (a result) and "the request itself failed" (an
 * error).
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";

import { importApi } from "../../api/import";

const originalFetch = globalThis.fetch;

function jsonResponse(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: () => Promise.resolve(body),
  } as unknown as Response;
}

describe("importApi.importCsv error handling", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn() as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("returns the per-row report of a 400-rejected import instead of throwing", async () => {
    const body = {
      success: false,
      imported_count: 0,
      skipped_count: 2,
      status: "validation_error",
      errors: [{ row_number: 2, field: "title", message: "Required field is empty" }],
      warnings: [],
    };
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(400, body));

    const result = await importApi.importCsv(
      "ws-1",
      new File(["title\n"], "a.csv"),
      "Requirement",
    );

    expect(result.success).toBe(false);
    expect(result.errors).toHaveLength(1);
    expect(result.errors[0].message).toBe("Required field is empty");
  });

  it("defaults `warnings` so callers never touch an undefined list", async () => {
    // An older backend (or a hand-rolled fixture) may omit the field entirely.
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse(201, {
        success: true,
        imported_count: 1,
        skipped_count: 0,
        status: "ok",
        errors: [],
      }),
    );

    const result = await importApi.importCsv(
      "ws-1",
      new File(["title\nA\n"], "a.csv"),
      "Requirement",
    );

    expect(result.warnings).toEqual([]);
  });

  it("still throws for a genuine transport/permission failure", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse(403, { error: { message: "Write permission required" } }),
    );

    await expect(
      importApi.importCsv("ws-1", new File(["title\n"], "a.csv"), "Requirement"),
    ).rejects.toThrow("Write permission required");
  });
});
