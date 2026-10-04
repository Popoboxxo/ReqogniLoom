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

function reqifEnv(overrides: Record<string, unknown> = {}) {
  return {
    created: 0,
    updated: 0,
    skipped: 0,
    failed: 0,
    errors: [],
    items: [],
    ...overrides,
  };
}

describe("importApi.importReqif contract v2 (ADR-014)", () => {
  beforeEach(() => {
    globalThis.fetch = vi.fn() as unknown as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("returns the v2 report of a 207 partial success instead of throwing", async () => {
    const body = {
      success: false,
      contract: "v2",
      dry_run: false,
      counts: { succeeded: 1, skipped: 0, failed: 1, total: 2 },
      items: [
        {
          row: 2,
          identifier: "REQ-2",
          kind: "Requirement",
          status: "failed",
          cause: { code: "INVALID_VALUE", message: "Title too long" },
        },
      ],
      idempotent_replay: false,
      request_id: "req-1",
      needs: reqifEnv({ created: 1 }),
      requirements: reqifEnv({
        failed: 1,
        errors: [{ identifier: "REQ-2", message: "Title too long" }],
        items: [
          {
            row: 2,
            identifier: "REQ-2",
            kind: "Requirement",
            status: "failed",
            cause: { code: "INVALID_VALUE", message: "Title too long" },
          },
        ],
      }),
      relations: reqifEnv(),
      warnings: [],
    };
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(207, body));

    const result = await importApi.importReqif("ws-1", new File(["x"], "a.reqif"));

    expect(result.success).toBe(false);
    expect(result.counts?.failed).toBe(1);
    expect(result.requirements.items?.[0].cause.code).toBe("INVALID_VALUE");
  });

  it("returns the v2 PARSE_ERROR report of a 422 instead of throwing", async () => {
    const body = {
      success: false,
      contract: "v2",
      dry_run: false,
      counts: { succeeded: 0, skipped: 0, failed: 1, total: 1 },
      items: [
        {
          row: null,
          identifier: null,
          kind: null,
          status: "failed",
          cause: { code: "PARSE_ERROR", message: "Malformed ReqIF document." },
        },
      ],
      needs: reqifEnv(),
      requirements: reqifEnv(),
      relations: reqifEnv(),
      warnings: [],
    };
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(422, body));

    const result = await importApi.importReqif("ws-1", new File(["x"], "a.reqif"));

    expect(result.counts?.failed).toBe(1);
    expect(result.items?.[0].cause.code).toBe("PARSE_ERROR");
  });

  it("sends the Idempotency-Key header when one is provided", async () => {
    const body = {
      success: true,
      contract: "v2",
      dry_run: false,
      counts: { succeeded: 1, skipped: 0, failed: 0, total: 1 },
      needs: reqifEnv({ created: 1 }),
      requirements: reqifEnv(),
      relations: reqifEnv(),
      warnings: [],
    };
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(200, body));

    await importApi.importReqif(
      "ws-1",
      new File(["x"], "a.reqif"),
      false,
      "idem-key-1",
    );

    const call = vi.mocked(globalThis.fetch).mock.calls[0];
    const init = call[1] as RequestInit;
    expect((init.headers as Record<string, string>)["Idempotency-Key"]).toBe(
      "idem-key-1",
    );
  });

  it("still throws for a genuine transport/permission failure (403)", async () => {
    vi.mocked(globalThis.fetch).mockResolvedValue(
      jsonResponse(403, { error: { message: "Write permission required" } }),
    );

    await expect(
      importApi.importReqif("ws-1", new File(["x"], "a.reqif")),
    ).rejects.toThrow("Write permission required");
  });

  it("keeps skip-only legacy `errors` empty on a reimport payload", async () => {
    // F3: a reimport yields DUPLICATE *skips*, so the legacy errors list is
    // empty while the v2 counts/items carry the skips.
    const body = {
      success: true,
      contract: "v2",
      dry_run: false,
      counts: { succeeded: 0, skipped: 2, failed: 0, total: 2 },
      needs: reqifEnv({
        skipped: 1,
        errors: [],
        items: [
          {
            row: 1,
            identifier: "N1",
            kind: "StakeholderNeed",
            status: "skipped",
            cause: { code: "DUPLICATE", message: "Identical object." },
          },
        ],
      }),
      requirements: reqifEnv({
        skipped: 1,
        errors: [],
        items: [
          {
            row: 2,
            identifier: "R1",
            kind: "Requirement",
            status: "skipped",
            cause: { code: "DUPLICATE", message: "Identical object." },
          },
        ],
      }),
      relations: reqifEnv(),
      warnings: [],
    };
    vi.mocked(globalThis.fetch).mockResolvedValue(jsonResponse(200, body));

    const result = await importApi.importReqif("ws-1", new File(["x"], "a.reqif"));

    expect(result.needs.errors).toEqual([]);
    expect(result.requirements.errors).toEqual([]);
    expect(result.counts?.skipped).toBe(2);
  });
});
